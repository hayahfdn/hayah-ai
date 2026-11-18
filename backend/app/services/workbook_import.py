"""Load month-sheet wells extracted from Hayah's workbook into the system.

Input is the JSON written by scripts/workbook_pdf_extract.py (the same shape can
later come from an .xlsx reader). Rules:
  * A row without a clear Well ID is never imported; it is reported.
  * A Well ID that already exists is never overwritten; it is reported.
  * A delivery date from the workbook is recorded as a delivery confirmation,
    approved by the person running the import, so the audit trail says where
    it came from.
  * Nothing is deleted.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConstructionStatus, Contractor, PaymentStatus, User
from app.services import delivery as dsvc, projects as psvc
from app.services.finance import ensure_workbook_defaults

SOURCE = "workbook_import"
_PREFIX = {"pak": ("PAK", "Pak", "Pakistan"), "nep": ("NEP", "Nepal", "Nepal"),
           "bang": ("BANG", "Bangladesh", "Bangladesh"), "india": ("IND", "India", "India"),
           "tiz": ("TZ", "Tanzania", "Tanzania"), "tz": ("TZ", "Tanzania", "Tanzania")}


def contractor_for(db: Session, text: str | None, created: list[str]) -> Contractor | None:
    if not text:
        return None
    m = re.fullmatch(r"\s*([A-Za-z]+)\s*(\d+)\s*", text)
    if not m or m.group(1).lower() not in _PREFIX:
        return None
    code_p, name_p, country = _PREFIX[m.group(1).lower()]
    code = f"{code_p}{int(m.group(2))}"
    c = db.scalar(select(Contractor).where(Contractor.code == code))
    if not c:
        c = Contractor(code=code, name=f"{name_p} {int(m.group(2))}", country=country)
        db.add(c)
        db.flush()
        created.append(code)
    return c


def _money(v) -> Decimal | None:
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


def import_wells(db: Session, data: dict, *, actor: User) -> dict:
    ensure_workbook_defaults(db)
    report = {"imported": 0, "delivered": 0, "skipped_existing": [], "skipped_no_id": [],
              "unknown_contractor": [], "contractors_created": [], "by_month": {}}
    for sheet in data["sheets"]:
        month = sheet["month"]
        stats = report["by_month"].setdefault(month, {"wells": 0, "sales": Decimal("0"), "cost": Decimal("0")})
        for r in sheet["rows"]:
            wid = r.get("well_id")
            if not wid:
                report["skipped_no_id"].append({"month": month, "pages": r.get("pages")})
                continue
            if psvc.get_by_well_id(db, wid):
                report["skipped_existing"].append(wid)
                continue
            con = contractor_for(db, r.get("contractor"), report["contractors_created"])
            if r.get("contractor") and not con:
                report["unknown_contractor"].append({"well_id": wid, "contractor": r["contractor"]})
            source = r.get("sales_source")
            notes_in = r.get("notes")
            if month == "2026-08" and notes_in and not source:
                # In the August sheet the lead source was typed in the notes column.
                source, notes_in = notes_in, None
            notes = [n for n in (notes_in, f"Follow-up: {r['follow_up']}" if r.get("follow_up") and r["follow_up"] != ".." else None) if n]
            notes.append(f"Imported from the workbook ({month} sheet, PDF page {r['pages'][0]}).")
            sale, cost = _money(r.get("sale_amount")), _money(r.get("cost"))
            fields = {
                "well_id": wid, "order_date": _d(r.get("order_date")), "customer_name": r.get("customer_name"),
                "well_type": r.get("well_type"), "contractor_id": con.id if con else None,
                "country": con.country if con else None, "sale_amount": sale, "cost": cost,
                "payment_method": r.get("payment_method"), "extras": r.get("extras"), "sales_source": source,
                "received_date": _d(r.get("received_date")), "notes": "\n".join(notes),
                "payment_status": PaymentStatus.paid if sale and sale > 0 else PaymentStatus.unpaid,
            }
            delivered = _d(r.get("delivery_date"))
            if delivered:
                fields["construction_status"] = ConstructionStatus.completed
                fields["completion_date"] = delivered  # the sheet has no separate completion date
            p = psvc.create_project(db, {k: v for k, v in fields.items() if v is not None}, actor=actor, source=SOURCE)
            if delivered:
                dc = dsvc.create_pending(db, p, delivery_date=delivered, source=SOURCE, requested_by=actor,
                                         notes=f"Delivery date written in the workbook ({month} sheet)")
                dsvc.decide(db, dc, approve=True, actor=actor, note="Historical delivery from the workbook import")
                report["delivered"] += 1
            report["imported"] += 1
            stats["wells"] += 1
            stats["sales"] += sale or 0
            stats["cost"] += cost or 0
    for s in report["by_month"].values():
        s["sales"], s["cost"] = str(s["sales"]), str(s["cost"])
    return report


def _d(v) -> date | None:
    return date.fromisoformat(v) if v else None

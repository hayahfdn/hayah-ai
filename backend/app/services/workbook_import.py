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
           "bang": ("BANG", "Bangladesh", "Bangladesh"), "india": ("IND", "India", "India"), "ind": ("IND", "India", "India"),
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


# ---------------------------------------------------------------------------
# Full workbook (.xlsx): wells, sacrifices and money rows from app.services.workbook_xlsx
# ---------------------------------------------------------------------------
def import_full_workbook(db: Session, data: dict, *, actor: User) -> dict:
    from app.models import FinanceAccount, Sacrifice
    from app.services import finance as fin

    ensure_workbook_defaults(db)
    created: list[str] = []
    rep = {"wells": 0, "delivered": 0, "sacrifices": 0, "transactions": 0, "skipped_existing_wells": [],
           "skipped_existing_sacrifices": [], "contractors_created": created,
           # exactly what this import added, so it can be removed again in one click
           "created": {"wells": [], "sacrifices": [], "transactions": []}}
    con_cache: dict[str, Contractor] = {}

    def con(code):
        if not code:
            return None
        if code not in con_cache:
            m = re.fullmatch(r"([A-Z]+)(\d+)", code)
            con_cache[code] = contractor_for(db, f"{m.group(1).lower()} {m.group(2)}", created) if m else None
        return con_cache[code]

    for w in data["wells"]:
        wid = w.get("well_id")
        if not wid:
            continue
        if psvc.get_by_well_id(db, wid):
            rep["skipped_existing_wells"].append(wid)
            continue
        c = con(w.get("contractor"))
        sale, cost = w.get("sale_amount"), w.get("cost")
        notes = list(w.get("notes") or []) + [f"Imported from the workbook ({w['sheet']} sheet, row {w['row']})."]
        fields = {
            "well_id": wid, "order_date": w.get("order_date"), "customer_name": w.get("customer_name"),
            "well_type": w.get("well_type"), "contractor_id": c.id if c else None, "country": c.country if c else None,
            "sale_amount": sale, "cost": cost, "payment_method": w.get("payment_method"), "extras": w.get("extras"),
            "sales_source": w.get("sales_source"), "received_date": w.get("received_date"), "notes": "\n".join(notes),
            "payment_status": PaymentStatus.paid if sale and sale > 0 else PaymentStatus.unpaid,
        }
        delivered = w.get("delivery_date")
        if delivered:
            fields["construction_status"] = ConstructionStatus.completed
            fields["completion_date"] = delivered
        p = psvc.create_project(db, {k: v for k, v in fields.items() if v is not None}, actor=actor, source=SOURCE)
        if delivered:
            dc = dsvc.create_pending(db, p, delivery_date=delivered, source=SOURCE, requested_by=actor,
                                     notes=f"Delivery date written in the workbook ({w['sheet']} sheet)")
            dsvc.decide(db, dc, approve=True, actor=actor, note="Historical delivery from the workbook import")
            rep["delivered"] += 1
        rep["wells"] += 1
        rep["created"]["wells"].append(wid)

    for s in data["sacrifices"]:
        if db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == s["sacrifice_no"])):
            rep["skipped_existing_sacrifices"].append(s["sacrifice_no"])
            continue
        c = con(s.get("contractor"))
        notes = list(s.get("notes") or []) + [f"Imported from the workbook ({s['sheet']} sheet, row {s['row']})."]
        fields = {k: s.get(k) for k in ("sacrifice_no", "order_date", "donor_name", "received_date", "delivery_date",
                                         "animal_type", "cost", "sale_price", "payment_method", "extras",
                                         "sales_source", "intention")}
        fields |= {"contractor_id": c.id if c else None, "notes": "\n".join(notes)}
        fin.create_sacrifice(db, {k: v for k, v in fields.items() if v is not None}, actor=actor, source=SOURCE)
        rep["sacrifices"] += 1
        rep["created"]["sacrifices"].append(s["sacrifice_no"])

    accounts = {a.code: a for a in db.scalars(select(FinanceAccount))}
    for t in sorted(data["transactions"], key=lambda t: (t["date"], t.get("reference") or "")):
        c = con(t.get("contractor"))
        row = {"date": t["date"], "kind": t["kind"], "direction": t["direction"],
               "account_id": accounts[t["account"]].id if t.get("account") else None,
               "contractor_id": c.id if c else None, "channel": t.get("channel"), "category": t.get("category"),
               "amount": t["amount"], "description": (t.get("description") or "")[:500] or None,
               "reference": (t.get("reference") or "")[:120] or None}
        tx = fin.create_transaction(db, {k: v for k, v in row.items() if v is not None}, actor=actor, source=SOURCE)
        rep["transactions"] += 1
        rep["created"]["transactions"].append(tx.id)
    return rep

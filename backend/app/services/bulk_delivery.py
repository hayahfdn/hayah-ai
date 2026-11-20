"""Mark projects from before this month as Delivered (Hayah, 2026-11-19, item 11).

Two steps, and nothing changes before the second:
1. preview(): counts by month and type (wells / sacrifices), split into "real date" (a delivery
   date was already typed) and "estimated date" (no date: the last day of the order month is
   used and the record is flagged `delivery_estimated`). Records that are left out are listed
   with the reason (no order date, cancelled).
2. apply(): a manager confirms the exact totals they saw. The server recomputes, refuses if the
   numbers moved, and then changes only delivery_status, delivery_date (when it was empty) and the
   estimated flag. Numbers, names and prices are never touched. Every record's before/after is kept
   in one `bulk_changes` row, so undo() puts everything back exactly.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BulkChange, ConstructionStatus, DeliveryStatus, Project, Sacrifice, User, utcnow
from app.services.audit import audit
from app.services.projects import add_event

KIND = "mark_old_delivered"


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _cutoff(today: date | None = None) -> date:
    t = today or date.today()
    return date(t.year, t.month, 1)


def _candidates(db: Session, today: date | None = None):
    cut = _cutoff(today)
    out, skipped = [], defaultdict(int)
    wells = db.scalars(select(Project).where(Project.merged_into_id.is_(None), Project.is_sample.is_(False),
                                             Project.delivery_status != DeliveryStatus.delivered))
    for p in wells:
        if p.construction_status == ConstructionStatus.cancelled:
            skipped["well_cancelled"] += 1
        elif not p.order_date:
            skipped["well_no_order_date"] += 1
        elif p.order_date < cut:
            out.append(("well", p))
    sacs = db.scalars(select(Sacrifice).where(Sacrifice.is_sample.is_(False),
                                              Sacrifice.delivery_status != DeliveryStatus.delivered))
    for s in sacs:
        if not s.order_date:
            skipped["sacrifice_no_order_date"] += 1
        elif s.order_date < cut:
            out.append(("sacrifice", s))
    return out, dict(skipped)


def preview(db: Session, today: date | None = None) -> dict:
    rows, skipped = _candidates(db, today)
    months: dict[str, dict] = {}
    totals = {"wells": 0, "sacrifices": 0, "real_date": 0, "estimated_date": 0}
    for kind, o in rows:
        m = o.order_date.strftime("%Y-%m")
        r = months.setdefault(m, {"month": m, "wells": 0, "sacrifices": 0, "real_date": 0, "estimated_date": 0})
        key = "wells" if kind == "well" else "sacrifices"
        est = "real_date" if o.delivery_date else "estimated_date"
        r[key] += 1; r[est] += 1; totals[key] += 1; totals[est] += 1
    return {"before": _cutoff(today).isoformat(), "months": sorted(months.values(), key=lambda r: r["month"], reverse=True),
            "totals": totals, "skipped": skipped,
            "rule": "Real delivery dates are kept. Without one, the last day of the order month is used and marked as estimated."}


def apply(db: Session, user: User, expected: dict, today: date | None = None) -> dict:
    now = preview(db, today)
    want = {k: int(expected.get(k, -1)) for k in ("wells", "sacrifices")}
    if want != {k: now["totals"][k] for k in want}:
        raise HTTPException(409, "The numbers changed since the preview. Open the preview again and check them.")
    rows, _ = _candidates(db, today)
    if not rows:
        raise HTTPException(422, "Nothing to mark.")
    items = []
    for kind, o in rows:
        before = {"delivery_status": o.delivery_status.value, "delivery_date": o.delivery_date.isoformat() if o.delivery_date else None,
                  "delivery_estimated": bool(o.delivery_estimated)}
        est = o.delivery_date is None
        o.delivery_status = DeliveryStatus.delivered
        if est:
            o.delivery_date, o.delivery_estimated = _month_end(o.order_date), True
        if kind == "well":
            add_event(db, o, "delivery.bulk_marked", source="dashboard", actor=user,
                      summary=f"Marked delivered in bulk ({'estimated date' if est else 'date kept'}: {o.delivery_date.isoformat()})")
        items.append({"kind": kind, "id": o.id, "no": o.well_id if kind == "well" else o.sacrifice_no, "before": before,
                      "after": {"delivery_status": "delivered", "delivery_date": o.delivery_date.isoformat(), "delivery_estimated": est}})
    batch = BulkChange(kind=KIND, summary=now, items=items, created_by=user.id)
    db.add(batch); db.flush()
    audit(db, "bulk.mark_old_delivered", "bulk_change", batch.id, actor=user, after={"totals": now["totals"], "count": len(items)})
    db.commit()
    return {"batch_id": batch.id, "changed": len(items), "totals": now["totals"]}


def undo(db: Session, user: User, batch_id: int) -> dict:
    b = db.get(BulkChange, batch_id, with_for_update=True)
    if not b or b.kind != KIND:
        raise HTTPException(404, "No such bulk change.")
    if b.undone_at:
        raise HTTPException(409, "This bulk change was already undone.")
    restored, skipped = 0, []
    for it in b.items:
        o = db.get(Project if it["kind"] == "well" else Sacrifice, it["id"], with_for_update=True)
        cur = {"delivery_status": o.delivery_status.value if o else None,
               "delivery_date": o.delivery_date.isoformat() if o and o.delivery_date else None,
               "delivery_estimated": bool(o.delivery_estimated) if o else None}
        if not o or cur != it["after"]:  # changed by someone since: leave it, report it
            skipped.append(it["no"]); continue
        bf = it["before"]
        o.delivery_status = DeliveryStatus(bf["delivery_status"])
        o.delivery_date = date.fromisoformat(bf["delivery_date"]) if bf["delivery_date"] else None
        o.delivery_estimated = bf["delivery_estimated"]
        if it["kind"] == "well":
            add_event(db, o, "delivery.bulk_undone", source="dashboard", actor=user, summary="Bulk 'delivered' undone")
        restored += 1
    b.undone_at, b.undone_by = utcnow(), user.id
    audit(db, "bulk.mark_old_delivered.undo", "bulk_change", b.id, actor=user, after={"restored": restored, "skipped": skipped})
    db.commit()
    return {"restored": restored, "skipped_changed_since": skipped}


def history(db: Session) -> list[dict]:
    rows = db.scalars(select(BulkChange).where(BulkChange.kind == KIND).order_by(BulkChange.id.desc()).limit(20))
    return [{"id": b.id, "created_at": b.created_at, "count": len(b.items), "totals": (b.summary or {}).get("totals"),
             "undone_at": b.undone_at} for b in rows]

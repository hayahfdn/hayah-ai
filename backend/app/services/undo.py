"""Undo recent changes, and remove everything a workbook import added.

Undo works from the audit log: it puts back the "before" values of one change,
through the normal audited update path, so the undo itself is recorded too.
It refuses when the same fields were changed again later (undo that first).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog, DeliveryConfirmation, InboundMessage, MaintenanceRecord, MediaAsset, Project,
    ProjectEvent, ReviewCase, Role, Sacrifice, Transaction, User,
)
from app.services import finance as fin, projects as psvc
from app.services.audit import audit, jsonable, snapshot

UNDOABLE = {"project.update", "sacrifice.update", "transaction.update", "transaction.create"}
SKIP = {"version", "updated_at", "created_at", "id"}
MANAGER_ROLES = {Role.super_admin, Role.operations_manager}
LABELS = {"project.update": "Well edited", "sacrifice.update": "Sacrifice edited",
          "transaction.update": "Money row edited", "transaction.create": "Money row added"}


def _restore_types(model, values: dict) -> dict:
    """The audit log stores JSON; turn values back into dates, decimals and enums."""
    import enum
    from datetime import date, datetime
    from decimal import Decimal
    from sqlalchemy import inspect as sa_inspect

    cols = {c.key: c for c in sa_inspect(model).columns}
    out = {}
    for k, v in values.items():
        col = cols.get(k)
        if v is None or col is None:
            out[k] = v
            continue
        try:
            py = col.type.python_type
        except NotImplementedError:
            out[k] = v
            continue
        if isinstance(py, type) and issubclass(py, enum.Enum):
            out[k] = py(v)
        elif py is Decimal:
            out[k] = Decimal(str(v))
        elif py is datetime:
            out[k] = datetime.fromisoformat(v)
        elif py is date:
            out[k] = date.fromisoformat(v)
        else:
            out[k] = v
    return out


def _fields(row: AuditLog) -> dict:
    return {k: v for k, v in (row.after or {}).items() if k not in SKIP}


def recent(db: Session, user: User, *, mine_only: bool, limit: int = 50) -> list[dict]:
    q = select(AuditLog).where(AuditLog.action.in_(UNDOABLE)).order_by(AuditLog.id.desc()).limit(limit)
    if mine_only or user.role not in MANAGER_ROLES:
        q = q.where(AuditLog.actor_user_id == user.id)
    if user.role not in MANAGER_ROLES:  # non-managers only ever see well edits
        q = q.where(AuditLog.action == "project.update")
    undone = set(db.scalars(select(AuditLog.entity_id).where(AuditLog.action == "undo")))
    out = []
    for r in db.scalars(q):
        changed = sorted(_fields(r)) if r.action != "transaction.create" else []
        if user.role not in MANAGER_ROLES and "cost" in changed:
            continue
        out.append({"id": r.id, "at": r.at, "action": r.action, "label": LABELS[r.action], "entity_type": r.entity_type,
                    "entity_id": r.entity_id, "by": r.actor_label, "fields": changed,
                    "before": {k: (r.before or {}).get(k) for k in changed}, "after": {k: (r.after or {}).get(k) for k in changed},
                    "undone": str(r.id) in undone})
    return out


def undo(db: Session, audit_id: int, user: User) -> dict:
    row = db.get(AuditLog, audit_id)
    if not row or row.action not in UNDOABLE:
        raise HTTPException(404, "This change can't be undone here")
    manager = user.role in MANAGER_ROLES
    if not manager and (row.actor_user_id != user.id or row.action != "project.update"):
        raise HTTPException(403, "You can only undo your own well edits")
    if db.scalar(select(AuditLog.id).where(AuditLog.action == "undo", AuditLog.entity_id == str(row.id))):
        raise HTTPException(409, "This change was already undone")

    if row.action == "transaction.create":
        t = db.get(Transaction, int(row.entity_id))
        if not t or t.voided:
            raise HTTPException(409, "This money row is already voided")
        fin.void_transaction(db, t, f"Undo of change #{row.id}", actor=user)
        what = f"Money row {t.id} voided"
    else:
        fields = _fields(row)
        before = {k: (row.before or {}).get(k) for k in fields}
        if row.action == "project.update":
            obj = psvc.require_project(db, int(row.entity_id), for_update=True)
        elif row.action == "sacrifice.update":
            obj = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == int(row.entity_id)))
        else:
            obj = db.get(Transaction, int(row.entity_id))
        if obj is None:
            raise HTTPException(404, "The record no longer exists")
        now = snapshot(obj)
        later = [k for k in fields if jsonable(now.get(k)) != fields[k]]
        if later:
            raise HTTPException(409, f"{', '.join(later)} changed again after this edit. Undo the newer change first.")
        changes = _restore_types(type(obj), before)
        if row.action == "project.update":
            psvc.update_project(db, obj, changes, actor=user, source="undo", allow_delivery_fields=manager)
        elif row.action == "sacrifice.update":
            fin.update_sacrifice(db, obj, changes, actor=user)
        else:
            fin.update_transaction(db, obj, changes, actor=user)
        what = f"{LABELS[row.action]} ({row.entity_id}): {', '.join(fields)} put back"
    audit(db, "undo", "audit", row.id, actor=user, after={"undid": row.action, "entity": row.entity_id, "summary": what})
    return {"undone": row.id, "summary": what}


# ---------------------------------------------------------------------------
# Remove a workbook import
# ---------------------------------------------------------------------------
def _created_by_import(db: Session, w: AuditLog) -> dict:
    """What one workbook import added. Newer imports list it; older ones are found from the audit log."""
    c = (w.after or {}).get("created")
    if c:
        return {"wells": set(c["wells"]), "sacrifices": set(c["sacrifices"]), "transactions": set(c["transactions"])}
    q = select(AuditLog).where(AuditLog.actor_user_id == w.actor_user_id, AuditLog.id < w.id,
                               AuditLog.at >= w.at - timedelta(minutes=15),
                               AuditLog.action.in_(["project.create", "sacrifice.create", "transaction.create"]))
    rows = list(db.scalars(q))
    wells = {int(r.entity_id) for r in rows if r.action == "project.create"}
    # A well counts only if its timeline says it came from the workbook.
    if wells:
        wells = set(db.scalars(select(Project.well_id).join(ProjectEvent, ProjectEvent.project_id == Project.id).where(
            Project.well_id.in_(wells), ProjectEvent.event_type == "project_created", ProjectEvent.source == "workbook_import")))
    return {"wells": wells,
            "sacrifices": {int(r.entity_id) for r in rows if r.action == "sacrifice.create"},
            "transactions": {int(r.entity_id) for r in rows if r.action == "transaction.create"}}


def imports_list(db: Session) -> list[dict]:
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "workbook.import").order_by(AuditLog.id.desc()))
    removed = set(db.scalars(select(AuditLog.entity_id).where(AuditLog.action == "workbook.import_removed")))
    return [{"id": r.id, "at": r.at, "file": r.entity_id, "by": r.actor_label, "wells": (r.after or {}).get("wells"),
             "sacrifices": (r.after or {}).get("sacrifices"), "transactions": (r.after or {}).get("transactions"),
             "removed": str(r.id) in removed} for r in rows]


def remove_import(db: Session, import_audit_id: int, user: User, *, apply: bool) -> dict:
    w = db.get(AuditLog, import_audit_id)
    if not w or w.action != "workbook.import":
        raise HTTPException(404, "No such workbook import")
    if db.scalar(select(AuditLog.id).where(AuditLog.action == "workbook.import_removed", AuditLog.entity_id == str(w.id))):
        raise HTTPException(409, "This import was already removed")
    found = _created_by_import(db, w)

    projects = list(db.scalars(select(Project).where(Project.well_id.in_(found["wells"] or {-1}))))
    sacrifices = list(db.scalars(select(Sacrifice).where(Sacrifice.sacrifice_no.in_(found["sacrifices"] or {-1}))))
    # Wells and sacrifices that now carry work added in the system (plaque, certificate, contract, video,
    # tasks, maintenance, photos, messages, merges, hand edits...) are kept, so nothing is lost or left dangling.
    from app.services.workbook_replace import attached_work
    w_work, s_work = attached_work(db, projects, sacrifices)
    keep = [p for p in projects if p.id in w_work]
    drop = [p for p in projects if p.id not in w_work]
    sac_kept = sorted(s.sacrifice_no for s in sacrifices if s.id in s_work)
    sacrifices = [s for s in sacrifices if s.id not in s_work]
    txs = list(db.scalars(select(Transaction).where(Transaction.id.in_(found["transactions"] or {-1}))))
    from app.models import WiseTransaction
    wise = set(db.scalars(select(WiseTransaction.transaction_id).where(WiseTransaction.transaction_id.in_([t.id for t in txs] or [-1]))))
    txs = [t for t in txs if t.id not in wise]  # a row matched to a Wise payment stays
    report = {"import": w.id, "file": w.entity_id, "wells": len(drop), "sacrifices": len(sacrifices),
              "transactions": len(txs), "wells_kept": sorted(p.well_id for p in keep), "sacrifices_kept": sac_kept,
              "well_ids": sorted(p.well_id for p in drop)}
    if not apply:
        return {**report, "applied": False}

    # Full copy of everything removed goes into the audit log, so nothing is lost for good.
    audit(db, "workbook.import_removed", "audit", w.id, actor=user,
          before={"wells": [snapshot(p) for p in drop], "sacrifices": [snapshot(s) for s in sacrifices],
                  "transactions": [snapshot(t) for t in txs]},
          after={k: v for k, v in report.items() if k != "well_ids"})
    drop_ids = [p.id for p in drop]
    if drop_ids:
        db.execute(delete(DeliveryConfirmation).where(DeliveryConfirmation.project_id.in_(drop_ids)))
        db.execute(delete(ProjectEvent).where(ProjectEvent.project_id.in_(drop_ids)))
        db.execute(delete(Project).where(Project.id.in_(drop_ids)).execution_options(synchronize_session=False))
    if sacrifices:
        db.execute(delete(Sacrifice).where(Sacrifice.id.in_([s.id for s in sacrifices])))
    if txs:
        db.execute(delete(Transaction).where(Transaction.id.in_([t.id for t in txs])).execution_options(synchronize_session=False))
    db.expire_all()
    psvc.queue_sheet_sync(db)
    return {**report, "applied": True}

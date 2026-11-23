"""Replace everything earlier workbook imports loaded with a new workbook (Hayah, 23 Nov 2026).

Hayah keeps the Excel workbook up to date and wants to load a newer copy over the old one.
The safest way to do that without losing work done in the system since the first import:

  * Only rows that came from a workbook import are touched. Wells and sacrifices typed in by hand,
    Shopify and WhatsApp orders, and sample rows are never changed.
  * A well or sacrifice whose number is in the new workbook is UPDATED IN PLACE: the workbook's
    columns take the new values (an empty cell never wipes a value), and everything that hangs on
    it stays linked: plaque, certificate, contract and invoice number, final video, team tasks,
    WhatsApp chat, Shopify link, photos and its history. Notes typed in the system are kept.
  * A well or sacrifice that is no longer in the new workbook is deleted, unless work was added to
    it in the system (any of the above, a hand edit, a delivery confirmed from WhatsApp...). Those are
    kept and listed, so nothing that took someone's time disappears.
  * All money rows from earlier imports are replaced by the money rows of the new workbook. A row
    that was matched to a Wise payment moves its match to the identical new row; if the new workbook
    has no identical row, the old row is kept and listed.
  * New numbers are added like a normal import.

Before anything changes, a database backup is written (app/services/backup.py), and a full copy
of every deleted row goes into the audit log.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (AuditLog, ConstructionStatus, Contractor, DeliveryConfirmation, DeliveryStatus, PaymentStatus,
                        Project, ProjectEvent, Sacrifice, Transaction, User, WiseTransaction)
from app.services import delivery as dsvc, finance as fin, projects as psvc
from app.services.audit import audit, jsonable, snapshot
from app.services.workbook_import import SOURCE, contractor_for, import_full_workbook

MARK = "Imported from the workbook ("
WELL_FIELDS = ("order_date", "customer_name", "well_type", "contractor_id", "country", "sale_amount", "cost",
               "payment_method", "extras", "sales_source", "received_date", "payment_status")
SAC_FIELDS = ("order_date", "donor_name", "received_date", "delivery_date", "animal_type", "cost", "sale_price",
              "payment_method", "extras", "sales_source", "intention", "contractor_id")
# What the system calls the tables that can hang on a well or a sacrifice (anything else shows its table name).
LABELS = {"plaques": "plaque", "final_videos": "final video", "media_assets": "photos / files",
          "maintenance_records": "maintenance", "wa_conversations": "WhatsApp chat", "inbound_messages": "messages",
          "team_steps": "team tasks", "team_assignments": "team tasks", "shopify_order_items": "Shopify order",
          "sacrifices": "sheep add-on", "review_cases": "review", "projects": "merged well"}
OWN_TABLES = {"project_events", "delivery_confirmations"}  # checked separately: the import writes some itself


# ---------------------------------------------------------------- what came from imports
def active_imports(db: Session) -> list[AuditLog]:
    removed = set(db.scalars(select(AuditLog.entity_id).where(AuditLog.action == "workbook.import_removed")))
    return [w for w in db.scalars(select(AuditLog).where(AuditLog.action == "workbook.import").order_by(AuditLog.id))
            if str(w.id) not in removed]


def imported_rows(db: Session) -> dict:
    """Wells, sacrifices and money rows that are in the system because of a workbook import.
    Found from records that survive renumbering: a well's own 'created' timeline event, a sacrifice's
    latest create record, and the money row ids the imports listed."""
    from app.services.undo import _created_by_import

    wells = list(db.scalars(select(Project).join(ProjectEvent, ProjectEvent.project_id == Project.id).where(
        ProjectEvent.event_type == "project_created", ProjectEvent.source == SOURCE, Project.is_sample.is_(False))))

    latest = {}
    for a in db.scalars(select(AuditLog).where(AuditLog.action == "sacrifice.create").order_by(AuditLog.id)):
        latest[a.entity_id] = a  # a number removed and typed in again by hand counts as hand-typed
    nos = [int(k) for k, a in latest.items() if MARK in str((a.after or {}).get("notes") or "")]
    sacs = list(db.scalars(select(Sacrifice).where(Sacrifice.sacrifice_no.in_(nos or [-1]), Sacrifice.is_sample.is_(False))))

    tx_ids: set[int] = set()
    imports = active_imports(db)
    for w in imports:
        tx_ids |= _created_by_import(db, w)["transactions"]
    txs = list(db.scalars(select(Transaction).where(Transaction.id.in_(tx_ids or {-1}), Transaction.is_sample.is_(False))))
    return {"wells": wells, "sacrifices": sacs, "transactions": txs, "imports": imports}


# ---------------------------------------------------------------- work added in the system
def _fk_columns(target: str):
    for t in Base.metadata.sorted_tables:
        if t.name in OWN_TABLES:
            continue
        for col in t.columns:
            for fk in col.foreign_keys:
                if fk.target_fullname == target:
                    yield t, col


def attached_work(db: Session, wells: list[Project], sacs: list[Sacrifice]) -> tuple[dict, dict]:
    """{record id: [what was added to it in the system]} for wells and for sacrifices."""
    w_found: dict[int, set[str]] = defaultdict(set)
    s_found: dict[int, set[str]] = defaultdict(set)
    pids, sids = [p.id for p in wells], [s.id for s in sacs]
    for target, ids, found in (("projects.id", pids, w_found), ("sacrifices.id", sids, s_found)):
        if not ids:
            continue
        for t, col in _fk_columns(target):
            for v in db.execute(select(col).where(col.in_(ids)).distinct()).scalars():
                found[v].add(LABELS.get(t.name, t.name.replace("_", " ")))
    if pids:
        # The import writes "created" and its own delivery; anything else on the timeline was done in the system.
        for pid, etype in db.execute(select(ProjectEvent.project_id, ProjectEvent.event_type).where(
                ProjectEvent.project_id.in_(pids), ProjectEvent.source != SOURCE,
                ProjectEvent.event_type != "delivery_confirmed")):
            w_found[pid].add({"certificate_saved": "certificate", "certificate_sent": "certificate"}.get(etype, "work in the system"))
        for pid in db.scalars(select(DeliveryConfirmation.project_id).where(
                DeliveryConfirmation.project_id.in_(pids), DeliveryConfirmation.source != SOURCE)):
            w_found[pid].add("delivery confirmation")
    by_well = {str(p.well_id): p.id for p in wells}
    by_no = {str(s.sacrifice_no): s.id for s in sacs}
    by_pid, by_sid = {str(i): i for i in pids}, {str(i): i for i in sids}
    for a in db.execute(select(AuditLog.action, AuditLog.entity_type, AuditLog.entity_id).where(AuditLog.action.in_(
            ["contract.saved", "plaque.saved", "sacrifice.update"]))):
        if a.action == "contract.saved" and a.entity_type == "contract_well" and a.entity_id in by_pid:
            w_found[by_pid[a.entity_id]].add("contract / invoice")
        elif a.action == "contract.saved" and a.entity_type == "contract_sacrifice" and a.entity_id in by_sid:
            s_found[by_sid[a.entity_id]].add("contract / invoice")
        elif a.action == "plaque.saved" and a.entity_type == "project" and a.entity_id in by_well:
            w_found[by_well[a.entity_id]].add("plaque")
        elif a.action == "plaque.saved" and a.entity_type == "sacrifice" and a.entity_id in by_no:
            s_found[by_no[a.entity_id]].add("plaque")
    # sacrifice edits made by a person (replace runs write theirs with this label)
    for eid in db.scalars(select(AuditLog.entity_id).where(AuditLog.action == "sacrifice.update",
                                                          AuditLog.actor_label.is_distinct_from(REPLACE_LABEL))):
        if eid in by_no:
            s_found[by_no[eid]].add("edited in the system")
    return ({k: sorted(v) for k, v in w_found.items()}, {k: sorted(v) for k, v in s_found.items()})


REPLACE_LABEL = "workbook replace"


# ---------------------------------------------------------------- helpers
def _created_notes(db: Session, action: str, entity_id) -> set[str]:
    a = db.scalar(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(entity_id))
                  .order_by(AuditLog.id.desc()).limit(1))
    return set(str((a.after or {}).get("notes") or "").splitlines()) if a else set()


def _merge_notes(current: str | None, old_import: set[str], new_lines: list[str]) -> str:
    """The new workbook's notes, plus any line someone typed in the system."""
    hand = [ln for ln in (current or "").splitlines()
            if ln.strip() and ln not in old_import and not ln.startswith(MARK) and ln not in new_lines]
    return "\n".join(new_lines + hand)


def _same(a, b) -> bool:
    if isinstance(a, (Decimal, int, float)) and isinstance(b, (Decimal, int, float)) and not isinstance(a, bool):
        return Decimal(str(a)) == Decimal(str(b))
    return jsonable(a) == jsonable(b)


def _contractors(db: Session, created: list[str]):
    import re
    cache: dict[str, Contractor | None] = {}

    def con(code):
        if not code:
            return None
        if code not in cache:
            m = re.fullmatch(r"([A-Z]+)(\d+)", code)
            cache[code] = contractor_for(db, f"{m.group(1).lower()} {m.group(2)}", created) if m else None
        return cache[code]
    return con


def _tx_key(t) -> tuple:
    g = (lambda k: getattr(t, k)) if not isinstance(t, dict) else t.get
    return (jsonable(g("date")), jsonable(g("kind")), g("direction"), g("account_id"), jsonable(Decimal(str(g("amount")))),
            g("reference") or None)


# ---------------------------------------------------------------- the replace
def replace_all(db: Session, data: dict, *, actor: User, file: str) -> dict:
    """Do the whole replace in the caller's transaction. The caller commits (apply) or rolls back (preview)."""
    fin.ensure_workbook_defaults(db)
    found = imported_rows(db)
    wells, sacs, txs = found["wells"], found["sacrifices"], found["transactions"]
    w_work, s_work = attached_work(db, wells, sacs)
    created_con: list[str] = []
    con = _contractors(db, created_con)

    new_wells = {w["well_id"]: w for w in data["wells"] if w.get("well_id")}
    new_sacs = {s["sacrifice_no"]: s for s in data["sacrifices"]}
    rep = {"file": file, "previous_imports": [{"id": w.id, "file": w.entity_id, "at": w.at} for w in found["imports"]],
           "before": {"wells": len(wells), "sacrifices": len(sacs), "transactions": len(txs)},
           "wells_updated": 0, "sacrifices_updated": 0, "wells_deleted": [], "sacrifices_deleted": [],
           "wells_kept": [], "sacrifices_kept": [], "transactions_deleted": 0, "transactions_kept": [],
           "wise_relinked": 0, "hand_edits_overwritten": [], "deliveries_changed": [], "renumbered_check": []}

    # --- wells: update in place, or delete / keep
    drop_w, upd_w = [], []
    for p in sorted(wells, key=lambda p: p.well_id):
        w = new_wells.get(p.well_id)
        if w is None:
            if p.id in w_work:
                rep["wells_kept"].append({"number": p.well_id, "why": w_work[p.id]})
            else:
                drop_w.append(p)
            continue
        upd_w.append(p.well_id)
        c = con(w.get("contractor"))
        sale = w.get("sale_amount")
        new = {"order_date": w.get("order_date"), "customer_name": w.get("customer_name"), "well_type": w.get("well_type"),
               "contractor_id": c.id if c else None, "country": c.country if c else None, "sale_amount": sale,
               "cost": w.get("cost"), "payment_method": w.get("payment_method"), "extras": w.get("extras"),
               "sales_source": w.get("sales_source"), "received_date": w.get("received_date"),
               "payment_status": (PaymentStatus.paid if sale and sale > 0 else PaymentStatus.unpaid) if sale is not None else None}
        new = {k: v for k, v in new.items() if v is not None}  # an empty cell never wipes a value
        orig = _orig_snapshot(db, "project.create", p.well_id)
        edited = [k for k in new if orig is not None and k in orig and not _same(getattr(p, k), orig[k])
                  and not _same(getattr(p, k), new[k])]
        if edited:
            rep["hand_edits_overwritten"].append({"number": p.well_id, "fields": edited})
        lines = list(w.get("notes") or []) + [f"{MARK}{w['sheet']} sheet, row {w['row']})."]
        new["notes"] = _merge_notes(p.notes, _created_notes(db, "project.create", p.well_id), lines)
        changes = {k: v for k, v in new.items() if not _same(getattr(p, k), v)}
        if changes:
            psvc.update_project(db, p, changes, actor=actor, source=SOURCE)
        delivered = w.get("delivery_date")
        if delivered and p.delivery_date != delivered:
            rep["deliveries_changed"].append({"number": p.well_id, "from": p.delivery_date, "to": delivered})
            if p.construction_status != ConstructionStatus.completed:
                psvc.update_project(db, p, {"construction_status": ConstructionStatus.completed,
                                            "completion_date": p.completion_date or delivered}, actor=actor, source=SOURCE)
            if p.delivery_status != DeliveryStatus.delivered:
                dc = dsvc.create_pending(db, p, delivery_date=delivered, source=SOURCE, requested_by=actor,
                                         notes=f"Delivery date written in the workbook ({w['sheet']} sheet)")
                dsvc.decide(db, dc, approve=True, actor=actor, note="Historical delivery from the workbook import")
            else:
                psvc.update_project(db, p, {"delivery_date": delivered}, actor=actor, source=SOURCE,
                                    allow_delivery_fields=True)
        rep["wells_updated"] += 1

    # --- sacrifices
    drop_s, upd_s = [], []
    for s in sorted(sacs, key=lambda s: s.sacrifice_no):
        n = new_sacs.get(s.sacrifice_no)
        if n is None:
            if s.id in s_work:
                rep["sacrifices_kept"].append({"number": s.sacrifice_no, "why": s_work[s.id]})
            else:
                drop_s.append(s)
            continue
        upd_s.append(s.sacrifice_no)
        c = con(n.get("contractor"))
        new = {k: n.get(k) for k in SAC_FIELDS if k != "contractor_id"} | {"contractor_id": c.id if c else None}
        new = {k: v for k, v in new.items() if v is not None}
        orig = _orig_snapshot(db, "sacrifice.create", s.sacrifice_no)
        edited = [k for k in new if orig is not None and k in orig and not _same(getattr(s, k), orig[k])
                  and not _same(getattr(s, k), new[k])]
        if edited:
            rep["hand_edits_overwritten"].append({"number": s.sacrifice_no, "fields": edited, "sacrifice": True})
        lines = list(n.get("notes") or []) + [f"{MARK}{n['sheet']} sheet, row {n['row']})."]
        new["notes"] = _merge_notes(s.notes, _created_notes(db, "sacrifice.create", s.sacrifice_no), lines)
        changes = {k: v for k, v in new.items() if not _same(getattr(s, k), v)}
        if changes:
            fin.update_sacrifice(db, s, changes, actor=actor, source=SOURCE)
            db.flush()
            # mark the update as the replace's own, so a later replace does not count it as a hand edit
            last = db.scalar(select(AuditLog).where(AuditLog.action == "sacrifice.update",
                                                    AuditLog.entity_id == str(s.sacrifice_no)).order_by(AuditLog.id.desc()).limit(1))
            if last is not None:
                last.actor_label = REPLACE_LABEL
        rep["sacrifices_updated"] += 1

    # --- renumbered in the system but the new workbook still uses the old number
    for action, label in (("project.renumber", "well_id"), ("sacrifice.renumber", "sacrifice_no")):
        pool = new_wells if action == "project.renumber" else new_sacs
        mine = {p.well_id for p in wells} if action == "project.renumber" else {s.sacrifice_no for s in sacs}
        for a in db.scalars(select(AuditLog).where(AuditLog.action == action)):
            old, now = (a.before or {}).get(label), (a.after or {}).get(label)
            if old in pool and now in mine and now not in pool:
                rep["renumbered_check"].append({"old": old, "now": now, "kind": "well" if label == "well_id" else "sacrifice"})

    # --- money rows
    linked = set(db.scalars(select(WiseTransaction.transaction_id).where(
        WiseTransaction.transaction_id.in_([t.id for t in txs] or [-1]))))
    drop_t = [t for t in txs if t.id not in linked]
    hold_t = [t for t in txs if t.id in linked]

    # --- delete (a full copy goes to the audit log first)
    audit(db, "workbook.replace_deleted", "workbook", file, actor=actor,
          before={"wells": [snapshot(p) for p in drop_w], "sacrifices": [snapshot(s) for s in drop_s],
                  "transactions": [snapshot(t) for t in drop_t]})
    _delete(db, drop_w, drop_s, drop_t)
    rep["wells_deleted"] = [p for p in sorted(x.well_id for x in drop_w)]
    rep["sacrifices_deleted"] = sorted(x.sacrifice_no for x in drop_s)
    rep["transactions_deleted"] = len(drop_t)

    # --- load the rest of the new workbook like a normal import (numbers in use are skipped and reported)
    rest = {**data, "wells": [w for w in data["wells"] if w.get("well_id") not in set(upd_w)],
            "sacrifices": [s for s in data["sacrifices"] if s["sacrifice_no"] not in set(upd_s)]}
    imp = import_full_workbook(db, rest, actor=actor)
    imp["contractors_created"] = sorted(set(imp["contractors_created"]) | set(created_con))

    # --- Wise matches: move to the identical new row, or keep the old row
    new_tx = {}
    for tid in imp["created"]["transactions"]:
        t = db.get(Transaction, tid)
        new_tx.setdefault(_tx_key(t), []).append(t)
    for t in hold_t:
        twins = new_tx.get(_tx_key(t)) or []
        twin = twins.pop(0) if twins else None
        if twin is None:
            rep["transactions_kept"].append({"id": t.id, "date": t.date, "amount": t.amount, "why": "matched to a Wise payment"})
            continue
        wt = db.scalar(select(WiseTransaction).where(WiseTransaction.transaction_id == t.id))
        audit(db, "wise.relinked", "wise_transaction", wt.id, actor=actor, before={"transaction_id": t.id},
              after={"transaction_id": twin.id, "why": "workbook replaced"})
        wt.transaction_id = None
        db.flush()
        wt.transaction_id = twin.id
        db.flush()
        audit(db, "workbook.replace_deleted", "workbook", file, actor=actor, before={"transactions": [snapshot(t)]})
        _delete(db, [], [], [t])
        rep["transactions_deleted"] += 1
        rep["wise_relinked"] += 1

    # This replace becomes the current import: the updated rows count as its own, so it can be removed or replaced later.
    imp["created"]["wells"] += upd_w
    imp["created"]["sacrifices"] += upd_s
    rep["import"] = {k: v for k, v in imp.items() if k != "created"}
    rep["created"] = imp["created"]
    rep["after"] = {"wells": len(imp["created"]["wells"]) + len(rep["wells_kept"]),
                    "sacrifices": len(imp["created"]["sacrifices"]) + len(rep["sacrifices_kept"]),
                    "transactions": len(imp["created"]["transactions"]) + len(rep["transactions_kept"])}
    rep["wells_added"] = imp["wells"]
    rep["sacrifices_added"] = imp["sacrifices"]
    rep["transactions_added"] = imp["transactions"]
    rep["delivered"] = imp["delivered"] + len(rep["deliveries_changed"])
    return rep


def _orig_snapshot(db: Session, action: str, entity_id) -> dict | None:
    a = db.scalar(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(entity_id))
                  .order_by(AuditLog.id.desc()).limit(1))
    if a is None:
        return None
    from app.services.undo import _restore_types
    model = Project if action == "project.create" else Sacrifice
    return _restore_types(model, a.after or {})


def _delete(db: Session, wells: list[Project], sacs: list[Sacrifice], txs: list[Transaction]) -> None:
    pids = [p.id for p in wells]
    if pids:
        db.execute(delete(DeliveryConfirmation).where(DeliveryConfirmation.project_id.in_(pids)))
        db.execute(delete(ProjectEvent).where(ProjectEvent.project_id.in_(pids)))
        db.execute(delete(Project).where(Project.id.in_(pids)).execution_options(synchronize_session=False))
    if sacs:
        db.execute(delete(Sacrifice).where(Sacrifice.id.in_([s.id for s in sacs])).execution_options(synchronize_session=False))
    if txs:
        db.execute(delete(Transaction).where(Transaction.id.in_([t.id for t in txs])).execution_options(synchronize_session=False))
    db.flush()


def finish(db: Session, rep: dict, *, actor: User, backup: dict) -> None:
    """Apply only: record the replace, mark the earlier imports as replaced, and log the new import."""
    summary = {k: v for k, v in rep.items() if k not in ("created", "previous_imports")}
    audit(db, "workbook.replace", "workbook", rep["file"], actor=actor, after={**summary, "backup": backup})
    for w in rep["previous_imports"]:
        audit(db, "workbook.import_removed", "audit", w["id"], actor=actor, after={"replaced_by": rep["file"]})
    audit(db, "workbook.import", "workbook", rep["file"], actor=actor,
          after={**rep["import"], "wells": len(rep["created"]["wells"]), "sacrifices": len(rep["created"]["sacrifices"]),
                 "transactions": len(rep["created"]["transactions"]), "created": rep["created"], "replace": True})
    psvc.queue_sheet_sync(db)


CONFIRM_WORDS = {"REPLACE", "استبدال"}

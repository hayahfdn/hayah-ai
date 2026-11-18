"""PostgreSQL → Google Sheets synchronization.

PostgreSQL is the source of truth. The "Master Projects" tab is two-way aware:
- Rows are keyed by Well ID; missing rows are appended, never duplicated.
- We remember what we last wrote to each row. If a cell in the sheet differs
  from what we wrote, a person edited it: we log a SyncConflict and leave that
  cell alone until a manager keeps the database value or accepts the sheet value.
- Accepted sheet values go through the normal project update path (validated,
  audited, tagged source="sheets"); the next push then matches, so there is no
  update loop.
- Duplicate Well ID rows and rows for unknown Well IDs are reported, not deleted.
The other tabs are read-only reports that are rewritten on every sync.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.sheets import get_sheets_client
from app.models import (
    Contractor, MaintenanceRecord, MediaAsset, Project, ProjectEvent, ReviewCase, ReviewStatus,
    SheetRowState, SyncConflict, SyncRun, User, utcnow,
)
from app.services import projects as project_service
from app.services.jobs import handler
from app.services.settings_store import get_setting, set_setting

MASTER = "Master Projects"


def _s(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "value"):
        return str(v.value)
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    return str(v)


# (header, project attribute or callable, editable-from-sheet)
MASTER_COLUMNS = [
    ("Well ID", "well_id", False),
    ("Order Date", "order_date", True),
    ("Customer Name", "customer_name", True),
    ("Customer Phone", "customer_phone", True),
    ("Country", "country", True),
    ("City", "city", True),
    ("Village", "village", True),
    ("Well Type", "well_type", True),
    ("Sales Source", "sales_source", True),
    ("Contractor", lambda p: p.contractor.code if p.contractor else None, False),
    ("Sale Amount", "sale_amount", True),
    ("Payment Status", "payment_status", True),
    ("Construction Status", "construction_status", True),
    ("Construction Start Date", "construction_start_date", True),
    ("Completion Date", "completion_date", True),
    ("Delivery Status", "delivery_status", False),  # only via approved delivery confirmation
    ("Delivery Date", "delivery_date", False),
    ("Raw Media Folder", "raw_media_folder_url", False),
    ("Final Video Link", "final_video_link", True),
    ("Video Status", "video_status", True),
    ("Maintenance Status", "maintenance_status", False),
    ("Last Maintenance Date", "last_maintenance_date", False),
    ("Next Maintenance Date", "next_maintenance_date", True),
    ("Notes", "notes", True),
    ("Last Updated", lambda p: p.updated_at.strftime("%Y-%m-%d %H:%M UTC") if p.updated_at else None, False),
]
MASTER_HEADER = [c[0] for c in MASTER_COLUMNS]
IGNORE_FOR_CONFLICT = {"Last Updated", "Raw Media Folder"}

REPORT_TABS = {
    "Maintenance Records": ["Maintenance ID", "Well ID", "Date", "Country", "Location", "Problem Type",
                            "Description", "Contractor", "Technician", "Repair Action", "Repair Cost",
                            "Status", "Next Maintenance Date"],
    "Media Library": ["File Name", "Well ID", "Category", "Type", "Size (MB)", "Sender", "Date",
                      "Drive File ID", "Link", "Status"],
    "Contractors": ["Code", "Name", "Country", "Phone", "Active", "Projects", "Completed", "Notes"],
    "Activity Log": ["Time (UTC)", "Well ID", "Event", "Source", "By", "Summary"],
    "Pending Review": ["Case ID", "Type", "Created (UTC)", "Reason", "Well ID", "Details"],
}
ALL_TABS = {MASTER: MASTER_HEADER, **REPORT_TABS}


def project_row(p: Project) -> list[str]:
    return [_s(attr(p) if callable(attr) else getattr(p, attr)) for _, attr, _ in MASTER_COLUMNS]


def row_hash(values: list[str]) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def _pad(row: list[str]) -> list[str]:
    return (list(row) + [""] * len(MASTER_HEADER))[:len(MASTER_HEADER)]


def _open_conflict(db: Session, tab, key, field, kind, db_value, sheet_value) -> bool:
    exists = db.scalar(select(SyncConflict.id).where(
        SyncConflict.tab == tab, SyncConflict.row_key == key, SyncConflict.field == field,
        SyncConflict.kind == kind, SyncConflict.status == "open"))
    if exists:
        return False
    db.add(SyncConflict(tab=tab, row_key=key, field=field, kind=kind, db_value=db_value, sheet_value=sheet_value))
    return True


def sync_master(db: Session, client) -> dict:
    stats = {"appended": 0, "updated": 0, "unchanged": 0, "conflicts_new": 0, "duplicates": 0, "unknown_rows": 0}
    rows = client.read_tab(MASTER)
    if not rows or rows[0][:len(MASTER_HEADER)] != MASTER_HEADER:
        client.update_rows(MASTER, [(1, MASTER_HEADER)])
        rows = [MASTER_HEADER] + rows[1:] if rows else [MASTER_HEADER]

    by_key: dict[str, list[int]] = {}
    for i, r in enumerate(rows[1:], start=2):
        key = (r[0].strip() if r else "")
        if key:
            by_key.setdefault(key, []).append(i)

    projects = list(db.scalars(select(Project).where(Project.merged_into_id.is_(None)).order_by(Project.well_id)).unique())
    known = {str(p.well_id) for p in projects}
    for key, nums in by_key.items():
        if len(nums) > 1:
            stats["duplicates"] += 1
            stats["conflicts_new"] += _open_conflict(db, MASTER, key, "Well ID", "duplicate_row", None,
                                                     f"rows {', '.join(map(str, nums))}")
        if key not in known:
            stats["unknown_rows"] += 1
            stats["conflicts_new"] += _open_conflict(db, MASTER, key, "Well ID", "unknown_row", None,
                                                     f"row {nums[0]}")

    states = {s.row_key: s for s in db.scalars(select(SheetRowState).where(SheetRowState.tab == MASTER))}
    open_fields: dict[str, set[str]] = {}
    for c in db.scalars(select(SyncConflict).where(SyncConflict.tab == MASTER, SyncConflict.status == "open",
                                                   SyncConflict.kind == "manual_edit")):
        open_fields.setdefault(c.row_key, set()).add(c.field)

    updates, appends = [], []
    for p in projects:
        key = str(p.well_id)
        desired = project_row(p)
        state = states.get(key)
        if key not in by_key:
            appends.append(desired)
            final = desired
        else:
            rownum = by_key[key][0]
            current = _pad(rows[rownum - 1])
            pushed = state.pushed_values.get("values") if state else None
            final = list(desired)
            for i, header in enumerate(MASTER_HEADER):
                if header in IGNORE_FOR_CONFLICT:
                    continue
                sheet_v, db_v = current[i], desired[i]
                if sheet_v == db_v:
                    continue
                edited_by_person = (pushed[i] != sheet_v) if pushed else (sheet_v != "")
                if header in open_fields.get(key, set()) or edited_by_person:
                    if _open_conflict(db, MASTER, key, header, "manual_edit", db_v, sheet_v):
                        stats["conflicts_new"] += 1
                    final[i] = sheet_v  # keep the person's value until a manager decides
            if final != current:
                updates.append((rownum, final))
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        # remember what the row now holds (person's values included), so they are not re-flagged
        if state:
            state.pushed_values, state.pushed_hash, state.pushed_at = {"values": final}, row_hash(final), utcnow()
        else:
            db.add(SheetRowState(tab=MASTER, row_key=key, pushed_values={"values": final}, pushed_hash=row_hash(final)))
    client.update_rows(MASTER, updates)
    client.append_rows(MASTER, appends)
    stats["appended"] = len(appends)
    return stats


def report_rows(db: Session) -> dict[str, list[list[str]]]:
    well = dict(db.execute(select(Project.id, Project.well_id)).all())
    out = {t: [h] for t, h in REPORT_TABS.items()}
    for m in db.scalars(select(MaintenanceRecord).order_by(MaintenanceRecord.id)).unique():
        out["Maintenance Records"].append([_s(x) for x in (
            m.maintenance_code, well.get(m.project_id), m.date, m.country, m.location, m.problem_type, m.description,
            m.contractor.code if m.contractor else None, m.technician, m.repair_action, m.repair_cost, m.status,
            m.next_maintenance_date)])
    for a in db.scalars(select(MediaAsset).order_by(MediaAsset.id)):
        out["Media Library"].append([_s(x) for x in (
            a.filename, well.get(a.project_id), a.category, a.mime_type, round(a.size_bytes / 1048576, 2), a.sender,
            (a.captured_at or a.created_at).date(), a.drive_file_id, a.drive_url, a.processing_status)])
    counts = dict(db.execute(select(Project.contractor_id, func.count()).group_by(Project.contractor_id)).all())
    done = dict(db.execute(select(Project.contractor_id, func.count()).where(
        Project.construction_status == "completed").group_by(Project.contractor_id)).all())
    for c in db.scalars(select(Contractor).order_by(Contractor.code)):
        out["Contractors"].append([_s(x) for x in (c.code, c.name, c.country, c.phone, "yes" if c.is_active else "no",
                                                   counts.get(c.id, 0), done.get(c.id, 0), c.notes)])
    for e in db.scalars(select(ProjectEvent).order_by(ProjectEvent.created_at.desc()).limit(1000)):
        out["Activity Log"].append([_s(x) for x in (e.created_at.strftime("%Y-%m-%d %H:%M"), well.get(e.project_id),
                                                    e.event_type, e.source, e.actor_label, e.summary)])
    for r in db.scalars(select(ReviewCase).where(ReviewCase.status == ReviewStatus.pending).order_by(ReviewCase.id)):
        out["Pending Review"].append([_s(x) for x in (r.id, r.kind, r.created_at.strftime("%Y-%m-%d %H:%M"), r.reason,
                                                      well.get(r.project_id) if r.project_id else r.proposed.get("well_id"),
                                                      json.dumps(r.proposed, ensure_ascii=False)[:500])])
    return out


def run_sync(db: Session, trigger: str = "manual") -> SyncRun:
    run = SyncRun(target="sheets", trigger=trigger)
    db.add(run)
    db.commit()
    client = get_sheets_client()
    try:
        sid = client.ensure_spreadsheet(get_settings().sheets_spreadsheet_title, ALL_TABS)
        meta = get_setting(db, "sheets") or {}
        if meta.get("spreadsheet_id") != sid:
            set_setting(db, "sheets", {"spreadsheet_id": sid, "url": client.spreadsheet_url()})
        stats = sync_master(db, client)
        for tab, rows in report_rows(db).items():
            client.replace_tab(tab, rows)
        # this run covers every change queued before it started
        from sqlalchemy import update
        from app.models import Job, JobStatus
        db.execute(update(Job).where(Job.kind == "sheets_sync", Job.status.in_([JobStatus.queued, JobStatus.retrying]),
                                     Job.created_at <= run.started_at)
                   .values(status=JobStatus.succeeded, finished_at=utcnow(), last_error="covered by sync run"))
        run.stats, run.status = stats, "succeeded"
        run.finished_at = utcnow()
        db.commit()
        return run
    except Exception as exc:
        db.rollback()
        run = db.get(SyncRun, run.id)
        run.status, run.error, run.finished_at = "failed", f"{type(exc).__name__}: {exc}"[:2000], utcnow()
        db.commit()
        raise


@handler("sheets_sync")
def _job(db: Session, payload: dict):
    run_sync(db, trigger=payload.get("trigger", "change"))


def status(db: Session) -> dict:
    last = db.scalar(select(SyncRun).where(SyncRun.target == "sheets").order_by(SyncRun.id.desc()).limit(1))
    last_ok = db.scalar(select(SyncRun).where(SyncRun.target == "sheets", SyncRun.status == "succeeded")
                        .order_by(SyncRun.id.desc()).limit(1))
    from app.models import Job, JobStatus
    pending_jobs = db.scalar(select(func.count()).select_from(Job).where(
        Job.kind == "sheets_sync", Job.status.in_([JobStatus.queued, JobStatus.retrying, JobStatus.running])))
    failed_jobs = db.scalar(select(func.count()).select_from(Job).where(Job.kind == "sheets_sync", Job.status == JobStatus.failed))
    changed_since = 0
    if last_ok:
        changed_since = db.scalar(select(func.count()).select_from(Project).where(Project.updated_at > last_ok.started_at))
    else:
        changed_since = db.scalar(select(func.count()).select_from(Project))
    conflicts = db.scalar(select(func.count()).select_from(SyncConflict).where(SyncConflict.status == "open"))
    if last and last.status == "failed":
        state = "error"
    elif conflicts:
        state = "conflicts"
    elif pending_jobs or changed_since:
        state = "pending"
    else:
        state = "synced"
    meta = get_setting(db, "sheets") or {}
    return {"state": state, "backend": get_settings().sheets_backend, "spreadsheet_url": meta.get("url"),
            "last_run": {"id": last.id, "status": last.status, "started_at": last.started_at, "finished_at": last.finished_at,
                         "stats": last.stats, "error": last.error} if last else None,
            "last_success_at": last_ok.finished_at if last_ok else None,
            "pending_jobs": pending_jobs, "failed_jobs": failed_jobs, "changed_since_last_sync": changed_since,
            "open_conflicts": conflicts}


def _parse(field: str, raw: str):
    raw = raw.strip()
    if raw == "":
        return None
    if field.endswith("_date"):
        return date.fromisoformat(raw)
    if field == "sale_amount":
        try:
            return Decimal(raw.replace(",", ""))
        except InvalidOperation:
            raise HTTPException(422, f"'{raw}' is not a number")
    return raw


def resolve_conflict(db: Session, conflict: SyncConflict, keep: str, actor: User) -> SyncConflict:
    if conflict.status != "open":
        raise HTTPException(409, "Conflict already resolved")
    if keep == "sheet":
        if conflict.kind != "manual_edit":
            raise HTTPException(422, "Only cell edits can be accepted from the sheet")
        col = next((c for c in MASTER_COLUMNS if c[0] == conflict.field), None)
        if not col or not col[2] or callable(col[1]):
            raise HTTPException(422, f"'{conflict.field}' can only be changed in the dashboard")
        project = project_service.require_project(db, int(conflict.row_key))
        try:
            value = _parse(col[1], conflict.sheet_value or "")
        except ValueError:
            raise HTTPException(422, f"'{conflict.sheet_value}' is not a valid value for {conflict.field}")
        project_service.update_project(db, project, {col[1]: value}, actor=actor, source="sheets")
    conflict.status = "accepted_sheet" if keep == "sheet" else "kept_db"
    conflict.resolved_by_id, conflict.resolved_at = actor.id, utcnow()
    from app.services.audit import audit
    audit(db, f"sync_conflict.{conflict.status}", "sync_conflict", conflict.id, actor=actor,
          after={"well_id": conflict.row_key, "field": conflict.field})
    project_service.queue_sheet_sync(db)
    return conflict

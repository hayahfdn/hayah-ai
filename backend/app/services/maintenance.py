from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Counter, MaintenanceRecord, MaintenanceStatus, Project, User, utcnow
from app.services.audit import audit, snapshot
from app.services.projects import add_event, queue_sheet_sync


def next_code(db: Session) -> str:
    c = db.scalar(select(Counter).where(Counter.name == "maintenance").with_for_update())
    if not c:
        c = Counter(name="maintenance", value=0)
        db.add(c)
        db.flush()
    c.value += 1
    return f"MNT-{c.value:06d}"


def _refresh_project(db: Session, project: Project):
    recs = list(db.scalars(select(MaintenanceRecord).where(MaintenanceRecord.project_id == project.id)))
    if not recs:
        return
    open_states = {MaintenanceStatus.open, MaintenanceStatus.in_progress}
    project.maintenance_status = (MaintenanceStatus.open if any(r.status in open_states for r in recs)
                                  else MaintenanceStatus.resolved)
    project.last_maintenance_date = max(r.date for r in recs)
    upcoming = [r.next_maintenance_date for r in recs if r.next_maintenance_date]
    if upcoming:
        project.next_maintenance_date = max(upcoming)
    project.updated_at = utcnow()


def create_record(db: Session, project: Project, data: dict, *, actor: User | None, source: str = "dashboard",
                  inbound_message_id: int | None = None) -> MaintenanceRecord:
    rec = MaintenanceRecord(maintenance_code=next_code(db), project_id=project.id, source=source,
                            inbound_message_id=inbound_message_id, created_by_id=actor.id if actor else None,
                            country=data.pop("country", None) or project.country, **data)
    db.add(rec)
    db.flush()
    _refresh_project(db, project)
    add_event(db, project, "maintenance_reported", source=source, actor=actor,
              summary=f"{rec.maintenance_code}: {rec.problem_type}", payload={"maintenance_id": rec.id,
                                                                              "code": rec.maintenance_code})
    audit(db, "maintenance.create", "maintenance", rec.maintenance_code, actor=actor, after=snapshot(rec))
    queue_sheet_sync(db)
    return rec


def update_record(db: Session, rec: MaintenanceRecord, changes: dict, *, actor: User) -> MaintenanceRecord:
    """Only follow-up fields can change; the original report (date, problem, well)
    is immutable, and every change is kept in the audit log."""
    before = snapshot(rec)
    for k, v in changes.items():
        setattr(rec, k, v)
    rec.updated_at = utcnow()
    project = db.get(Project, rec.project_id)
    _refresh_project(db, project)
    add_event(db, project, "maintenance_updated", source="dashboard", actor=actor,
              summary=f"{rec.maintenance_code} updated", payload={"maintenance_id": rec.id, "changes": list(changes)})
    audit(db, "maintenance.update", "maintenance", rec.maintenance_code, actor=actor, before=before, after=snapshot(rec))
    queue_sheet_sync(db)
    return rec

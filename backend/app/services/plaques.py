"""Plaque designer: each saved plaque is a print-ready PNG stored with the well's media
(category PLAQUE, Drive folder Plaques/<WellID>/) plus a 'plaque_saved' timeline event
that keeps the design settings, so the plaque can be reopened and edited later.
Rule-based only: the browser draws the plaque; no AI is involved."""
import json
from typing import BinaryIO

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MediaCategory, Project, ProjectEvent, User, utcnow
from app.services.audit import audit
from app.services.media import store_media
from app.services.projects import add_event

MAX_DESIGN_BYTES = 600_000  # room for an uploaded flag or well icon (shrunk in the browser)
PLAQUE_MIME = {"image/png", "application/pdf"}


def parse_design(raw: str) -> dict:
    if len(raw.encode("utf-8")) > MAX_DESIGN_BYTES:
        raise HTTPException(413, "Plaque design is too large")
    try:
        design = json.loads(raw)
    except ValueError:
        raise HTTPException(422, "Plaque design is not valid JSON")
    if not isinstance(design, dict) or not isinstance(design.get("template"), str):
        raise HTTPException(422, "Plaque design needs a template")
    return design


def save_plaque(db: Session, project: Project, fh: BinaryIO, *, filename: str | None, mime_type: str | None,
                design: dict, actor: User, approve: bool = False, replace: bool = False) -> dict:
    """Every save is a new version (nothing is overwritten). approve=True also makes it the
    order's approved plaque; if another plaque is already approved, replace=True is required."""
    mime = (mime_type or "").split(";")[0]
    if mime not in PLAQUE_MIME:
        raise HTTPException(415, "A plaque must be a PNG or PDF file")
    if approve:
        _check_replace(project, replace)
    asset, _ = store_media(db, fh, original_filename=filename or f"plaque-{project.well_id}.png", mime_type=mime,
                           project=project, category=MediaCategory.plaque, source="dashboard",
                           sender=actor.full_name, actor=actor)
    label = design.get("name") or design.get("name_ar") or design.get("name_en") or ""
    version = _count(db, project) + 1
    ev = add_event(db, project, "plaque_saved", source="dashboard", actor=actor,
                   summary=f"v{version} · {design.get('template')} · {design.get('size', '')} · {label}"[:500],
                   payload={"media_id": asset.id, "filename": asset.filename, "design": design, "version": version})
    audit(db, "plaque.saved", "project", project.well_id, actor=actor,
          after={"media_id": asset.id, "template": design.get("template"), "version": version})
    if project.plaque_status is None:
        project.plaque_status = "draft"
    db.flush()
    from app.services import plaque_flow
    v = plaque_flow.add_version(db, project, design=design, actor=actor, media_id=asset.id, filename=asset.filename,
                                event_id=str(ev.id))
    if approve:
        _approve(db, project, ev, actor)
        plaque_flow.approve_from_designer(db, project, v, actor)
    return _row(ev, asset.filename, project)


def _count(db: Session, project: Project) -> int:
    return db.scalar(select(func.count()).select_from(ProjectEvent).where(
        ProjectEvent.project_id == project.id, ProjectEvent.event_type == "plaque_saved")) or 0


def _check_replace(project: Project, replace: bool) -> None:
    if project.plaque_media_id and not replace:
        raise HTTPException(409, "This order already has an approved plaque. Confirm to replace it "
                                 "(the earlier plaque stays in the versions list).")


def _approve(db: Session, project: Project, ev: ProjectEvent, actor: User) -> None:
    media_id = (ev.payload or {}).get("media_id")
    previous = project.plaque_media_id
    project.plaque_status = "approved"
    project.plaque_media_id = media_id
    project.plaque_approved_at = utcnow()
    project.plaque_approved_by = actor.full_name
    add_event(db, project, "plaque_approved", source="dashboard", actor=actor,
              summary=f"Plaque v{(ev.payload or {}).get('version') or ''} approved"[:500],
              payload={"media_id": media_id, "plaque_event_id": str(ev.id), "replaced_media_id": previous})
    audit(db, "plaque.approved", "project", project.well_id, actor=actor,
          before={"plaque_media_id": previous}, after={"plaque_media_id": media_id, "plaque_event_id": str(ev.id)})
    from app.services.projects import queue_sheet_sync
    queue_sheet_sync(db)
    db.flush()


def approve_version(db: Session, project: Project, event_id: str, actor: User, *, replace: bool = False) -> dict:
    import uuid
    try:
        eid = uuid.UUID(str(event_id))
    except ValueError:
        raise HTTPException(404, "No such plaque version")
    ev = db.scalar(select(ProjectEvent).where(ProjectEvent.id == eid, ProjectEvent.project_id == project.id,
                                              ProjectEvent.event_type == "plaque_saved"))
    if not ev:
        raise HTTPException(404, "No such plaque version")
    if project.plaque_media_id == (ev.payload or {}).get("media_id"):
        return _row(ev, None, project)
    _check_replace(project, replace)
    _approve(db, project, ev, actor)
    from app.models import PlaqueVersion
    from app.services import plaque_flow
    v = db.scalar(select(PlaqueVersion).where(PlaqueVersion.event_id == str(ev.id)))
    if v:
        plaque_flow.approve_from_designer(db, project, v, actor)
    return _row(ev, None, project)


def plaque_file(db: Session, project_ids: list[int], media_id: int) -> tuple[bytes, str, str]:
    from app.integrations.drive import get_drive_client
    from app.models import MediaAsset
    a = db.get(MediaAsset, media_id)
    if not a or a.project_id not in project_ids or a.category != MediaCategory.plaque or not a.drive_file_id:
        raise HTTPException(404, "Plaque file not found")
    try:
        data = get_drive_client().download(a.drive_file_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Could not read the plaque file: {e}")
    return data, a.mime_type, a.filename


def _row(ev: ProjectEvent, filename: str | None = None, project: Project | None = None) -> dict:
    p = ev.payload or {}
    return {"id": str(ev.id), "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "actor_label": ev.actor_label, "media_id": p.get("media_id"), "version": p.get("version"),
            "filename": filename or p.get("filename"), "design": p.get("design") or {},
            "approved": bool(project and project.plaque_media_id and project.plaque_media_id == p.get("media_id"))}


def list_plaques(db: Session, project: Project, project_ids: list[int]) -> list[dict]:
    rows = list(db.scalars(select(ProjectEvent).where(ProjectEvent.project_id.in_(project_ids),
                                                      ProjectEvent.event_type == "plaque_saved")
                           .order_by(ProjectEvent.created_at.desc()).limit(200)))
    out = [_row(e, None, project) for e in rows]
    for i, r in enumerate(out):  # older saves have no number: count them from the oldest
        r["version"] = r["version"] or len(out) - i
    return out


# ---------------- sacrifice plaques ----------------
# Sacrifices have no media table link, so the PNG goes straight to Drive under
# Plaques/Sacrifices/<No>/ and the design is kept in the audit log (action plaque.saved).
def sacrifice_plaque_data(db: Session, no: int) -> dict:
    """Only what a plaque needs. Never cost or price, so Employees can use it."""
    from app.models import Contractor, Sacrifice
    s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no))
    if not s:
        raise HTTPException(404, f"No sacrifice number {no}")
    c = db.get(Contractor, s.contractor_id) if s.contractor_id else None
    return {"sacrifice_no": s.sacrifice_no, "donor_name": s.donor_name, "dedication": getattr(s, "dedication", None),
            "animal_type": s.animal_type, "intention": s.intention, "extras": s.extras,
            "order_date": s.order_date, "delivery_date": s.delivery_date,
            "contractor_country": c.country if c else None}


def save_sacrifice_plaque(db: Session, no: int, fh: BinaryIO, *, mime_type: str | None, design: dict, actor: User,
                          approve: bool = False) -> dict:
    """Stored like every other file (media_assets, Drive Plaques/Sacrifices/<No>/) and added as a
    new version of the sacrifice's plaque. The audit row keeps the design for the history list."""
    from app.models import Sacrifice
    from app.services import plaque_flow
    from app.services.media import sniff_ok
    sacrifice_plaque_data(db, no)  # 404 if unknown
    s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no))
    mime = (mime_type or "").split(";")[0]
    fh.seek(0)
    if mime != "image/png" or not sniff_ok(fh.read(16), mime):
        raise HTTPException(415, "A plaque must be a PNG file")
    fh.seek(0)
    asset, _ = store_media(db, fh, original_filename=f"sacrifice-plaque-{no}.png", mime_type=mime, project=None,
                           category=MediaCategory.plaque, source="dashboard", sender=actor.full_name, actor=actor, sacrifice=s)
    row = audit(db, "plaque.saved", "sacrifice", no, actor=actor,
                after={"filename": asset.filename, "drive_file_id": asset.drive_file_id, "media_id": asset.id, "design": design})
    db.flush()
    v = plaque_flow.add_version(db, s, design=design, actor=actor, media_id=asset.id, filename=asset.filename)
    if approve:
        plaque_flow.approve_from_designer(db, s, v, actor)
    return _audit_row(row)


def _audit_row(a) -> dict:
    after = a.after or {}
    return {"id": str(a.id), "created_at": a.at.isoformat() if a.at else None, "actor_label": a.actor_label,
            "filename": after.get("filename"), "design": after.get("design") or {}}


def list_sacrifice_plaques(db: Session, no: int) -> list[dict]:
    from app.models import AuditLog
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "plaque.saved", AuditLog.entity_type == "sacrifice",
                                             AuditLog.entity_id == str(no)).order_by(AuditLog.at.desc()).limit(200))
    return [_audit_row(a) for a in rows]

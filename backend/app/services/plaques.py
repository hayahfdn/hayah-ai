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
                design: dict, actor: User) -> dict:
    mime = (mime_type or "").split(";")[0]
    if mime not in PLAQUE_MIME:
        raise HTTPException(415, "A plaque must be a PNG or PDF file")
    asset, _ = store_media(db, fh, original_filename=filename or f"plaque-{project.well_id}.png", mime_type=mime,
                           project=project, category=MediaCategory.plaque, source="dashboard",
                           sender=actor.full_name, actor=actor)
    label = design.get("name_ar") or design.get("name_en") or ""
    ev = add_event(db, project, "plaque_saved", source="dashboard", actor=actor,
                   summary=f"{design.get('template')} · {design.get('size', '')} · {label}"[:500],
                   payload={"media_id": asset.id, "filename": asset.filename, "design": design})
    audit(db, "plaque.saved", "project", project.well_id, actor=actor,
          after={"media_id": asset.id, "template": design.get("template")})
    db.flush()
    return _row(ev, asset.filename)


def _row(ev: ProjectEvent, filename: str | None = None) -> dict:
    p = ev.payload or {}
    return {"id": str(ev.id), "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "actor_label": ev.actor_label, "media_id": p.get("media_id"),
            "filename": filename or p.get("filename"), "design": p.get("design") or {}}


def list_plaques(db: Session, project_ids: list[int]) -> list[dict]:
    rows = db.scalars(select(ProjectEvent).where(ProjectEvent.project_id.in_(project_ids),
                                                 ProjectEvent.event_type == "plaque_saved")
                      .order_by(ProjectEvent.created_at.desc()).limit(200))
    return [_row(e) for e in rows]


# ---------------- sacrifice plaques ----------------
# Sacrifices have no media table link, so the PNG goes straight to Drive under
# Plaques/Sacrifices/<No>/ and the design is kept in the audit log (action plaque.saved).
def sacrifice_plaque_data(db: Session, no: int) -> dict:
    """Only what a plaque needs. Never cost or price, so Team members can use it."""
    from app.models import Contractor, Sacrifice
    s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no))
    if not s:
        raise HTTPException(404, f"No sacrifice number {no}")
    c = db.get(Contractor, s.contractor_id) if s.contractor_id else None
    return {"sacrifice_no": s.sacrifice_no, "donor_name": s.donor_name, "dedication": getattr(s, "dedication", None),
            "animal_type": s.animal_type, "intention": s.intention, "extras": s.extras,
            "order_date": s.order_date, "delivery_date": s.delivery_date,
            "contractor_country": c.country if c else None}


def save_sacrifice_plaque(db: Session, no: int, fh: BinaryIO, *, mime_type: str | None, design: dict, actor: User) -> dict:
    import hashlib
    from app.integrations.drive import get_drive_client
    from app.models import AuditLog
    from app.services.media import ensure_structure, sniff_ok
    sacrifice_plaque_data(db, no)  # 404 if unknown
    mime = (mime_type or "").split(";")[0]
    fh.seek(0)
    if mime != "image/png" or not sniff_ok(fh.read(16), mime):
        raise HTTPException(415, "A plaque must be a PNG file")
    fh.seek(0)
    digest = hashlib.sha256(fh.read()).hexdigest()
    fh.seek(0)
    drive = get_drive_client()
    remote = drive.find_by_sha256(digest)
    if not remote:
        cache = ensure_structure(db)
        folder = drive.ensure_folder(str(no), drive.ensure_folder("Sacrifices", cache["Plaques"]))
        n = db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "plaque.saved", AuditLog.entity_type == "sacrifice", AuditLog.entity_id == str(no))) or 0
        name = f"S{no}_{utcnow().date().isoformat()}_PLAQUE_{n + 1:03d}.png"
        remote = drive.upload(fh, name, mime, folder, {"sha256": digest, "sacrifice_no": no, "category": "PLAQUE"})
        remote = {**remote, "name": name}
    row = audit(db, "plaque.saved", "sacrifice", no, actor=actor,
                after={"filename": remote.get("name"), "drive_file_id": remote["id"], "design": design})
    db.flush()
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

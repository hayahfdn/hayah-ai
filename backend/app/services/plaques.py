"""Plaque designer: each saved plaque is a print-ready PNG stored with the well's media
(category PLAQUE, Drive folder Plaques/<WellID>/) plus a 'plaque_saved' timeline event
that keeps the design settings, so the plaque can be reopened and edited later.
Rule-based only: the browser draws the plaque; no AI is involved."""
import json
from typing import BinaryIO

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MediaCategory, Project, ProjectEvent, User
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

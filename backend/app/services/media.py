"""Media storage in Google Drive with metadata in PostgreSQL.

Folder layout (created automatically):
  HAYAH PROJECTS/
    Raw Footages/<WellID>/
    Final Videos/<WellID>/
    Maintenance & Servicing/<WellID>/
    Plaques/<WellID>/
    Unassigned Media/
    Pending Review/
Filenames: <WellID>_<YYYY-MM-DD>_<CATEGORY>_<NNN>.<ext>
"""
import hashlib
import mimetypes
import re
from datetime import date, datetime
from typing import BinaryIO

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.drive import get_drive_client
from app.models import (
    MediaAsset, MediaCategory, Project, ReviewCase, ReviewKind, User, VideoStatus, utcnow,
)
from app.services.audit import audit
from app.services.projects import add_event, queue_sheet_sync
from app.services.settings_store import get_setting, set_setting

TOP_FOLDERS = ["Raw Footages", "Final Videos", "Maintenance & Servicing", "Plaques", "Unassigned Media", "Pending Review"]
CATEGORY_FOLDER = {
    MediaCategory.construction: "Raw Footages", MediaCategory.delivery: "Raw Footages",
    MediaCategory.other: "Raw Footages", MediaCategory.final_video: "Final Videos",
    MediaCategory.maintenance: "Maintenance & Servicing", MediaCategory.maintenance_before: "Maintenance & Servicing",
    MediaCategory.maintenance_after: "Maintenance & Servicing", MediaCategory.plaque: "Plaques",
}
ALLOWED_MIME = re.compile(r"^(image/(jpeg|png|webp|heic|heif)|video/(mp4|quicktime|3gpp|webm|x-matroska)|"
                          r"audio/(ogg|mpeg|aac|mp4|amr)|application/pdf)$")
# magic numbers for common types so a renamed .exe is not accepted as a .jpg
MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"%PDF": "application/pdf",
         b"RIFF": "image/webp", b"OggS": "audio/ogg", b"\x1aE\xdf\xa3": "video/webm"}


def sniff_ok(head: bytes, mime: str) -> bool:
    if head[4:8] == b"ftyp":  # mp4 / mov / 3gp / heic / m4a family
        return mime.startswith(("video/", "image/hei", "audio/mp4", "audio/aac"))
    for sig, m in MAGIC.items():
        if head.startswith(sig):
            return mime == m or (sig == b"RIFF" and mime.startswith("image/webp"))
    return mime.startswith("audio/") or mime == "video/3gpp" or mime.startswith("image/hei")


def ensure_structure(db: Session) -> dict:
    cache = get_setting(db, "drive_folders") or {}
    drive = get_drive_client()
    if not cache.get("root"):
        s = get_settings()
        cache["root"] = s.drive_root_folder_id or drive.ensure_folder(s.drive_root_folder_name, None)
    for name in TOP_FOLDERS:
        if not cache.get(name):
            cache[name] = drive.ensure_folder(name, cache["root"])
    cache.setdefault("wells", {})
    set_setting(db, "drive_folders", cache)
    return cache


def well_folder(db: Session, top: str, well_id: int) -> str:
    cache = ensure_structure(db)
    key = f"{top}/{well_id}"
    if not cache["wells"].get(key):
        cache["wells"][key] = get_drive_client().ensure_folder(str(well_id), cache[top])
        set_setting(db, "drive_folders", dict(cache))
    return cache["wells"][key]


def build_filename(db: Session, well_id: int | None, day: date, category: MediaCategory, ext: str) -> str:
    prefix = f"{well_id if well_id else 'UNASSIGNED'}_{day.isoformat()}_{category.value}_"
    n = db.scalar(select(func.count()).select_from(MediaAsset).where(MediaAsset.filename.like(prefix + "%"))) or 0
    return f"{prefix}{n + 1:03d}{ext}"


def store_media(db: Session, fh: BinaryIO, *, original_filename: str | None, mime_type: str | None,
                project: Project | None, category: MediaCategory, source: str, sender: str | None = None,
                actor: User | None = None, inbound_message_id: int | None = None,
                captured_at: datetime | None = None, maintenance_id: int | None = None) -> tuple[MediaAsset, bool]:
    """Returns (asset, created). created=False means an identical file was already stored."""
    s = get_settings()
    mime_type = (mime_type or mimetypes.guess_type(original_filename or "")[0] or "application/octet-stream").split(";")[0]
    if not ALLOWED_MIME.match(mime_type):
        raise HTTPException(415, f"File type {mime_type} is not allowed")
    sha, size = hashlib.sha256(), 0
    fh.seek(0)
    head = fh.read(16)
    fh.seek(0)
    if not sniff_ok(head, mime_type):
        raise HTTPException(415, "File content does not match its type")
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        sha.update(chunk)
        size += len(chunk)
        if size > s.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"File is larger than {s.max_upload_mb} MB")
    digest = sha.hexdigest()
    fh.seek(0)
    existing = db.scalar(select(MediaAsset).where(MediaAsset.sha256 == digest))
    if existing:
        return existing, False

    drive = get_drive_client()
    day = (captured_at or utcnow()).date()
    ext = ""
    if original_filename and "." in original_filename:
        ext = "." + re.sub(r"[^a-zA-Z0-9]", "", original_filename.rsplit(".", 1)[1])[:5].lower()
    ext = ext or mimetypes.guess_extension(mime_type) or ""
    if project:
        top = CATEGORY_FOLDER[category]
        folder_id = well_folder(db, top, project.well_id)
    else:
        folder_id = ensure_structure(db)["Unassigned Media"]
    name = build_filename(db, project.well_id if project else None, day, category, ext)

    remote = drive.find_by_sha256(digest)  # survives a crash between upload and DB commit
    if not remote:
        remote = drive.upload(fh, name, mime_type, folder_id, {"sha256": digest,
                                                                "well_id": project.well_id if project else "",
                                                                "category": category.value})
    asset = MediaAsset(project_id=project.id if project else None, category=category, filename=name,
                       original_filename=original_filename, mime_type=mime_type, size_bytes=size, sha256=digest,
                       drive_file_id=remote["id"], drive_folder_id=folder_id, drive_url=remote.get("url"),
                       source=source, sender=sender, inbound_message_id=inbound_message_id,
                       captured_at=captured_at, uploaded_by_id=actor.id if actor else None,
                       maintenance_id=maintenance_id)
    db.add(asset)
    db.flush()
    if project:
        if category in (MediaCategory.construction, MediaCategory.delivery, MediaCategory.other) and not project.raw_media_folder_id:
            project.raw_media_folder_id = folder_id
            project.raw_media_folder_url = drive.folder_url(folder_id)
        if mime_type.startswith("video/") and category == MediaCategory.construction and project.video_status == VideoStatus.none:
            project.video_status = VideoStatus.raw_received
        project.updated_at = utcnow()
        add_event(db, project, "media_added", source=source, actor=actor, actor_label=sender,
                  summary=f"{category.value}: {name}", payload={"media_id": asset.id, "drive_file_id": asset.drive_file_id})
        queue_sheet_sync(db)
    else:
        db.add(ReviewCase(kind=ReviewKind.unassigned_media, media_asset_id=asset.id,
                          inbound_message_id=inbound_message_id, dedupe_key=f"media:{asset.id}",
                          reason="Media received without a confident Well ID",
                          proposed={"filename": name, "sender": sender}))
    audit(db, "media.stored", "media", asset.id, actor=actor, actor_label=sender,
          after={"filename": name, "drive_file_id": asset.drive_file_id, "sha256": digest})
    return asset, True


def assign_media(db: Session, asset: MediaAsset, project: Project, category: MediaCategory, actor: User) -> MediaAsset:
    """Link an unassigned file to a well. The Drive original stays where it is
    (never moved or deleted); a reference is recorded instead."""
    asset.project_id = project.id
    asset.category = category
    add_event(db, project, "media_assigned", source="dashboard", actor=actor, summary=asset.filename,
              payload={"media_id": asset.id})
    audit(db, "media.assigned", "media", asset.id, actor=actor, after={"well_id": project.well_id})
    queue_sheet_sync(db)
    return asset

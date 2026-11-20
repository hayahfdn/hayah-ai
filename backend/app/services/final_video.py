"""Final delivery video of each order (wells and sacrifices).

States: not_uploaded → uploaded → ready_for_delivery → sent_to_customer.
Every upload is kept (a media asset of category final_video linked to that one order), a newer
upload becomes the current video and goes back to "uploaded" so it is checked again. A file that
already belongs to another order is refused, so videos of different orders never mix.
Every step is written to the order's timeline (wells) and the audit log.
"""
from __future__ import annotations

from typing import BinaryIO

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    FinalVideo, FinalVideoStatus as V, MediaAsset, MediaCategory, Plaque, PlaqueStatus, Project, Sacrifice, User,
    VideoStatus, utcnow,
)
from app.services.audit import audit

LABELS_AR = {V.not_uploaded: "لم يتم رفع الفيديو", V.uploaded: "تم رفع الفيديو",
             V.ready_for_delivery: "جاهز للتسليم", V.sent_to_customer: "تم إرساله للعميل"}
MOVES = {V.uploaded: {V.ready_for_delivery}, V.ready_for_delivery: {V.sent_to_customer, V.uploaded},
         V.sent_to_customer: {V.ready_for_delivery}}
VIDEO_TYPES = ("video/mp4", "video/quicktime")


def number(rec) -> int:
    return rec.well_id if isinstance(rec, Project) else rec.sacrifice_no


def get(db: Session, rec, lock: bool = False) -> FinalVideo | None:
    col = FinalVideo.project_id if isinstance(rec, Project) else FinalVideo.sacrifice_id
    q = select(FinalVideo).where(col == rec.id)
    return db.scalar(q.with_for_update() if lock else q)


def _order_filter(rec):
    return MediaAsset.project_id == rec.id if isinstance(rec, Project) else MediaAsset.sacrifice_id == rec.id


def _log(db: Session, fv: FinalVideo, rec, event: str, actor: User | None, summary: str, payload: dict | None = None) -> None:
    if isinstance(rec, Project):
        from app.services.projects import add_event
        add_event(db, rec, event, source="dashboard", actor=actor, summary=summary[:500], payload={"final_video_id": fv.id, **(payload or {})})
    audit(db, f"final_video.{event.removeprefix('final_video_')}", "final_video", fv.id, actor=actor,
          after={"order": ("well " if isinstance(rec, Project) else "sacrifice ") + str(number(rec)),
                 "status": fv.status.value, "summary": summary, **(payload or {})})


def upload(db: Session, rec, fh: BinaryIO, *, filename: str | None, mime_type: str | None, actor: User) -> FinalVideo:
    from app.services.media import store_media
    mime = (mime_type or "").split(";")[0].lower()
    if filename and filename.lower().endswith(".mov"):
        mime = "video/quicktime"
    elif filename and filename.lower().endswith(".mp4") and not mime.startswith("video/"):
        mime = "video/mp4"
    if mime not in VIDEO_TYPES:
        raise HTTPException(415, "Upload an MP4 or MOV video")
    fv = get(db, rec, lock=True)
    is_well = isinstance(rec, Project)
    asset, created = store_media(db, fh, original_filename=filename, mime_type=mime,
                                 project=rec if is_well else None, sacrifice=None if is_well else rec,
                                 category=MediaCategory.final_video, source="dashboard", actor=actor)
    if not created:
        same_order = (asset.project_id == rec.id) if is_well else (asset.sacrifice_id == rec.id)
        if not same_order or asset.category != MediaCategory.final_video:
            raise HTTPException(409, "This exact video is already stored for another order or as another kind of file. "
                                     "Check that you picked the right order.")
        if fv and fv.current_media_id == asset.id:
            raise HTTPException(409, "This video is already the current final video of this order.")
    if not fv:
        fv = FinalVideo(kind="well" if is_well else "sacrifice", project_id=rec.id if is_well else None,
                        sacrifice_id=None if is_well else rec.id)
        db.add(fv)
    replaced = fv.current_media_id
    fv.current_media_id = asset.id
    fv.status = V.uploaded
    fv.uploaded_at, fv.uploaded_by = utcnow(), actor.full_name
    fv.ready_at = fv.ready_by = None
    fv.updated_at = utcnow()
    if is_well and rec.video_status != VideoStatus.completed:
        rec.video_status = VideoStatus.completed
    db.flush()
    _log(db, fv, rec, "final_video_uploaded", actor,
         ("Final video replaced: " if replaced else "Final video uploaded: ") + asset.filename,
         {"media_id": asset.id, "replaced_media_id": replaced, "size_bytes": asset.size_bytes})
    return fv


def set_status(db: Session, rec, to: V, actor: User, note: str | None = None) -> FinalVideo:
    fv = get(db, rec, lock=True)
    if not fv or not fv.current_media_id:
        raise HTTPException(409, "Upload the final video first")
    if to not in MOVES.get(fv.status, set()):
        raise HTTPException(409, f"A video that is '{LABELS_AR[fv.status]}' cannot move to '{LABELS_AR[to]}'")
    before = fv.status
    fv.status = to
    now = utcnow()
    if to == V.ready_for_delivery and before == V.uploaded:
        fv.ready_at, fv.ready_by = now, actor.full_name
    if to == V.sent_to_customer:
        fv.sent_at, fv.sent_by, fv.sent_note = now, actor.full_name, (note or None)
    fv.updated_at = now
    db.flush()
    _log(db, fv, rec, "final_video_status", actor, f"{LABELS_AR[before]} → {LABELS_AR[to]}" + (f" · {note}" if note else ""),
         {"from": before.value, "to": to.value})
    return fv


def versions(db: Session, rec) -> list[MediaAsset]:
    return list(db.scalars(select(MediaAsset).where(_order_filter(rec), MediaAsset.category == MediaCategory.final_video)
                           .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())))


def data(db: Session, rec) -> dict:
    fv = get(db, rec)
    vs = versions(db, rec)
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_({v.uploaded_by_id for v in vs if v.uploaded_by_id})))}
    status = fv.status if fv else V.not_uploaded
    phone = rec.customer_phone_e164
    return {
        "kind": "well" if isinstance(rec, Project) else "sacrifice", "number": number(rec),
        "status": status.value, "status_ar": LABELS_AR[status],
        "current_media_id": fv.current_media_id if fv else None,
        "uploaded_at": fv.uploaded_at if fv else None, "uploaded_by": fv.uploaded_by if fv else None,
        "ready_at": fv.ready_at if fv else None, "ready_by": fv.ready_by if fv else None,
        "sent_at": fv.sent_at if fv else None, "sent_by": fv.sent_by if fv else None, "sent_note": fv.sent_note if fv else None,
        "customer_name": rec.customer_name if isinstance(rec, Project) else rec.donor_name,
        "customer_phone_e164": phone, "customer_phone_status": rec.customer_phone_status,
        "final_video_link": rec.final_video_link if isinstance(rec, Project) else None,
        "versions": [{"media_id": v.id, "filename": v.filename, "original_filename": v.original_filename, "mime_type": v.mime_type,
                      "size_bytes": v.size_bytes, "created_at": v.created_at,
                      "uploaded_by": names.get(v.uploaded_by_id) or v.sender,
                      "current": bool(fv and fv.current_media_id == v.id)} for v in vs],
    }


def asset_for(db: Session, media_id: int) -> MediaAsset:
    a = db.get(MediaAsset, media_id)
    if not a or a.category != MediaCategory.final_video:
        raise HTTPException(404, "No such final video")
    return a


def list_videos(db: Session, status: V | None = None, limit: int = 300) -> list[dict]:
    q = select(FinalVideo).order_by(FinalVideo.updated_at.desc()).limit(limit)
    if status:
        q = q.where(FinalVideo.status == status)
    out = []
    for fv in db.scalars(q):
        rec = db.get(Project, fv.project_id) if fv.project_id else db.get(Sacrifice, fv.sacrifice_id)
        d = data(db, rec)
        d.pop("versions")
        out.append(d)
    return out


def _waiting_filter_wells():
    """Wells waiting for their final video: the plaque was sent to the contractor (or the well is
    built or delivered), and no final video file or link exists yet. Older wells delivered before
    this workflow only count if they were built in the system's workflow (plaque sent)."""
    has_video = exists().where(FinalVideo.project_id == Project.id, FinalVideo.current_media_id.is_not(None))
    plaque_sent = exists().where(Plaque.project_id == Project.id, Plaque.status == PlaqueStatus.sent_to_contractor)
    return and_(Project.merged_into_id.is_(None), Project.is_sample.is_(False), ~has_video,
                or_(Project.final_video_link.is_(None), Project.final_video_link == ""), plaque_sent)


def counts(db: Session) -> dict:
    g = lambda s: db.scalar(select(func.count()).select_from(FinalVideo).where(FinalVideo.status == s)) or 0  # noqa: E731
    waiting_wells = db.scalar(select(func.count()).select_from(Project).where(_waiting_filter_wells())) or 0
    sac_has_video = exists().where(FinalVideo.sacrifice_id == Sacrifice.id, FinalVideo.current_media_id.is_not(None))
    waiting_sac = db.scalar(select(func.count()).select_from(Plaque).join(Sacrifice, Plaque.sacrifice_id == Sacrifice.id)
                            .where(Plaque.status == PlaqueStatus.sent_to_contractor, ~sac_has_video)) or 0
    return {"waiting_upload": waiting_wells + waiting_sac, "uploaded": g(V.uploaded),
            "ready_for_delivery": g(V.ready_for_delivery), "sent_to_customer": g(V.sent_to_customer)}


def waiting_list(db: Session, limit: int = 300) -> list[dict]:
    """Orders that still need their final video (same rule as counts)."""
    out = []
    for p in db.scalars(select(Project).where(_waiting_filter_wells()).order_by(Project.well_id.desc()).limit(limit)):
        out.append({"kind": "well", "number": p.well_id, "status": V.not_uploaded.value, "status_ar": LABELS_AR[V.not_uploaded],
                    "customer_name": p.customer_name, "customer_phone_e164": p.customer_phone_e164,
                    "customer_phone_status": p.customer_phone_status})
    sac_has_video = exists().where(FinalVideo.sacrifice_id == Sacrifice.id, FinalVideo.current_media_id.is_not(None))
    for s in db.scalars(select(Sacrifice).join(Plaque, Plaque.sacrifice_id == Sacrifice.id)
                        .where(Plaque.status == PlaqueStatus.sent_to_contractor, ~sac_has_video).limit(limit)):
        out.append({"kind": "sacrifice", "number": s.sacrifice_no, "status": V.not_uploaded.value,
                    "status_ar": LABELS_AR[V.not_uploaded], "customer_name": s.donor_name, "customer_phone_e164": s.customer_phone_e164,
                    "customer_phone_status": s.customer_phone_status})
    return out

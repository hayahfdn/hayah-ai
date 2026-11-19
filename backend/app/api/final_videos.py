"""Final delivery videos: upload, play, download, status. Employees and managers only.

A <video> tag cannot send the login header, so playing or downloading goes through a short-lived
signed link (2 hours, one file, made only for a logged-in employee or manager).
"""
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import PROJECT_CREATORS, require_roles
from app.models import FinalVideoStatus, Project, Sacrifice, User
from app.services import final_video as fv

router = APIRouter(prefix="/api/videos", tags=["final videos"])
EDITORS = Depends(require_roles(PROJECT_CREATORS))
LINK_HOURS = 2


def _order(db: Session, kind: str, number: int):
    if kind == "well":
        rec = db.scalar(select(Project).where(Project.well_id == number))
    elif kind == "sacrifice":
        rec = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == number))
    else:
        raise HTTPException(404, "Unknown order type")
    if not rec:
        raise HTTPException(404, f"No {kind} number {number}")
    return rec


@router.get("")
def list_all(status: str = Query("ready_for_delivery", pattern="^(waiting|uploaded|ready_for_delivery|sent_to_customer)$"),
             db: Session = Depends(get_db), _: User = EDITORS):
    if status == "waiting":
        return fv.waiting_list(db)
    return fv.list_videos(db, FinalVideoStatus(status))


@router.get("/counts")
def counts(db: Session = Depends(get_db), _: User = EDITORS):
    return fv.counts(db)


@router.get("/order/{kind}/{number}")
def for_order(kind: str, number: int, db: Session = Depends(get_db), _: User = EDITORS):
    return fv.data(db, _order(db, kind, number))


@router.post("/order/{kind}/{number}", status_code=201)
def upload(kind: str, number: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = EDITORS):
    rec = _order(db, kind, number)
    # spool to disk (videos can be hundreds of MB; the server has little memory)
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as tmp:
        shutil.copyfileobj(file.file, tmp, 1024 * 1024)
        tmp.seek(0)
        fv.upload(db, rec, tmp, filename=file.filename, mime_type=file.content_type, actor=user)
    db.commit()
    return fv.data(db, rec)


class StatusIn(BaseModel):
    to: FinalVideoStatus
    note: str | None = Field(default=None, max_length=1000)


@router.post("/order/{kind}/{number}/status")
def change_status(kind: str, number: int, body: StatusIn, db: Session = Depends(get_db), user: User = EDITORS):
    rec = _order(db, kind, number)
    fv.set_status(db, rec, body.to, user, body.note)
    db.commit()
    return fv.data(db, rec)


@router.get("/file/{media_id}/link")
def file_link(media_id: int, db: Session = Depends(get_db), user: User = EDITORS):
    fv.asset_for(db, media_id)
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=LINK_HOURS)
    t = jwt.encode({"sub": str(user.id), "media": media_id, "purpose": "final_video", "exp": exp}, s.jwt_secret, algorithm=s.jwt_algorithm)
    return {"url": f"/api/videos/file/{media_id}?t={t}", "download_url": f"/api/videos/file/{media_id}?t={t}&download=true",
            "expires_at": exp}


@router.get("/file/{media_id}")
def file(media_id: int, t: str, download: bool = False, db: Session = Depends(get_db)):
    s = get_settings()
    try:
        claims = jwt.decode(t, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(401, "This video link has expired. Open the order again.")
    if claims.get("purpose") != "final_video" or claims.get("media") != media_id:
        raise HTTPException(403, "This link is for another file")
    user = db.get(User, int(claims["sub"]))
    if not user or not user.is_active or user.role not in PROJECT_CREATORS:
        raise HTTPException(403, "Not allowed")
    a = fv.asset_for(db, media_id)
    from app.integrations.drive import get_drive_client
    drive = get_drive_client()
    disp = f'{"attachment" if download else "inline"}; filename="{a.filename}"'
    path = getattr(drive, "local_path", lambda _id: None)(a.drive_file_id)
    if path and path.exists():  # stream from disk, with seeking (Range requests)
        return FileResponse(path, media_type=a.mime_type, headers={"Content-Disposition": disp, "Cache-Control": "private, max-age=3600"})
    try:
        data = drive.download(a.drive_file_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Could not read the video file: {e}")
    return Response(content=data, media_type=a.mime_type, headers={"Content-Disposition": disp})

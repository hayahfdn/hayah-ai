"""WhatsApp inbox API (employees and managers). Settings for the connection: admins only."""
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import ADMINS, PROJECT_CREATORS, require_roles
from app.integrations.whatsapp import WaSendError
from app.models import FinalVideo, MediaAsset, MediaCategory, Plaque, PlaqueVersion, User, WaConversation, WaMessage
from app.services import wa_inbox as wa

router = APIRouter(prefix="/api/inbox", tags=["whatsapp inbox"])
EDITORS = Depends(require_roles(PROJECT_CREATORS))
LINK_HOURS = 2


def _conv(db: Session, cid: int, lock: bool = False) -> WaConversation:
    q = select(WaConversation).where(WaConversation.id == cid)
    c = db.scalar(q.with_for_update() if lock else q)
    if not c:
        raise HTTPException(404, "No such chat")
    return c


def _signer(user: User):
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=LINK_HOURS)

    def sign(message_id: int) -> str:
        t = jwt.encode({"sub": str(user.id), "wam": message_id, "purpose": "wa_media", "exp": exp}, s.jwt_secret, algorithm=s.jwt_algorithm)
        return f"/api/inbox/media/{message_id}?t={t}"
    return sign


# ---------------------------------------------------------------- chats
@router.get("/status")
def connection(db: Session = Depends(get_db), _: User = EDITORS):
    st = wa.status(db)
    return {"enabled": st["enabled"], "mock": st["mock"], "display_number": st["display_number"]}


@router.get("/counts")
def counts(db: Session = Depends(get_db), _: User = EDITORS):
    return wa.counts(db)


@router.get("/conversations")
def conversations(box: str = Query("all", pattern="^(all|mine|unassigned|unread|waiting|open|pending|closed)$"),
                  q: str | None = None, db: Session = Depends(get_db), user: User = EDITORS):
    return wa.list_conversations(db, user, box=box, q=q)


class StartIn(BaseModel):
    phone: str = Field(min_length=6, max_length=40)


@router.post("/conversations", status_code=201)
def start(body: StartIn, db: Session = Depends(get_db), user: User = EDITORS):
    c = wa.find_by_phone(db, body.phone)
    db.commit()
    return wa.conv_row(db, c, wa._users(db))


@router.get("/conversations/{cid}")
def one(cid: int, db: Session = Depends(get_db), _: User = EDITORS):
    c = _conv(db, cid)
    return {**wa.conv_row(db, c, wa._users(db)), "orders": wa.orders_for(db, c)}


@router.get("/conversations/{cid}/messages")
def messages(cid: int, after_id: int | None = None, before_id: int | None = None, limit: int = Query(60, le=200),
             db: Session = Depends(get_db), user: User = EDITORS):
    c = _conv(db, cid)
    q = select(WaMessage).where(WaMessage.conversation_id == c.id)
    if after_id:
        q = q.where(WaMessage.id > after_id).order_by(WaMessage.id).limit(limit)
        rows = list(db.scalars(q))
    else:
        if before_id:
            q = q.where(WaMessage.id < before_id)
        rows = list(reversed(list(db.scalars(q.order_by(WaMessage.id.desc()).limit(limit)))))
    sign = _signer(user)
    return [wa.msg_row(m, sign) for m in rows]


@router.post("/conversations/{cid}/read")
def read(cid: int, db: Session = Depends(get_db), _: User = EDITORS):
    c = _conv(db, cid, lock=True)
    wa.mark_read(db, c)
    db.commit()
    return {"unread": 0}


class AssignIn(BaseModel):
    user_id: int | None = None


@router.post("/conversations/{cid}/assign")
def assign(cid: int, body: AssignIn, db: Session = Depends(get_db), user: User = EDITORS):
    c = wa.assign(db, _conv(db, cid, lock=True), body.user_id, user)
    db.commit()
    return wa.conv_row(db, c, wa._users(db))


class ChatStatusIn(BaseModel):
    status: str = Field(pattern="^(open|pending|closed)$")


@router.post("/conversations/{cid}/status")
def chat_status(cid: int, body: ChatStatusIn, db: Session = Depends(get_db), user: User = EDITORS):
    c = wa.set_status(db, _conv(db, cid, lock=True), body.status, user)
    db.commit()
    return wa.conv_row(db, c, wa._users(db))


class LinkIn(BaseModel):
    kind: str | None = Field(default=None, pattern="^(well|sacrifice)$")
    number: int | None = None


@router.post("/conversations/{cid}/link")
def link(cid: int, body: LinkIn, db: Session = Depends(get_db), user: User = EDITORS):
    c = wa.link(db, _conv(db, cid, lock=True), body.kind, body.number, user)
    db.commit()
    return {**wa.conv_row(db, c, wa._users(db)), "orders": wa.orders_for(db, c)}


@router.get("/assignees")
def assignees(db: Session = Depends(get_db), _: User = EDITORS):
    return [{"id": u.id, "name": u.full_name, "role": u.role.value} for u in
            db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(PROJECT_CREATORS)).order_by(User.full_name))]


# ---------------------------------------------------------------- sending
class SendIn(BaseModel):
    client_ref: str = Field(min_length=8, max_length=64)  # made by the browser once per message: retries never duplicate
    text: str | None = Field(default=None, max_length=4096)
    asset_id: int | None = None
    template: dict | None = None
    reply_to: str | None = None


@router.post("/conversations/{cid}/send", status_code=201)
def send(cid: int, body: SendIn, db: Session = Depends(get_db), user: User = EDITORS):
    c = _conv(db, cid, lock=True)
    asset = None
    if body.asset_id:
        asset = db.get(MediaAsset, body.asset_id)
        if not asset or asset.category not in (MediaCategory.plaque, MediaCategory.final_video, MediaCategory.other):
            raise HTTPException(404, "No such file")
    tpl = None
    if body.template:
        name = str(body.template.get("name") or "")
        if not name:
            raise HTTPException(422, "Choose a template")
        tpl = {"name": name[:200], "language": str(body.template.get("language") or "ar")[:15],
               "params": [str(p)[:1000] for p in (body.template.get("params") or [])][:20],
               "preview": str(body.template.get("preview") or "")[:2000] or None}
    m = wa.send(db, c, user, client_ref=body.client_ref, text=body.text, asset=asset, caption=body.text if asset else None,
                template=tpl, reply_to=body.reply_to)
    db.commit()
    return wa.msg_row(m, _signer(user))


@router.post("/conversations/{cid}/upload", status_code=201)
def send_file(cid: int, client_ref: str = Form(..., min_length=8, max_length=64), caption: str | None = Form(None),
              file: UploadFile = File(...), db: Session = Depends(get_db), user: User = EDITORS):
    """Send a file from the computer or phone (image, PDF, video, document, audio)."""
    c = _conv(db, cid, lock=True)
    existing = db.scalar(select(WaMessage).where(WaMessage.client_ref == client_ref))
    if existing:
        return wa.msg_row(existing, _signer(user))
    if not wa.window_open(c):
        raise HTTPException(409, "More than 24 hours since the customer's last message: WhatsApp only allows an approved template now.")
    from app.services.media import store_media
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as tmp:
        shutil.copyfileobj(file.file, tmp, 1024 * 1024)
        tmp.seek(0)
        asset, _ = store_media(db, tmp, original_filename=file.filename, mime_type=file.content_type, project=None,
                               category=MediaCategory.other, source="whatsapp_inbox", actor=user, inbox_chat=c.wa_id)
    m = wa.send(db, c, user, client_ref=client_ref, asset=asset, caption=caption)
    db.commit()
    return wa.msg_row(m, _signer(user))


@router.post("/messages/{mid}/retry")
def retry(mid: int, db: Session = Depends(get_db), user: User = EDITORS):
    m = db.get(WaMessage, mid)
    if not m:
        raise HTTPException(404, "No such message")
    wa.retry(db, m, user)
    db.commit()
    return wa.msg_row(m, _signer(user))


@router.get("/conversations/{cid}/attachables")
def attachables(cid: int, db: Session = Depends(get_db), _: User = EDITORS):
    """Files of the linked order that can be sent: the approved (or latest) plaque and the final video."""
    c = _conv(db, cid)
    out = []
    pl = db.scalar(select(Plaque).where(Plaque.project_id == c.project_id)) if c.project_id else \
        (db.scalar(select(Plaque).where(Plaque.sacrifice_id == c.sacrifice_id)) if c.sacrifice_id else None)
    if pl:
        vid = pl.approved_version_id or pl.current_version_id
        v = db.get(PlaqueVersion, vid) if vid else None
        if v and v.media_id:
            out.append({"kind": "plaque", "asset_id": v.media_id, "label": f"plaque v{v.version}", "approved": vid == pl.approved_version_id})
    fv = db.scalar(select(FinalVideo).where(FinalVideo.project_id == c.project_id)) if c.project_id else \
        (db.scalar(select(FinalVideo).where(FinalVideo.sacrifice_id == c.sacrifice_id)) if c.sacrifice_id else None)
    if fv and fv.current_media_id:
        a = db.get(MediaAsset, fv.current_media_id)
        out.append({"kind": "final_video", "asset_id": a.id, "label": a.filename, "size": a.size_bytes, "status": fv.status.value})
    return out


@router.get("/templates")
def templates(db: Session = Depends(get_db), _: User = EDITORS):
    if not wa.enabled(db):
        return []
    try:
        rows = wa.client(db).templates()
    except WaSendError as e:
        raise HTTPException(502, str(e))
    out = []
    for t in rows:
        if t.get("status") != "APPROVED":
            continue
        body = next((c.get("text") for c in t.get("components") or [] if c.get("type") == "BODY"), "") or ""
        out.append({"name": t["name"], "language": t.get("language"), "category": t.get("category"), "body": body,
                    "params": body.count("{{")})
    return out


@router.get("/media/{mid}")
def media(mid: int, t: str, download: bool = False, db: Session = Depends(get_db)):
    s = get_settings()
    try:
        claims = jwt.decode(t, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(401, "This link has expired. Open the chat again.")
    if claims.get("purpose") != "wa_media" or claims.get("wam") != mid:
        raise HTTPException(403, "This link is for another file")
    u = db.get(User, int(claims["sub"]))
    if not u or not u.is_active or u.role not in PROJECT_CREATORS:
        raise HTTPException(403, "Not allowed")
    m = db.get(WaMessage, mid)
    if not m or not m.media_asset_id:
        raise HTTPException(404, "No file")
    a = db.get(MediaAsset, m.media_asset_id)
    from app.integrations.drive import get_drive_client
    drive = get_drive_client()
    # only images, audio and video show in the page; everything else always downloads
    inline = not download and a.mime_type.startswith(("image/", "video/", "audio/")) and a.mime_type != "image/svg+xml"
    name = (m.media or {}).get("filename") or a.filename
    disp = f'{"inline" if inline else "attachment"}; filename="{a.filename}"; filename*=UTF-8\'\'{_quote(name)}'
    path = getattr(drive, "local_path", lambda _id: None)(a.drive_file_id)
    if path and path.exists():
        return FileResponse(path, media_type=a.mime_type, headers={"Content-Disposition": disp, "Cache-Control": "private, max-age=3600"})
    return Response(content=drive.download(a.drive_file_id), media_type=a.mime_type, headers={"Content-Disposition": disp})


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


# ---------------------------------------------------------------- connection settings (admins)
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


class WaSettingsIn(BaseModel):
    phone_number_id: str = Field(min_length=3, max_length=40, pattern=r"^\d+$")
    waba_id: str | None = Field(default=None, max_length=40, pattern=r"^\d*$")
    display_number: str | None = Field(default=None, max_length=40)
    access_token: str | None = Field(default=None, max_length=1000)   # None keeps the stored one, "" clears it
    app_secret: str | None = Field(default=None, max_length=200)
    verify_token: str | None = Field(default=None, max_length=200)


@settings_router.get("/whatsapp-inbox")
def get_wa_settings(db: Session = Depends(get_db), _: User = Depends(require_roles(ADMINS))):
    return wa.status(db)


@settings_router.put("/whatsapp-inbox")
def put_wa_settings(body: WaSettingsIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    st = wa.save_config(db, phone_number_id=body.phone_number_id, waba_id=body.waba_id, display_number=body.display_number,
                        user=user, access_token_value=body.access_token, app_secret_value=body.app_secret,
                        verify_token_value=body.verify_token)
    db.commit()
    return st


@settings_router.post("/whatsapp-inbox/test")
def test_wa(db: Session = Depends(get_db), _: User = Depends(require_roles(ADMINS))):
    if not wa.enabled(db):
        raise HTTPException(409, "Add the phone number ID and the access token first")
    try:
        return {"ok": True, "phone": wa.client(db).phone_info()}
    except WaSendError as e:
        raise HTTPException(502, str(e))


# ---------------- Coexistence: connect the current WhatsApp Business app number ----------------
from app.services import wa_coexist  # noqa: E402


class CoexIdsIn(BaseModel):
    app_id: str = Field(min_length=5, max_length=40, pattern=r"^\d+$")
    config_id: str = Field(min_length=5, max_length=40, pattern=r"^\d+$")


class CoexDoneIn(BaseModel):
    code: str = Field(min_length=5, max_length=2000)
    phone_number_id: str = Field(min_length=3, max_length=40, pattern=r"^\d+$")
    waba_id: str = Field(min_length=3, max_length=40, pattern=r"^\d+$")


@settings_router.get("/whatsapp-coexistence")
def coex_state(db: Session = Depends(get_db), _: User = Depends(require_roles(ADMINS))):
    return wa_coexist.state(db)


@settings_router.put("/whatsapp-coexistence")
def coex_ids(body: CoexIdsIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    return wa_coexist.save_ids(db, body.app_id, body.config_id, user)


@settings_router.post("/whatsapp-coexistence/finish")
def coex_finish(body: CoexDoneIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    return wa_coexist.finish_signup(db, body.code, body.phone_number_id, body.waba_id, user)


@settings_router.post("/whatsapp-coexistence/sync")
def coex_sync(db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    return wa_coexist.start_sync(db, user)

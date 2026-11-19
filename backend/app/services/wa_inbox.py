"""WhatsApp inbox on the official WhatsApp Business Platform (Meta Cloud API).

- The business number is connected to the Cloud API with Coexistence, so the WhatsApp Business
  app on the phone keeps working; messages sent from the phone come back as "echoes" and are
  shown in the same chat (source=phone_app).
- Incoming messages are stored once (unique WhatsApp id); outgoing ones once (unique client_ref),
  so a retried request or job never sends twice.
- A free-form reply is only allowed within 24 hours of the customer's last message
  (Meta's customer service window); after that only an approved template can be sent.
- Media is downloaded by the worker and kept as a media asset under WhatsApp Inbox/<number>.
- Secrets (access token, app secret) come from the server environment or are pasted in Settings
  and stored encrypted; they never reach the browser.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.whatsapp import CloudAPIClient, MockWhatsAppClient, WaSendError
from app.models import (
    FinalVideo, FinalVideoStatus, MediaAsset, MediaCategory, Plaque, Project, Sacrifice, User, WaConversation, WaMessage, utcnow,
)
from app.services import phones, secrets_store
from app.services.audit import audit
from app.services.jobs import enqueue, handler
from app.services.settings_store import get_setting, set_setting

log = logging.getLogger("hayah.wa_inbox")
WINDOW = timedelta(hours=24)
STATUS_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3}
# WhatsApp's own limits per message type
LIMITS = {"image": 5 * 1024 * 1024, "video": 16 * 1024 * 1024, "audio": 16 * 1024 * 1024, "document": 100 * 1024 * 1024}
IMAGE_TYPES = ("image/jpeg", "image/png")
VIDEO_TYPES = ("video/mp4", "video/3gpp")
AUDIO_TYPES = ("audio/aac", "audio/amr", "audio/mpeg", "audio/mp4", "audio/ogg")


# ---------------------------------------------------------------- settings
def config(db: Session) -> dict:
    return get_setting(db, "whatsapp_inbox") or {}


def access_token(db: Session) -> str:
    return get_settings().whatsapp_access_token or secrets_store.get_secret(db, "whatsapp_access_token")


def app_secret(db: Session) -> str:
    return get_settings().whatsapp_app_secret or secrets_store.get_secret(db, "whatsapp_app_secret")


def verify_token(db: Session) -> str:
    return get_settings().whatsapp_verify_token or secrets_store.get_secret(db, "whatsapp_verify_token")


def mock() -> bool:
    return get_settings().whatsapp_backend != "meta"


def enabled(db: Session) -> bool:
    c = config(db)
    return bool(c.get("phone_number_id")) and (mock() or bool(access_token(db)))


def client(db: Session):
    c = config(db)
    if mock():
        return MockWhatsAppClient(waba_id=c.get("waba_id"))
    return CloudAPIClient(token=access_token(db), phone_number_id=c.get("phone_number_id"), waba_id=c.get("waba_id"))


def save_config(db: Session, *, phone_number_id: str, waba_id: str | None, display_number: str | None, user: User,
                access_token_value: str | None = None, app_secret_value: str | None = None, verify_token_value: str | None = None) -> dict:
    before = config(db)
    value = {"phone_number_id": phone_number_id.strip(), "waba_id": (waba_id or "").strip() or None,
             "display_number": (display_number or "").strip() or None}
    set_setting(db, "whatsapp_inbox", value, user.id)
    for name, v in (("whatsapp_access_token", access_token_value), ("whatsapp_app_secret", app_secret_value),
                    ("whatsapp_verify_token", verify_token_value)):
        if v is not None:  # "" clears, None keeps
            secrets_store.set_secret(db, name, v.strip() or None, user.id)
    audit(db, "settings.whatsapp_inbox", "settings", "whatsapp_inbox", actor=user, before=before,
          after={**value, "token_changed": access_token_value is not None, "secret_changed": app_secret_value is not None})
    return status(db)


def status(db: Session) -> dict:
    s = get_settings()
    c = config(db)

    def where(env: str, name: str):
        return "server" if env else ("settings" if secrets_store.get_secret(db, name) else None)
    return {"enabled": enabled(db), "mock": mock(), "phone_number_id": c.get("phone_number_id"), "waba_id": c.get("waba_id"),
            "display_number": c.get("display_number"),
            "access_token": {"where": where(s.whatsapp_access_token, "whatsapp_access_token"),
                             "last4": (access_token(db) or "")[-4:] or None},
            "app_secret": {"where": where(s.whatsapp_app_secret, "whatsapp_app_secret")},
            "verify_token": {"where": where(s.whatsapp_verify_token, "whatsapp_verify_token")},
            "webhook_path": "/webhooks/whatsapp"}


# ---------------------------------------------------------------- conversations
def _digits(p: str | None) -> str:
    return "".join(ch for ch in (p or "") if ch.isdigit())


def get_or_create(db: Session, wa_id: str, name: str | None = None) -> WaConversation:
    wa_id = _digits(wa_id)
    if not wa_id:
        raise HTTPException(422, "No phone number")
    conv = db.scalar(select(WaConversation).where(WaConversation.wa_id == wa_id))
    if conv:
        if name and not conv.contact_name:
            conv.contact_name = name[:200]
        return conv
    conv = WaConversation(wa_id=wa_id, phone_e164="+" + wa_id, contact_name=(name or None) and name[:200])
    try:
        with db.begin_nested():
            db.add(conv)
            db.flush()
    except IntegrityError:
        conv = db.scalar(select(WaConversation).where(WaConversation.wa_id == wa_id))
    _auto_link(db, conv)
    return conv


def orders_for(db: Session, conv: WaConversation) -> list[dict]:
    """Every order with this customer's number (wells and sacrifices), newest first."""
    out = []
    for p in db.scalars(select(Project).where(Project.customer_phone_e164 == conv.phone_e164, Project.merged_into_id.is_(None))
                        .order_by(Project.well_id.desc()).limit(50)):
        pl = db.scalar(select(Plaque).where(Plaque.project_id == p.id))
        out.append({"kind": "well", "number": p.well_id, "id": p.id, "type": p.well_type, "customer_name": p.customer_name,
                    "construction_status": p.construction_status.value, "plaque_status": pl.status.value if pl else None,
                    "linked": conv.project_id == p.id})
    for s in db.scalars(select(Sacrifice).where(Sacrifice.customer_phone_e164 == conv.phone_e164)
                        .order_by(Sacrifice.sacrifice_no.desc()).limit(50)):
        pl = db.scalar(select(Plaque).where(Plaque.sacrifice_id == s.id))
        out.append({"kind": "sacrifice", "number": s.sacrifice_no, "id": s.id, "type": s.animal_type, "customer_name": s.donor_name,
                    "construction_status": None, "plaque_status": pl.status.value if pl else None,
                    "linked": conv.sacrifice_id == s.id})
    return out


def _auto_link(db: Session, conv: WaConversation) -> None:
    """Link a chat to its order when the number belongs to exactly one order. Several: the employee picks."""
    if conv.project_id or conv.sacrifice_id:
        return
    orders = orders_for(db, conv)
    if len(orders) == 1:
        o = orders[0]
        if o["kind"] == "well":
            conv.project_id = o["id"]
        else:
            conv.sacrifice_id = o["id"]


def link(db: Session, conv: WaConversation, kind: str | None, number: int | None, user: User) -> WaConversation:
    before = {"project_id": conv.project_id, "sacrifice_id": conv.sacrifice_id}
    conv.project_id = conv.sacrifice_id = None
    if kind == "well":
        p = db.scalar(select(Project).where(Project.well_id == number))
        if not p:
            raise HTTPException(404, f"No well number {number}")
        conv.project_id = p.id
        from app.services.projects import add_event
        add_event(db, p, "whatsapp_linked", source="dashboard", actor=user, summary=f"WhatsApp chat {conv.phone_e164} linked to this order")
    elif kind == "sacrifice":
        s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == number))
        if not s:
            raise HTTPException(404, f"No sacrifice number {number}")
        conv.sacrifice_id = s.id
    audit(db, "whatsapp.linked", "wa_conversation", conv.id, actor=user, before=before,
          after={"project_id": conv.project_id, "sacrifice_id": conv.sacrifice_id})
    return conv


def assign(db: Session, conv: WaConversation, user_id: int | None, actor: User) -> WaConversation:
    from app.deps import MANAGERS, PROJECT_CREATORS
    manager = actor.role in MANAGERS
    if not manager:
        # an employee can take an unassigned chat, hand over their own, or let it go
        if conv.assigned_to_id not in (None, actor.id):
            raise HTTPException(403, "Only a manager can take a chat that is assigned to someone else")
    if user_id is not None:
        u = db.get(User, user_id)
        if not u or not u.is_active or u.role not in PROJECT_CREATORS:
            raise HTTPException(422, "Choose an active employee or manager")
    before = conv.assigned_to_id
    conv.assigned_to_id = user_id
    conv.updated_at = utcnow()
    audit(db, "whatsapp.assigned", "wa_conversation", conv.id, actor=actor, before={"assigned_to_id": before},
          after={"assigned_to_id": user_id})
    return conv


def set_status(db: Session, conv: WaConversation, to: str, actor: User) -> WaConversation:
    if to not in ("open", "pending", "closed"):
        raise HTTPException(422, "Status is open, pending or closed")
    before = conv.status
    conv.status = to
    conv.updated_at = utcnow()
    audit(db, "whatsapp.status", "wa_conversation", conv.id, actor=actor, before={"status": before}, after={"status": to})
    return conv


def mark_read(db: Session, conv: WaConversation) -> None:
    if not conv.unread:
        return
    conv.unread = 0
    last_in = db.scalar(select(WaMessage).where(WaMessage.conversation_id == conv.id, WaMessage.direction == "in")
                        .order_by(WaMessage.id.desc()).limit(1))
    if last_in and last_in.wa_message_id and enabled(db):
        try:
            client(db).mark_read(last_in.wa_message_id)
        except Exception:  # noqa: BLE001  (read receipts are best effort)
            pass


def window_open(conv: WaConversation) -> bool:
    return bool(conv.last_inbound_at and utcnow() - conv.last_inbound_at < WINDOW)


# ---------------------------------------------------------------- webhook
def _preview(m: WaMessage) -> str:
    if m.text:
        return m.text[:300]
    return {"image": "📷", "video": "🎬", "audio": "🎤", "document": "📄", "sticker": "🙂", "location": "📍",
            "template": "📋"}.get(m.type, m.type)


def _touch(conv: WaConversation, m: WaMessage) -> None:
    if not conv.last_message_at or m.at >= conv.last_message_at:
        conv.last_message_at, conv.last_preview, conv.last_direction = m.at, _preview(m), m.direction
    conv.updated_at = utcnow()


def _content(m: dict) -> tuple[str, str | None, dict]:
    t = m.get("type", "text")
    if t == "text":
        return t, (m.get("text") or {}).get("body"), {}
    if t in ("image", "video", "audio", "document", "sticker"):
        part = m.get(t) or {}
        return t, part.get("caption"), {"wa_media_id": part.get("id"), "mime_type": part.get("mime_type"),
                                        "filename": part.get("filename"), "voice": bool(part.get("voice"))}
    if t == "location":
        loc = m.get("location") or {}
        return t, " ".join(str(x) for x in (loc.get("name"), loc.get("address")) if x) or None, \
            {"latitude": loc.get("latitude"), "longitude": loc.get("longitude")}
    if t == "interactive":
        i = m.get("interactive") or {}
        return "text", (i.get("button_reply") or i.get("list_reply") or {}).get("title"), {}
    if t == "button":
        return "text", (m.get("button") or {}).get("text"), {}
    if t == "reaction":
        r = m.get("reaction") or {}
        return t, r.get("emoji"), {"to": r.get("message_id")}
    if t == "contacts":
        names = [((c.get("name") or {}).get("formatted_name") or "") for c in m.get("contacts") or []]
        return t, "👤 " + ", ".join(n for n in names if n), {"contacts": m.get("contacts")}
    return t, None, {}


def _ts(m: dict) -> datetime:
    try:
        return datetime.fromtimestamp(int(m.get("timestamp") or 0), tz=timezone.utc) if m.get("timestamp") else utcnow()
    except (TypeError, ValueError):
        return utcnow()


def _store(db: Session, conv: WaConversation, m: dict, direction: str, source: str) -> WaMessage | None:
    if db.scalar(select(WaMessage.id).where(WaMessage.wa_message_id == m["id"])):
        return None  # already stored (Meta re-sends webhooks)
    typ, text, media = _content(m)
    msg = WaMessage(conversation_id=conv.id, direction=direction, wa_message_id=m["id"], type=typ, text=text, media=media,
                    status="received" if direction == "in" else "sent", source=source, at=_ts(m),
                    reply_to_wa_id=(m.get("context") or {}).get("id"),
                    sent_by_label="WhatsApp Business app" if source == "phone_app" else None)
    try:
        with db.begin_nested():
            db.add(msg)
            db.flush()
    except IntegrityError:
        return None
    _touch(conv, msg)
    if media.get("wa_media_id"):
        enqueue(db, "wa_media", {"message_id": msg.id}, key=f"wa_media:{msg.id}")
    return msg


def handle_webhook(db: Session, payload: dict) -> set[str]:
    """Store what belongs to the inbox number. Returns the WhatsApp ids it took, so the intake
    pipeline (the team's forwarding number) skips them."""
    inbox_id = config(db).get("phone_number_id")
    taken: set[str] = set()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            field, value = change.get("field"), change.get("value") or {}
            to_id = (value.get("metadata") or {}).get("phone_number_id")
            # message statuses for anything we sent from the inbox
            for st in value.get("statuses") or []:
                _status_update(db, st)
            if not inbox_id or to_id != inbox_id:
                continue
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            if field in (None, "messages"):
                for m in value.get("messages") or []:
                    conv = get_or_create(db, m.get("from"), names.get(m.get("from")))
                    msg = _store(db, conv, m, "in", "cloud_api")
                    taken.add(m["id"])
                    if msg:
                        conv.unread = (conv.unread or 0) + (0 if msg.type == "reaction" else 1)
                        if not conv.last_inbound_at or msg.at > conv.last_inbound_at:
                            conv.last_inbound_at = msg.at
                        if conv.status == "closed":
                            conv.status = "open"  # a customer writing again reopens the chat
            elif field == "smb_message_echoes":  # sent from the WhatsApp Business app on the phone (Coexistence)
                for m in value.get("message_echoes") or []:
                    conv = get_or_create(db, m.get("to"))
                    _store(db, conv, m, "out", "phone_app")
                    taken.add(m["id"])
    db.flush()
    return taken


def _status_update(db: Session, st: dict) -> None:
    msg = db.scalar(select(WaMessage).where(WaMessage.wa_message_id == st.get("id")))
    if not msg:
        return
    new = st.get("status")
    if new == "failed":
        errs = st.get("errors") or [{}]
        e = errs[0]
        msg.status = "failed"
        msg.error = f"{e.get('title') or e.get('message') or 'Failed'}" + (f" (code {e.get('code')})" if e.get("code") else "") + \
            (f": {(e.get('error_data') or {}).get('details')}" if (e.get("error_data") or {}).get("details") else "")
    elif new in STATUS_RANK and STATUS_RANK[new] > STATUS_RANK.get(msg.status, -1):
        msg.status = new  # never go backwards (webhooks can arrive out of order)
    else:
        return
    msg.status_at = _ts(st)


@handler("wa_media")
def _download_media(db: Session, payload: dict) -> dict:
    msg = db.get(WaMessage, payload["message_id"])
    if not msg or msg.media_asset_id or not (msg.media or {}).get("wa_media_id"):
        return {"skipped": True}
    conv = db.get(WaConversation, msg.conversation_id)
    data, mime = client(db).download_media(msg.media["wa_media_id"])
    from app.services.media import store_media
    name = msg.media.get("filename") or f"{msg.type}"
    asset, _ = store_media(db, io.BytesIO(data), original_filename=name, mime_type=msg.media.get("mime_type") or mime,
                           project=None, category=MediaCategory.other, source="whatsapp_inbox",
                           sender=conv.phone_e164, inbox_chat=conv.wa_id)
    msg.media_asset_id = asset.id
    msg.media = {**msg.media, "size": asset.size_bytes}
    return {"asset_id": asset.id}


# ---------------------------------------------------------------- sending
def _kind_for(mime: str, size: int) -> str:
    if mime in IMAGE_TYPES and size <= LIMITS["image"]:
        return "image"
    if mime in VIDEO_TYPES and size <= LIMITS["video"]:
        return "video"
    if mime in AUDIO_TYPES and size <= LIMITS["audio"]:
        return "audio"
    if size <= LIMITS["document"]:
        return "document"
    raise HTTPException(413, "WhatsApp accepts files up to 100 MB. Share a download link for bigger videos.")


def send(db: Session, conv: WaConversation, actor: User, *, client_ref: str, text: str | None = None,
         asset: MediaAsset | None = None, caption: str | None = None, template: dict | None = None,
         reply_to: str | None = None) -> WaMessage:
    if not enabled(db):
        raise HTTPException(409, "WhatsApp is not connected yet (Settings → WhatsApp)")
    existing = db.scalar(select(WaMessage).where(WaMessage.client_ref == client_ref))
    if existing:  # the same request again (double click, retry): never send twice
        return existing
    if not template and not window_open(conv):
        raise HTTPException(409, "More than 24 hours since the customer's last message: WhatsApp only allows an approved "
                                 "template now. Choose a template.")
    if not template and not asset and not (text or "").strip():
        raise HTTPException(422, "Write a message or attach a file")
    typ, media = "text", {}
    if template:
        typ = "template"
    elif asset:
        typ = _kind_for(asset.mime_type, asset.size_bytes)
        media = {"mime_type": asset.mime_type, "filename": asset.original_filename or asset.filename, "size": asset.size_bytes}
    msg = WaMessage(conversation_id=conv.id, direction="out", client_ref=client_ref, type=typ,
                    text=(caption if asset else text) or (template or {}).get("preview"), media=media,
                    media_asset_id=asset.id if asset else None, template=template, status="queued", source="cloud_api",
                    sent_by_id=actor.id, sent_by_label=actor.full_name, reply_to_wa_id=reply_to, at=utcnow())
    db.add(msg)
    db.flush()
    _touch(conv, msg)
    try:
        deliver(db, msg)
    except WaSendError as e:
        if e.transient:  # try again in the background; the message keeps its place in the chat
            msg.error = str(e)
            enqueue(db, "wa_send", {"message_id": msg.id}, key=f"wa_send:{msg.id}", max_attempts=5)
        else:
            msg.status, msg.error = "failed", str(e)
    audit(db, "whatsapp.sent", "wa_message", msg.id, actor=actor,
          after={"to": conv.phone_e164, "type": typ, "status": msg.status, "asset_id": msg.media_asset_id,
                 "template": (template or {}).get("name")})
    return msg


def deliver(db: Session, msg: WaMessage) -> None:
    """Send one queued message. Safe to call again: a message that has a WhatsApp id is never re-sent."""
    if msg.wa_message_id or msg.status in ("sent", "delivered", "read"):
        return
    conv = db.get(WaConversation, msg.conversation_id)
    c = client(db)
    msg.attempts = (msg.attempts or 0) + 1
    payload: dict = {"to": conv.wa_id}
    if msg.reply_to_wa_id:
        payload["context"] = {"message_id": msg.reply_to_wa_id}
    if msg.type == "template":
        t = msg.template or {}
        comp = [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in t.get("params") or []]}] if t.get("params") else []
        payload.update(type="template", template={"name": t["name"], "language": {"code": t.get("language") or "ar"},
                                                  **({"components": comp} if comp else {})})
    elif msg.type == "text":
        payload.update(type="text", text={"body": msg.text, "preview_url": True})
    else:
        wa_media = (msg.media or {}).get("wa_media_id")
        if not wa_media:  # upload once, remember the id so a retry does not upload again
            a = db.get(MediaAsset, msg.media_asset_id)
            from app.integrations.drive import get_drive_client
            data = get_drive_client().download(a.drive_file_id)
            wa_media = c.upload_media(data, a.mime_type, (msg.media or {}).get("filename") or a.filename)
            msg.media = {**(msg.media or {}), "wa_media_id": wa_media}
            db.flush()
        part: dict = {"id": wa_media}
        if msg.text and msg.type in ("image", "video", "document"):
            part["caption"] = msg.text[:1024]
        if msg.type == "document":
            part["filename"] = (msg.media or {}).get("filename") or "file"
        payload.update(type=msg.type, **{msg.type: part})
    wid = c.send(payload)
    msg.wa_message_id, msg.status, msg.status_at, msg.error = wid, "sent", utcnow(), None
    _after_sent(db, conv, msg)


def _after_sent(db: Session, conv: WaConversation, msg: WaMessage) -> None:
    """Sending an order's final video or plaque on WhatsApp is part of the order's history."""
    if not msg.media_asset_id:
        return
    a = db.get(MediaAsset, msg.media_asset_id)
    if a.category not in (MediaCategory.final_video, MediaCategory.plaque):
        return
    actor = db.get(User, msg.sent_by_id) if msg.sent_by_id else None
    if a.project_id:
        from app.services.projects import add_event
        p = db.get(Project, a.project_id)
        add_event(db, p, "whatsapp_sent", source="dashboard", actor=actor,
                  summary=f"Sent on WhatsApp to {conv.phone_e164}: {a.filename}", payload={"wa_message_id": msg.id, "media_id": a.id})
    if a.category == MediaCategory.final_video:
        fv = db.scalar(select(FinalVideo).where(FinalVideo.current_media_id == a.id))
        if fv and fv.status in (FinalVideoStatus.uploaded, FinalVideoStatus.ready_for_delivery) and actor:
            rec = db.get(Project, fv.project_id) if fv.project_id else db.get(Sacrifice, fv.sacrifice_id)
            from app.services import final_video
            if fv.status == FinalVideoStatus.uploaded:
                final_video.set_status(db, rec, FinalVideoStatus.ready_for_delivery, actor)
            final_video.set_status(db, rec, FinalVideoStatus.sent_to_customer, actor, f"WhatsApp {conv.phone_e164}")


@handler("wa_send")
def _send_job(db: Session, payload: dict) -> dict:
    msg = db.get(WaMessage, payload["message_id"])
    if not msg or msg.wa_message_id:
        return {"skipped": True}
    try:
        deliver(db, msg)
    except WaSendError as e:
        msg.error = str(e)
        if not e.transient or (msg.attempts or 0) >= 5:
            msg.status = "failed"
            return {"failed": str(e)}
        db.commit()  # keep the attempt count, then let the queue retry with backoff
        raise
    return {"sent": msg.wa_message_id}


def retry(db: Session, msg: WaMessage, actor: User) -> WaMessage:
    """Send a failed message again, by hand. It keeps the same message (no duplicate in the chat)."""
    if msg.status != "failed" or msg.wa_message_id:
        raise HTTPException(409, "Only a failed message that WhatsApp never accepted can be sent again")
    conv = db.get(WaConversation, msg.conversation_id)
    if msg.type != "template" and not window_open(conv):
        raise HTTPException(409, "More than 24 hours since the customer's last message: send a template instead")
    msg.status, msg.error = "queued", None
    try:
        deliver(db, msg)
    except WaSendError as e:
        msg.status, msg.error = "failed", str(e)
    audit(db, "whatsapp.retry", "wa_message", msg.id, actor=actor, after={"status": msg.status})
    return msg


# ---------------------------------------------------------------- reading
def conv_row(db: Session, c: WaConversation, users: dict[int, str] | None = None) -> dict:
    users = users or {}
    order = None
    if c.project_id:
        p = db.get(Project, c.project_id)
        pl = db.scalar(select(Plaque).where(Plaque.project_id == p.id))
        order = {"kind": "well", "number": p.well_id, "type": p.well_type, "plaque_status": pl.status.value if pl else None}
    elif c.sacrifice_id:
        s = db.get(Sacrifice, c.sacrifice_id)
        pl = db.scalar(select(Plaque).where(Plaque.sacrifice_id == s.id))
        order = {"kind": "sacrifice", "number": s.sacrifice_no, "type": s.animal_type, "plaque_status": pl.status.value if pl else None}
    return {"id": c.id, "phone": c.phone_e164, "name": c.contact_name, "status": c.status,
            "assigned_to_id": c.assigned_to_id, "assigned_to": users.get(c.assigned_to_id) if c.assigned_to_id else None,
            "order": order, "unread": c.unread or 0, "last_message_at": c.last_message_at, "last_preview": c.last_preview,
            "last_direction": c.last_direction, "waiting_reply": c.status != "closed" and c.last_direction == "in",
            "window_open": window_open(c),
            "window_ends_at": (c.last_inbound_at + WINDOW) if c.last_inbound_at else None,
            "plaque_unconfirmed": bool(order and order["plaque_status"] and order["plaque_status"] not in
                                       ("approved_for_contractor", "sent_to_contractor", "customer_approved"))}


def _users(db: Session) -> dict[int, str]:
    return {u.id: u.full_name for u in db.scalars(select(User))}


def list_conversations(db: Session, me: User, *, box: str = "all", q: str | None = None, limit: int = 200) -> list[dict]:
    query = select(WaConversation).order_by(WaConversation.last_message_at.desc().nullslast()).limit(limit)
    if box == "mine":
        query = query.where(WaConversation.assigned_to_id == me.id, WaConversation.status != "closed")
    elif box == "unassigned":
        query = query.where(WaConversation.assigned_to_id.is_(None), WaConversation.status != "closed")
    elif box == "unread":
        query = query.where(WaConversation.unread > 0)
    elif box == "waiting":
        query = query.where(WaConversation.status != "closed", WaConversation.last_direction == "in")
    elif box in ("open", "pending", "closed"):
        query = query.where(WaConversation.status == box)
    if q and q.strip():
        term = q.strip()
        digits = _digits(term)
        conds = [WaConversation.contact_name.ilike(f"%{term}%"), WaConversation.last_preview.ilike(f"%{term}%")]
        if digits:
            conds.append(WaConversation.wa_id.like(f"%{digits}%"))
            if digits.isdigit() and len(digits) <= 7:  # an order number
                pids = select(Project.id).where(Project.well_id == int(digits))
                sids = select(Sacrifice.id).where(Sacrifice.sacrifice_no == int(digits))
                conds += [WaConversation.project_id.in_(pids), WaConversation.sacrifice_id.in_(sids)]
        query = query.where(or_(*conds))
    users = _users(db)
    return [conv_row(db, c, users) for c in db.scalars(query)]


def counts(db: Session) -> dict:
    live = WaConversation.status != "closed"
    return {"unread_messages": db.scalar(select(func.coalesce(func.sum(WaConversation.unread), 0))) or 0,
            "unread_chats": db.scalar(select(func.count()).select_from(WaConversation).where(WaConversation.unread > 0)) or 0,
            "waiting_reply": db.scalar(select(func.count()).select_from(WaConversation).where(live, WaConversation.last_direction == "in")) or 0,
            "unassigned": db.scalar(select(func.count()).select_from(WaConversation).where(live, WaConversation.assigned_to_id.is_(None))) or 0}


def msg_row(m: WaMessage, sign) -> dict:
    return {"id": m.id, "direction": m.direction, "type": m.type, "text": m.text, "status": m.status, "error": m.error,
            "source": m.source, "sent_by": m.sent_by_label, "at": m.at, "status_at": m.status_at,
            "media": {k: v for k, v in (m.media or {}).items() if k in ("mime_type", "filename", "size", "voice", "latitude", "longitude")},
            "file": sign(m.id) if m.media_asset_id else None, "media_pending": bool((m.media or {}).get("wa_media_id")) and not m.media_asset_id
            and m.direction == "in", "template": (m.template or {}).get("name"), "reply_to": m.reply_to_wa_id, "wa_id": m.wa_message_id}


def find_by_phone(db: Session, phone: str) -> WaConversation:
    """Open (or start) the chat for a customer's number, e.g. from an order page."""
    r = phones.normalize(phone)
    if r["status"] != "valid":
        raise HTTPException(422, "This is not a valid international number")
    return get_or_create(db, r["e164"])

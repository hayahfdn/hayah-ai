import hmac
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import FIELD_WRITERS, MANAGERS, require_roles
from app.integrations.whatsapp import parse_webhook, verify_signature
from app.models import InboundMessage, User, utcnow
from app.schemas import ManualMessageIn
from app.services import wa_inbox
from app.services.intake import process_message, store_inbound

router = APIRouter(tags=["intake"])


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def verify(hub_mode: str = Query(None, alias="hub.mode"), hub_verify_token: str = Query(None, alias="hub.verify_token"),
           hub_challenge: str = Query(None, alias="hub.challenge"), db: Session = Depends(get_db)):
    expected = wa_inbox.verify_token(db)
    if hub_mode == "subscribe" and expected and hmac.compare_digest(hub_verify_token or "", expected):
        return hub_challenge or ""
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp")
async def receive(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(413, "Payload too large")
    secret = wa_inbox.app_secret(db)
    if secret:
        if not verify_signature(body, request.headers.get("X-Hub-Signature-256"), secret):
            raise HTTPException(401, "Bad signature")
    elif s.env == "production":
        raise HTTPException(503, "Webhook secret not configured")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    stored = 0
    taken = wa_inbox.handle_webhook(db, payload)  # customer chats on the business number (inbox)
    for m in parse_webhook(payload):
        if m["external_id"] in taken:
            continue
        _, created = store_inbound(db, m)
        stored += created
    db.commit()
    return {"received": stored}  # always 200 quickly; processing happens in the worker


@router.post("/api/intake/manual")
def manual(body: ManualMessageIn, db: Session = Depends(get_db), user: User = Depends(require_roles(FIELD_WRITERS))):
    """Paste a message from a WhatsApp group by hand. Same pipeline, processed immediately."""
    text = f"#{body.group_label} {body.text}" if body.group_label else body.text
    msg, _ = store_inbound(db, {"external_id": f"manual-{uuid.uuid4()}", "sender_phone": body.sender_phone or user.phone,
                                "sender_name": body.sender_name or user.full_name, "received_at": utcnow(),
                                "text": text, "group_label": body.group_label}, channel="manual")
    if not body.sender_phone:
        msg.sender_user_id = user.id
    status = process_message(db, msg)
    db.commit()
    return {"message_id": msg.id, "status": status, "extraction": msg.extraction}


@router.get("/api/intake/messages")
def messages(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    q = select(InboundMessage).order_by(InboundMessage.received_at.desc()).limit(200)
    if status:
        q = q.where(InboundMessage.processing_status == status)
    return [{"id": m.id, "channel": m.channel, "group": m.group_label, "sender": m.sender_name or m.sender_phone,
             "received_at": m.received_at, "text": m.text, "status": m.processing_status, "project_id": m.project_id,
             "media_count": len(m.media or [])} for m in db.scalars(q)]

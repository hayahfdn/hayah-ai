"""Turns an inbound operational message into safe, auditable actions.

Rules:
- Every message is stored raw first (idempotent on the WhatsApp message id).
- A Well ID is never guessed. Unless exactly one explicit Well ID matches an
  existing project with high confidence, the message becomes a Pending Review case.
- Delivery messages only create a *pending* confirmation; a manager approves it.
- Automatic updates are only applied for senders registered as active users.
"""
import io
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.ai import extract_message
from app.integrations.whatsapp import get_whatsapp_client
from app.models import (
    ConstructionStatus, InboundMessage, MediaCategory, ReviewCase, ReviewKind, Role, User, VideoStatus, utcnow,
)
from app.services import delivery as delivery_service
from app.services import maintenance as maintenance_service
from app.services import projects as project_service
from app.services.audit import audit
from app.services.jobs import enqueue, handler
from app.services.settings_store import get_setting

# "#B ...", "[B] ...", "Group B: ...", "مجموعة ب ...", "B: ..."
GROUP_TAG = re.compile(r"^\s*(?:(?:#|\[|group\s*|grp\s*|مجموعة\s*)\s*([ABCDabcd]|أ|ب|ج|د)\s*\]?\s*[:\-]?|([ABCD])\s*:)\s+",
                       re.IGNORECASE)
AR_GROUP = {"أ": "A", "ب": "B", "ج": "C", "د": "D"}
CATEGORY_BY_GROUP = {"A": MediaCategory.construction, "B": MediaCategory.delivery, "C": MediaCategory.final_video,
                     "D": MediaCategory.maintenance}


def detect_group(text: str | None) -> tuple[str | None, str | None]:
    if not text:
        return None, text
    m = GROUP_TAG.match(text + " ")
    if not m:
        return None, text
    raw = m.group(1) or m.group(2)
    return AR_GROUP.get(raw, raw.upper()), (text + " ")[m.end():].strip()


def normalize_phone(p: str | None) -> str | None:
    return re.sub(r"\D", "", p) if p else None


def find_sender(db: Session, phone: str | None) -> User | None:
    n = normalize_phone(phone)
    if not n:
        return None
    for u in db.scalars(select(User).where(User.is_active.is_(True), User.phone.is_not(None))):
        if normalize_phone(u.phone) == n:
            return u
    return None


def store_inbound(db: Session, m: dict, channel: str = "whatsapp_intake") -> tuple[InboundMessage, bool]:
    existing = db.scalar(select(InboundMessage).where(InboundMessage.external_id == m["external_id"]))
    if existing:
        return existing, False
    group, _ = detect_group(m.get("text"))
    sender = find_sender(db, m.get("sender_phone"))
    msg = InboundMessage(channel=channel, external_id=m["external_id"], group_label=m.get("group_label") or group,
                         sender_phone=m.get("sender_phone"), sender_name=m.get("sender_name") or (sender.full_name if sender else None),
                         sender_user_id=sender.id if sender else None, received_at=m.get("received_at") or utcnow(),
                         message_type=m.get("message_type", "text"), text=m.get("text"), media=m.get("media") or [],
                         raw=m.get("raw") or {})
    try:
        with db.begin_nested():
            db.add(msg)
            db.flush()
    except IntegrityError:
        return db.scalar(select(InboundMessage).where(InboundMessage.external_id == m["external_id"])), False
    audit(db, "inbound.received", "inbound_message", msg.id, actor_label=msg.sender_phone or channel,
          after={"external_id": msg.external_id, "group": msg.group_label, "type": msg.message_type})
    enqueue(db, "process_inbound", {"message_id": msg.id}, key=f"process_inbound:{msg.id}")
    return msg, True


def _review(db: Session, msg: InboundMessage, reason: str, ex: dict, kind=ReviewKind.unassigned_message, project=None):
    msg.processing_status = "needs_review"
    try:
        with db.begin_nested():
            db.add(ReviewCase(kind=kind, reason=reason, inbound_message_id=msg.id, project_id=project.id if project else None,
                              proposed=ex, dedupe_key=f"msg:{msg.id}"))
    except IntegrityError:
        pass


def process_message(db: Session, msg: InboundMessage) -> str:
    if msg.processing_status not in ("received", "retry"):
        return msg.processing_status
    _, body = detect_group(msg.text)
    ex = extract_message(db, body or "", msg.group_label, has_media=bool(msg.media))
    msg.extraction = ex.model_dump(mode="json")
    min_conf = float(get_setting(db, "ai").get("min_confidence", 0.9))
    sender = db.get(User, msg.sender_user_id) if msg.sender_user_id else None
    project = project_service.get_by_well_id(db, ex.well_id) if ex.well_id else None
    if project:
        msg.project_id = project.id
    if ex.well_id and not project:
        _review(db, msg, f"Well ID {ex.well_id} is not in the system (new project needs a person)", msg.extraction)
    elif ex.requires_human_review or ex.confidence < min_conf or not project:
        reason = "; ".join(ex.conflicts + [f"missing: {', '.join(ex.missing_fields)}"] * bool(ex.missing_fields)) \
            or "Low confidence"
        _review(db, msg, reason, msg.extraction, kind=ReviewKind.ai_extraction if project else ReviewKind.unassigned_message,
                project=project)
    elif ex.event_type == "delivery_confirmation":
        delivery_service.create_pending(db, project, delivery_date=msg.received_at.date(), source="whatsapp", message=msg,
                                        notes=msg.text)
        msg.processing_status = "pending_approval"
    elif not sender or sender.role == Role.viewer:
        _review(db, msg, "Sender is not a registered team member, so nothing was changed automatically",
                msg.extraction, kind=ReviewKind.ai_extraction, project=project)
    else:
        try:
            with db.begin_nested():
                apply_extraction(db, project, ex.event_type, msg.extraction, actor=sender, msg=msg)
            msg.processing_status = "applied"
        except (PermissionError, HTTPException) as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            _review(db, msg, f"Could not apply automatically: {detail}", msg.extraction,
                    kind=ReviewKind.ai_extraction, project=project)
    if msg.media:
        for i, item in enumerate(msg.media):
            enqueue(db, "whatsapp_media", {"message_id": msg.id, "index": i}, key=f"wa_media:{msg.id}:{i}")
    if msg.processing_status in ("received", "retry"):
        msg.processing_status = "logged"
    return msg.processing_status


def apply_extraction(db: Session, project, event_type: str, ex: dict, *, actor: User, msg: InboundMessage | None):
    key = f"msg:{msg.id}" if msg else None
    if event_type == "construction_update" and ex.get("construction", {}).get("construction_status"):
        status = ConstructionStatus(ex["construction"]["construction_status"])
        if actor.role == Role.contractor and project.contractor_id != actor.contractor_id:
            raise PermissionError("Contractor is not assigned to this project")
        project_service.update_project(db, project, {"construction_status": status}, actor=actor, source="whatsapp")
    elif event_type == "maintenance_report":
        m = ex.get("maintenance") or {}
        maintenance_service.create_record(db, project, {"date": (msg.received_at.date() if msg else utcnow().date()),
                                                        "problem_type": m.get("problem_type") or "reported_issue",
                                                        "description": m.get("description")},
                                          actor=actor, source="whatsapp", inbound_message_id=msg.id if msg else None)
    elif event_type == "final_video" and (ex.get("final_video") or {}).get("video_url"):
        project_service.update_project(db, project, {"final_video_link": ex["final_video"]["video_url"],
                                                     "video_status": VideoStatus.completed}, actor=actor, source="whatsapp")
    elif event_type == "delivery_confirmation":
        delivery_service.create_pending(db, project, delivery_date=msg.received_at.date() if msg else None,
                                        source="whatsapp" if msg else "dashboard", message=msg, requested_by=actor)
        return
    project_service.add_event(db, project, "whatsapp_message", source="whatsapp", actor_label=msg.sender_name if msg else None,
                              summary=(msg.text or "")[:300] if msg else None, payload={"message_id": msg.id if msg else None,
                                                                                        "event_type": event_type},
                              idempotency_key=key)


@handler("process_inbound")
def _process_job(db: Session, payload: dict):
    msg = db.get(InboundMessage, payload["message_id"])
    if msg:
        process_message(db, msg)


@handler("whatsapp_media")
def _media_job(db: Session, payload: dict):
    from app.services.media import store_media
    msg = db.get(InboundMessage, payload["message_id"])
    item = msg.media[payload["index"]]
    content, mime = get_whatsapp_client().download_media(item["id"])
    project = db.get(__import__("app.models", fromlist=["Project"]).Project, msg.project_id) if msg.project_id else None
    category = CATEGORY_BY_GROUP.get(msg.group_label or "", MediaCategory.construction)
    store_media(db, io.BytesIO(content), original_filename=item.get("filename"), mime_type=item.get("mime_type") or mime,
                project=project, category=category, source="whatsapp", sender=msg.sender_name or msg.sender_phone,
                inbound_message_id=msg.id, captured_at=msg.received_at)

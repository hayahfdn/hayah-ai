"""The WhatsApp button on an order's prepared plaque (Hayah, 19 Nov 2026).

Nothing is sent automatically. The employee taps the WhatsApp icon: WhatsApp opens on the
customer's number (wa.me) with this message ready, and the plaque image is downloaded so it
can be attached:

    السلام عليكم
    تم استلام طلبك وإعداد اللوحة سيتم التنفيذ ان شاء الله خلال <المدة>

The time depends on the order: 48 hours for sacrifices, 10 days for hand-pump and medium
wells, 15 days for deep wells and 20 days for solar wells.

The tap is logged on the order and moves the plaque to "awaiting customer approval".
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import PlaqueStatus as S, Plaque, Project, User
from app.services import plaque_flow as flow

# Hayah's times, written as she wrote them
WELL_TIMES = {"يدوي": "١٠ أيام", "متوسط": "١٠ أيام", "عميق": "١٥ يوم", "شمسي": "٢٠ يوم"}
SACRIFICE_TIME = "٤٨ ساعة"
TEXT = "السلام عليكم\nتم استلام طلبك وإعداد اللوحة سيتم التنفيذ ان شاء الله خلال {time}"
# Opening WhatsApp for the customer moves the plaque on from these states
TO_CUSTOMER = {S.draft: [S.ready_for_review, S.awaiting_customer], S.ready_for_review: [S.awaiting_customer],
               S.needs_changes: [S.awaiting_customer]}


def delivery_time(rec) -> str | None:
    if isinstance(rec, Project):
        return WELL_TIMES.get(rec.well_type or "")
    return SACRIFICE_TIME


def message_text(rec) -> str | None:
    t = delivery_time(rec)
    return TEXT.format(time=t) if t else None


def info(db: Session, pl: Plaque, rec=None) -> dict:
    """Shown with every plaque, so the button is ready without another request."""
    rec = rec or flow.record_of(db, pl)
    problems = []
    if pl.missing:
        problems.append("missing")
    if not flow._has_file(db, pl):
        problems.append("no_file")
    if not rec.customer_phone_e164:
        problems.append("no_phone")
    if not delivery_time(rec):
        problems.append("no_time")  # a well without one of the four types
    return {"text": message_text(rec), "time": delivery_time(rec), "phone": rec.customer_phone_e164, "problems": problems}


def opened(db: Session, pl: Plaque, actor: User) -> dict:
    """The employee opened WhatsApp on the customer's number: log it and move the plaque on."""
    rec = flow.record_of(db, pl)
    w = info(db, pl, rec)
    if w["problems"]:
        raise HTTPException(409, "Not ready to send: " + ", ".join(w["problems"]))
    moves = TO_CUSTOMER.get(pl.status, [])
    for to in moves:
        flow.set_status(db, pl, to, actor, "WhatsApp")
    if not moves:  # already with the customer or approved: just note that it was sent again
        flow._log(db, pl, rec, "plaque_whatsapp", actor, f"Plaque sent to the customer on WhatsApp ({w['phone']})",
                  {"phone": w["phone"], "status": pl.status.value})
    return flow.row(db, pl, rec)

"""«شهادة وقفية»: the endowment certificate for a well, drawn in the browser like the plaques.

The server gives the certificate's default text from the order (donor names, project type,
opening month and year, well number, country) and keeps the last edited design as a timeline
event (certificate_saved), so no new table is needed. Sending is logged the same way
(certificate_sent). No cost or finance figure is ever part of it.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plaque, PlaqueVersion, Project, ProjectEvent, User
from app.services import final_video as fv
from app.services.projects import add_event

MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
SAVED, SENT = "certificate_saved", "certificate_sent"


def project_type(well_type: str | None) -> str:
    if well_type == "شمسي":
        return "حفر بئر مياه بالطاقة الشمسية"
    return "حفر بئر مياه"


def donor_names(db: Session, p: Project) -> str:
    """The name on the plaque when there is one (staff have already checked it), else the order's."""
    pl = db.scalar(select(Plaque).where(Plaque.project_id == p.id))
    if pl and pl.current_version_id:
        v = db.get(PlaqueVersion, pl.current_version_id)
        name = (v.design or {}).get("name") if v else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    return (p.dedication or p.customer_name or "").strip()


def opening(p: Project) -> tuple[date, bool]:
    """Opening date: delivery, then completion. Without either, this month, marked as a guess."""
    d = p.delivery_date or p.completion_date
    return (d, False) if d else (date.today(), True)


def defaults(db: Session, p: Project) -> dict:
    d, guessed = opening(p)
    return {
        "names": donor_names(db, p), "project_type": project_type(p.well_type),
        "month": MONTHS_AR[d.month - 1], "year": str(d.year), "date_guessed": guessed,
        "number": str(p.well_id), "country": p.country or "", "well_type": p.well_type,
    }


def _last(db: Session, p: Project, event: str) -> ProjectEvent | None:
    return db.scalar(select(ProjectEvent).where(ProjectEvent.project_id == p.id, ProjectEvent.event_type == event)
                     .order_by(ProjectEvent.created_at.desc()).limit(1))


def data(db: Session, p: Project) -> dict:
    saved, sent = _last(db, p, SAVED), _last(db, p, SENT)
    video = fv.data(db, p)
    cur = next((v for v in video["versions"] if v["current"]), None)
    return {
        "number": p.well_id, "defaults": defaults(db, p),
        "design": (saved.payload or {}).get("design") if saved else None,
        "saved_at": saved.created_at if saved else None, "saved_by": saved.actor_label if saved else None,
        "sent_at": sent.created_at if sent else None, "sent_by": sent.actor_label if sent else None,
        "customer_name": p.customer_name, "customer_phone_e164": p.customer_phone_e164,
        "customer_phone_status": p.customer_phone_status,
        "video": {"status": video["status"], "media_id": cur["media_id"] if cur else None,
                  "mime_type": cur["mime_type"] if cur else None, "filename": cur["filename"] if cur else None,
                  "size_bytes": cur["size_bytes"] if cur else None},
    }


def save(db: Session, p: Project, design: dict, actor: User) -> None:
    add_event(db, p, SAVED, source="dashboard", actor=actor, summary="حفظ الشهادة الوقفية", payload={"design": design})


def log_sent(db: Session, p: Project, actor: User, *, with_video: bool, method: str) -> None:
    what = "الشهادة الوقفية والفيديو" if with_video else "الشهادة الوقفية"
    add_event(db, p, SENT, source="dashboard", actor=actor, summary=f"إرسال {what} للعميل على واتساب",
              payload={"with_video": with_video, "method": method, "phone": p.customer_phone_e164})

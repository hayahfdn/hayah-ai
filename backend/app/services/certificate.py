"""«شهادة وقفية»: the endowment certificate for a well, drawn in the browser like the plaques.

The server gives the certificate's default text from the order (donor names, project type,
opening month and year, well number, country) and keeps the last edited design as a timeline
event (certificate_saved), so no new table is needed. Sending is logged the same way
(certificate_sent). No cost or finance figure is ever part of it.
"""
from __future__ import annotations

import re
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


# Hayah's rule (2026-11-20): the certificate shows the names only, one per line. No title, no kinship,
# no "late", no prayer. Words are matched whole (with or without tashkeel); genealogical بن / بنت / ابن
# inside a name and kunyas such as أبو محمد / أم أحمد are kept, they are part of the name.
_KIN = ("والد|والدة|والدت|اب|أب|ام|أم|جد|جدة|جدت|زوج|زوجة|زوجت|ابن|ابنة|ابنت|بنت|اخ|أخ|اخت|أخت|خال|خالة|خالت|عم|عمة|عمت"
        "|حبيب|حبيبة|حبيبت|صديق|صديقة|صديقت|جار|جارة|جارت|عائلت|اسرت|أسرت|اهل|أهل|اولاد|أولاد|ابناء|أبناء|بنات|اخوان|إخوان|اخوة|إخوة|اخوات|أخوات")
_KIN_RE = re.compile(rf"^(?:{_KIN})(?:ي|ه|ها|نا|هم|كم|ك|يه|ته|تي|تها|تنا)$|^(?:والدي|والديه|والديها|والدينا|والداي|والدي)$")
_TITLES = {
    "المرحوم", "المرحومة", "المرحومه", "المغفور", "المغفورة", "له", "لها", "لهم", "الفقيد", "الفقيدة", "المتوفى", "المتوفي",
    "المتوفاة", "الراحل", "الراحلة", "الشهيد", "الشهيدة", "السيد", "السيدة", "سيد", "سيدة", "الحاج", "الحاجة", "الحاجه", "حاج", "حجي",
    "الشيخ", "الشيخة", "الأستاذ", "الاستاذ", "الأستاذة", "الاستاذة", "الدكتور", "الدكتورة", "د", "د.", "دكتور", "المهندس", "المهندسة",
    "م.", "الأخ", "الاخ", "الأخت", "الاخت", "الآنسة", "الانسة", "الطفل", "الطفلة", "المولود", "المولودة", "الغالي", "الغالية",
    "روح", "لروح", "عن", "على", "الى", "إلى", "لـ", "ل", "صدقة", "صدقه", "جارية", "جاريه", "وقف", "وقفية", "إهداء", "اهداء",
    "رحمه", "رحمها", "رحمهم", "رحمهما", "يرحمه", "يرحمها", "حفظه", "حفظها", "حفظهم", "تغمده", "تغمدها", "mr", "mrs", "ms", "miss", "dr", "dr.", "late",
    "the", "haji", "hajja", "sheikh", "for", "in", "memory", "of",
}
_TASH = re.compile(r"[\u064b-\u0652\u0640]")
# prayers written after a name ("رحمه الله", "حفظها الله"...), removed as whole phrases so that a name
# such as عبد الله keeps its الله
_PRAYER = re.compile(r"(?:ي?رحم|حفظ|تغمد|اسكن|أسكن|غفر|يغفر)(?:ه|ها|هم|هما)\s+الله(?:\s+تعالى)?(?:\s+برحمته(?:\s+الواسعة)?)?"
                     r"|رحمة\s+واسعة|(?:و?أ?اسكن|و?أسكن)(?:ه|ها|هم)\s+فسيح\s+جناته|فسيح\s+جناته|سبحانه\s+وتعالى")
_SPLIT = re.compile(r"[\n\r،,;؛/+&|]+|\s+و\s+|\s+and\s+", re.I)


def _is_noise(tok: str) -> bool:
    w = _TASH.sub("", tok).strip(".:-()[]«»\"'").lower()
    return not w or w in _TITLES or bool(_KIN_RE.match(w))


def clean_names(text: str | None) -> str:
    """Names only, one per line, from a dedication or plaque name.
    "صدقة جارية عن روح والدي المرحوم محمد أحمد ووالدتي فاطمة" -> "محمد أحمد\nفاطمة"."""
    out: list[str] = []
    for part in _SPLIT.split(_PRAYER.sub(" ", _TASH.sub("", text or ""))):
        cur: list[str] = []
        for tok in part.split():
            bare = _TASH.sub("", tok)
            # "ووالدتي" / "والمرحومة": a joined و before a kinship word or title starts the next name
            if len(bare) > 2 and bare.startswith("و") and _is_noise(bare[1:]) and not _is_noise(bare):
                if cur:
                    out.append(" ".join(cur)); cur = []
                continue
            if _is_noise(tok) or (not cur and bare in ("ابن", "ابنة", "بن", "بنت")):
                continue
            cur.append(tok.strip(":"))
        if cur:
            out.append(" ".join(cur))
    seen: list[str] = []
    for n in out:
        if n not in seen:
            seen.append(n)
    return "\n".join(seen)


def donor_names(db: Session, p: Project) -> str:
    """The name on the plaque when there is one (staff have already checked it), else the order's;
    cleaned to the names only (clean_names)."""
    pl = db.scalar(select(Plaque).where(Plaque.project_id == p.id))
    if pl and pl.current_version_id:
        v = db.get(PlaqueVersion, pl.current_version_id)
        name = (v.design or {}).get("name") if v else None
        if isinstance(name, str) and clean_names(name):
            return clean_names(name)
    return clean_names(p.dedication) or clean_names(p.customer_name)


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


def auto_prepare(db: Session, p: Project, actor: User | None) -> bool:
    """The system prepares the certificate when the final video is ready for delivery (Hayah, 21 Nov 2026):
    saved with the order's own data (names, type, month, number, country) in the order's file, unless one
    was already saved. Returns True when it was prepared now."""
    if _last(db, p, SAVED):
        return False
    add_event(db, p, SAVED, source="system", actor=actor, actor_label=None if actor else "system",
              summary="تجهيز الشهادة الوقفية تلقائياً من بيانات الطلب", payload={"design": {}, "auto": True})
    return True


def log_sent(db: Session, p: Project, actor: User, *, with_video: bool, method: str) -> None:
    what = "الشهادة الوقفية والفيديو" if with_video else "الشهادة الوقفية"
    add_event(db, p, SENT, source="dashboard", actor=actor, summary=f"إرسال {what} للعميل على واتساب",
              payload={"with_video": with_video, "method": method, "phone": p.customer_phone_e164})

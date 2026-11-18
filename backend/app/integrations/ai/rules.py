"""Free, offline extraction used when AI is off, over budget, or unavailable.

It is intentionally conservative: it only reports a Well ID that is written in
the message, and it marks anything unclear for human review.
"""
import re

from app.integrations.ai.schemas import (
    ConstructionFields, DeliveryFields, Extraction, FinalVideoFields, MaintenanceFields,
)

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ARABIC = re.compile(r"[؀-ۿ]")
# A Well ID: 3-6 digits, not part of a longer number, a date (2026-11-17, 17/11) or a phone.
WELL_NUM = re.compile(r"(?<![\d/.:+-])(\d{3,6})(?![\d/.:-])")
URL = re.compile(r"https://\S+")

KEYWORDS = {
    "delivery_confirmation": ["تم التسليم", "تسليم", "سلمنا", "تم تسليم", "استلم", "استلام", "delivered",
                              "delivery done", "handover", "handed over"],
    "maintenance_report": ["صيانة", "عطل", "معطل", "خربان", "خراب", "إصلاح", "اصلاح", "تصليح", "لا يعمل", "ما يشتغل",
                           "maintenance", "repair", "broken", "not working", "leak", "service"],
    "final_video": ["فيديو نهائي", "الفيديو النهائي", "فيديو التسليم النهائي", "final video", "final edit"],
    "completed": ["اكتمل", "مكتمل", "تم الانتهاء", "انتهى", "انتهينا", "خلص", "خلصنا", "جاهز", "completed",
                  "complete", "finished", "done"],
    "in_progress": ["بدأ", "بدينا", "بدأنا", "جاري", "قيد التنفيذ", "حفر", "نحفر", "شغالين", "started", "drilling",
                    "in progress", "ongoing", "working on"],
    "new_order": ["طلب جديد", "مشروع جديد", "بئر جديد", "new order", "new project", "new well"],
}
GROUP_HINT = {"A": "construction_update", "B": "delivery_confirmation", "C": "final_video", "D": "maintenance_report"}


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def normalize(text: str) -> str:
    return (text or "").translate(DIGITS)


def extract(text: str, group_label: str | None = None, *, has_media: bool = False) -> Extraction:
    t = normalize(text)
    low = t.lower()
    ids = sorted({int(m) for m in WELL_NUM.findall(URL.sub(" ", t))})
    has_ar, has_en = bool(ARABIC.search(t)), bool(re.search(r"[A-Za-z]{3,}", URL.sub(" ", t)))
    lang = "mixed" if has_ar and has_en else "ar" if has_ar else "en" if has_en else "unknown"

    found = []
    if _has(low, KEYWORDS["delivery_confirmation"]):
        found.append("delivery_confirmation")
    if _has(low, KEYWORDS["maintenance_report"]):
        found.append("maintenance_report")
    if _has(low, KEYWORDS["final_video"]) or (group_label == "C" and URL.search(t)):
        found.append("final_video")
    if _has(low, KEYWORDS["new_order"]):
        found.append("new_order")
    if _has(low, KEYWORDS["completed"]) or _has(low, KEYWORDS["in_progress"]):
        found.append("construction_update")

    conflicts = []
    hint = GROUP_HINT.get(group_label or "")
    if len(found) == 1:
        event = found[0]
    elif len(found) > 1 and hint in found:
        event = hint
    elif len(found) > 1:
        event = found[0]
        conflicts.append(f"Message mentions several event types: {', '.join(found)}")
    elif hint and has_media:
        event = hint if hint != "delivery_confirmation" else "general_note"  # never infer delivery from media alone
    else:
        event = "general_note" if t.strip() else "unknown"
    if hint and event not in (hint, "general_note", "unknown"):
        conflicts.append(f"Event '{event}' arrived via Group {group_label}")

    ex = Extraction(well_ids=ids, well_id=ids[0] if len(ids) == 1 else None, event_type=event, language=lang,
                    confidence=0.0, engine="rules")
    if event == "construction_update":
        status = "completed" if _has(low, KEYWORDS["completed"]) else "in_progress"
        ex.construction = ConstructionFields(construction_status=status, progress_note=t[:500])
    elif event == "delivery_confirmation":
        ex.delivery = DeliveryFields(handover_note=t[:500])
    elif event == "final_video":
        m = URL.search(t)
        ex.final_video = FinalVideoFields(video_url=m.group(0) if m else None)
        if not m:
            ex.missing_fields.append("video_url")
    elif event == "maintenance_report":
        ex.maintenance = MaintenanceFields(problem_type="reported_issue", description=t[:2000])

    if not ids:
        ex.missing_fields.append("well_id")
    if len(ids) > 1:
        conflicts.append(f"Several Well IDs in one message: {ids}")
    ex.conflicts = conflicts
    clear = len(ids) == 1 and not conflicts and event not in ("unknown",) and not ex.missing_fields
    ex.confidence = 0.95 if clear else 0.4 if ids else 0.1
    ex.requires_human_review = not clear
    return ex

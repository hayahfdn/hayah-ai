"""Which prayer a plaque gets, from clear words in the dedication only (no AI, no guessing).

Mirrors classifyDua() in frontend/src/plaque/render.ts; keep the two in step.
sure=False means gender or living/deceased is not clear: the draft uses a neutral prayer and
lists 'gender_state' as missing, so an employee confirms it before the plaque goes forward.
"""
from __future__ import annotations

import re

_F = r"(?:والدتي|امي|أمي|جدتي|زوجتي|ابنتي|بنتي|اختي|أختي|خالتي|عمتي)"
_M = r"(?:ابي|أبي|جدي|زوجي|ابني|اخي|أخي|خالي|عمي)"
_RULES: list[tuple[str, str, bool]] = [
    (r"^فاعلة (ال)?خير", "anon_f", True),
    (r"^فاعل (ال)?خير", "anon_m", True),
    (r"أرواح|ارواح|موتانا|موتى|المرحومين|المرحومون|الأموات|الاموات|المتوفين|رحمهم الله|روح والدي(ه|ها|نا|ّ)", "dead_group", True),
    (rf"المرحومة|المرحومه|المغفور لها|الفقيدة|المتوفاة|رحمها الله|روح {_F}", "dead_f", True),
    (rf"المرحوم|المغفور له|الفقيد|المتوفى|رحمه الله|روح {_M}", "dead_m", True),
    (r"روح|وفاة|متوفى|متوفي", "dead_neutral", False),
    (r"عائلة|عائله|أسرة|اسرة|^آل |والديه|والديها|والدينا|وأولاده|واولاده|وأهله|واهله|وأهلها|واهلها", "living_group", True),
    (rf"^(أم|ام|السيدة|الحاجة|الأخت|الاخت|الآنسة|الانسة|الدكتورة|المهندسة|الطفلة|المولودة) |{_F}", "living_f", True),
    (rf"^(أبو|ابو|السيد|الحاج|الأخ|الاخ|الدكتور|المهندس|الطفل|المولود|الشيخ) |{_M}", "living_m", True),
]
_TASHKEEL = re.compile(r"[ً-ْ]")

# gender: male | female | group | None ; state: living | deceased | None
FACTS = {
    "living_m": ("male", "living"), "living_f": ("female", "living"), "living_group": ("group", "living"),
    "dead_m": ("male", "deceased"), "dead_f": ("female", "deceased"), "dead_group": ("group", "deceased"),
    "anon_m": ("male", "living"), "anon_f": ("female", "living"),
    "dead_neutral": (None, "deceased"), "neutral": (None, None),
}


def classify(text: str | None) -> dict:
    n = re.sub(r"\s+", " ", _TASHKEEL.sub("", text or "")).strip()
    kind, sure = "neutral", False
    if n:
        for pattern, k, s in _RULES:
            if re.search(pattern, n):
                kind, sure = k, s
                break
    gender, state = FACTS[kind]
    return {"kind": kind, "sure": sure, "gender": gender, "state": state}


def kind_for(gender: str | None, state: str | None, anonymous: bool = False) -> str | None:
    """The prayer for facts an employee confirmed. None if still incomplete."""
    if anonymous:
        return "anon_f" if gender == "female" else "anon_m"
    if not gender or not state:
        return None
    return {("male", "living"): "living_m", ("female", "living"): "living_f", ("group", "living"): "living_group",
            ("male", "deceased"): "dead_m", ("female", "deceased"): "dead_f", ("group", "deceased"): "dead_group"}[(gender, state)]

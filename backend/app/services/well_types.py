"""The four HAYAH well types, and how every older spelling maps onto them.

Only four types are offered for new wells: يدوي، متوسط، عميق، شمسي.
"كهربائي" (previously "سطحي كهربائي") is kept for the one old project that has it;
it is discontinued, so it is accepted on existing records but never offered as a choice.

`normalize()` runs on every write to Project.well_type (see models.Project), so the
dashboard, the workbook import, Shopify, the prompt editor and the CLI all store the
same spelling. Values that match no rule are kept unchanged, so nothing is ever lost.
"""
from __future__ import annotations

import re

CANONICAL = ["يدوي", "متوسط", "عميق", "شمسي"]
LEGACY = ["كهربائي"]  # discontinued: kept for old records only
ALLOWED = set(CANONICAL) | set(LEGACY)

# Checked in this order; the first rule whose words appear in the value wins.
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("كهربائي", ("كهربائي", "كهربا", "electric")),
    ("شمسي", ("شمسي", "شمسية", "solar")),
    ("عميق", ("عميق", "متوضأ", "متوضا", "وضوء", "deep")),
    ("متوسط", ("متوسط", "medium")),
    ("يدوي", ("يدوي", "يدوية", "hand")),
]

_AR_NORMAL = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""})


def _fold(s: str) -> str:
    s = re.sub(r"[ً-ْ]", "", s)  # tashkeel
    return re.sub(r"\s+", " ", s.translate(_AR_NORMAL)).strip().lower()


_FOLDED_RULES = [(value, tuple(_fold(w) for w in words)) for value, words in _RULES]


def normalize(value: str | None) -> str | None:
    """Map any known spelling to its canonical type. Unknown values are returned trimmed but unchanged."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    f = _fold(v)
    for canon, words in _FOLDED_RULES:
        if any(w in f for w in words):
            return canon
    return v


def is_known(value: str | None) -> bool:
    return value is None or value in ALLOWED

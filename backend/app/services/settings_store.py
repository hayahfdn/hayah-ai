import copy

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.models import AppSetting


def defaults() -> dict:
    s = get_settings()
    return {
        "ai": {"ai_enabled": s.ai_backend == "anthropic", "monthly_budget_usd": min(s.ai_monthly_budget_usd, s.ai_monthly_budget_max_usd),
               "min_confidence": s.ai_min_confidence, "manual_approval_over_usd": 0.25},
        # From HAYAH's workbook; editable in Settings.
        "well_types": {"values": ["يدوي", "متوسط", "عميق", "شمسي"]},
        "countries": {"values": ["Pakistan", "Nepal", "Bangladesh", "India", "Tanzania"]},
        "animal_types": {"values": ["خروف", "ماعز", "بقرة"]},
        # Add-ons a customer can buy with a well or a sacrifice (Settings → Lists). خروف becomes its own sacrifice.
        "well_addons": {"values": ["خزان", "سيراميك", "خروف"]},
        "sacrifice_addons": {"values": ["إطعام"]},
        "branding": {"logo_drive_file_id": None, "primary_color": "#0E7C86", "font": "Noto Sans Arabic"},
    }


def get_setting(db: Session, key: str) -> dict:
    row = db.get(AppSetting, key)
    return copy.deepcopy(row.value) if row else copy.deepcopy(defaults().get(key, {}))


def set_setting(db: Session, key: str, value: dict, user_id: int | None = None) -> None:
    row = db.get(AppSetting, key)
    value = copy.deepcopy(value)
    if row:
        row.value = value
        flag_modified(row, "value")
        row.updated_by_id = user_id
    else:
        db.add(AppSetting(key=key, value=value, updated_by_id=user_id))
        db.flush()

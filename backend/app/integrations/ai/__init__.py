"""AI extraction entry point with cost guard and manual fallback.

Phase 6 adds the Anthropic extractor behind the same `Extraction` contract.
Until it is approved and configured, the free rules engine is used, and the
system stays fully functional (uncertain items go to Pending Review).
"""
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.ai import rules
from app.integrations.ai.schemas import Extraction


def extract_message(db: Session, text: str, group_label: str | None, *, has_media: bool = False) -> Extraction:
    s = get_settings()
    if s.ai_backend == "anthropic":
        from app.services.settings_store import get_setting
        from app.services.usage import month_ai_cost
        cfg = get_setting(db, "ai")
        from app.services.secrets_store import anthropic_key
        if cfg.get("ai_enabled") and anthropic_key(db) and month_ai_cost(db) < min(cfg.get("monthly_budget_usd", 0), s.ai_monthly_budget_max_usd):
            try:
                from app.integrations.ai.anthropic_extractor import extract as ai_extract  # Phase 6
                return ai_extract(db, text, group_label, has_media=has_media)
            except ImportError:
                pass
    return rules.extract(text, group_label, has_media=has_media)

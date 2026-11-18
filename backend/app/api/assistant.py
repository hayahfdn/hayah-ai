"""Edit-with-a-prompt endpoints: plan (preview only) and apply (after the manager confirms)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import MANAGERS, require_roles
from app.models import User
from app.services import assistant as svc
from app.services.settings_store import get_setting
from app.services.usage import month_ai_cost

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class PlanIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=4000)
    page: dict | None = None


class ApplyIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=4000)
    operations: list[dict] = Field(min_length=1, max_length=100)


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    s, cfg = get_settings(), get_setting(db, "ai")
    try:
        svc.check_available(db)
        ready, why, code = True, None, None
    except svc.AssistantUnavailable as e:
        ready, why, code = False, e.detail, e.code
    return {"ready": ready, "reason": why, "code": code, "model": s.anthropic_model,
            "spent_this_month_usd": round(month_ai_cost(db), 2), "budget_usd": cfg.get("monthly_budget_usd")}


@router.post("/plan")
def plan(body: PlanIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    return svc.plan(db, body.prompt, body.page, user)


@router.post("/apply")
def apply(body: ApplyIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    return svc.apply(db, body.prompt, body.operations, user)

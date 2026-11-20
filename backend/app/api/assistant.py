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
            "spent_this_month_usd": round(month_ai_cost(db), 2), "budget_usd": min(cfg.get("monthly_budget_usd", 0), get_settings().ai_monthly_budget_max_usd)}


@router.post("/plan")
def plan(body: PlanIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    return svc.plan(db, body.prompt, body.page, user)


@router.post("/apply")
def apply(body: ApplyIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    return svc.apply(db, body.prompt, body.operations, user)


# ---------------- floating help assistant (all roles, read only) ----------------
from app.deps import ALL_ROLES  # noqa: E402
from app.services import help_chat  # noqa: E402

help_router = APIRouter(prefix="/api/help", tags=["help"])


class HelpMsg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=8000)


class AskIn(BaseModel):
    messages: list[HelpMsg] = Field(min_length=1, max_length=40)
    page: str | None = Field(None, max_length=300)


@help_router.get("/status")
def help_status(db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    """Ready or not, and why, in plain words. No money is shown here."""
    try:
        svc.check_available(db)
        return {"ready": True, "reason": None, "code": None}
    except svc.AssistantUnavailable as e:
        return {"ready": False, "reason": help_chat.UNAVAILABLE.get(e.code, e.detail), "code": e.code}


@help_router.post("/ask")
def help_ask(body: AskIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ALL_ROLES))):
    return help_chat.ask(db, user, [m.model_dump() for m in body.messages], body.page)

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import UsageRecord


def month_start() -> datetime:
    n = datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_ai_cost(db: Session) -> float:
    v = db.scalar(select(func.coalesce(func.sum(UsageRecord.est_cost_usd), 0)).where(
        UsageRecord.service == "anthropic", UsageRecord.at >= month_start()))
    return float(v or 0)


def summary(db: Session) -> dict:
    rows = db.execute(select(UsageRecord.service, func.count(), func.coalesce(func.sum(UsageRecord.est_cost_usd), 0))
                      .where(UsageRecord.at >= month_start()).group_by(UsageRecord.service)).all()
    return {svc: {"count": n, "est_cost_usd": float(c)} for svc, n, c in rows}

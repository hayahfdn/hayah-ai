from datetime import date, datetime
from decimal import Decimal
import enum
import uuid

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def snapshot(obj, exclude: set[str] = frozenset({"password_hash"})) -> dict:
    return {c.key: jsonable(getattr(obj, c.key)) for c in inspect(obj).mapper.column_attrs if c.key not in exclude}


def audit(db: Session, action: str, entity_type: str, entity_id, *, actor: User | None = None,
          actor_label: str | None = None, before: dict | None = None, after: dict | None = None,
          ip: str | None = None) -> AuditLog:
    if before is not None and after is not None:
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        before = {k: before.get(k) for k in changed}
        after = {k: after.get(k) for k in changed}
    row = AuditLog(action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None,
                   actor_user_id=actor.id if actor else None,
                   actor_label=actor_label or (actor.email if actor else "system"),
                   before=jsonable(before) if before is not None else None,
                   after=jsonable(after) if after is not None else None, ip=ip)
    db.add(row)
    return row

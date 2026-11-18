"""Undo recent changes, and remove a workbook import."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ADMINS, FIELD_WRITERS, require_roles
from app.models import User
from app.services import undo as svc

router = APIRouter(prefix="/api", tags=["undo"])


@router.get("/undo/recent")
def recent(mine: bool = False, limit: int = 50, db: Session = Depends(get_db),
           user: User = Depends(require_roles(FIELD_WRITERS))):
    return svc.recent(db, user, mine_only=mine, limit=min(max(limit, 1), 200))


@router.post("/undo/{audit_id}")
def undo(audit_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(FIELD_WRITERS))):
    out = svc.undo(db, audit_id, user)
    db.commit()
    return out


@router.get("/admin/imports")
def imports(db: Session = Depends(get_db), _: User = Depends(require_roles(ADMINS))):
    return svc.imports_list(db)


@router.post("/admin/imports/{audit_id}/remove")
def remove(audit_id: int, apply: bool = False, db: Session = Depends(get_db),
           user: User = Depends(require_roles(ADMINS))):
    out = svc.remove_import(db, audit_id, user, apply=apply)
    if apply:
        db.commit()
    else:
        db.rollback()
    return out

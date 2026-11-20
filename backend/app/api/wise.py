"""Wise, read only: connect (token), sync, and review the unmatched list. Managers only; token: super admin."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ADMINS, MANAGERS, require_roles
from app.models import User
from app.services import wise as svc

router = APIRouter(prefix="/api/wise", tags=["wise"])
MGR = Depends(require_roles(MANAGERS))


class TokenIn(BaseModel):
    token: str | None = Field(None, max_length=200)


class MapIn(BaseModel):
    recipient_contractors: dict[str, str]


class MatchIn(BaseModel):
    transaction_id: int


class RecordIn(BaseModel):
    kind: str | None = None
    contractor_code: str | None = None


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = MGR):
    return svc.status(db)


@router.put("/token")
def token(body: TokenIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    return svc.set_token(db, body.token, user)


@router.put("/recipients")
def recipients(body: MapIn, db: Session = Depends(get_db), user: User = MGR):
    svc.save_cfg(db, body.model_dump(), user)
    db.commit()
    return svc.status(db)


@router.post("/sync")
def sync(db: Session = Depends(get_db), user: User = MGR):
    return svc.sync(db, user)


@router.get("/transactions")
def transactions(status: str | None = Query("unmatched", pattern="^(unmatched|matched|ignored|all)$"),
                 db: Session = Depends(get_db), _: User = MGR):
    return svc.list_rows(db, None if status == "all" else status)


@router.get("/transactions/{wid}/candidates")
def candidates(wid: int, db: Session = Depends(get_db), _: User = MGR):
    return svc.candidates(db, wid)


@router.post("/transactions/{wid}/match")
def match(wid: int, body: MatchIn, db: Session = Depends(get_db), user: User = MGR):
    return svc.match(db, wid, body.transaction_id, user)


@router.post("/transactions/{wid}/unmatch")
def unmatch(wid: int, db: Session = Depends(get_db), user: User = MGR):
    return svc.unmatch(db, wid, user)


@router.post("/transactions/{wid}/ignore")
def ignore(wid: int, undo: bool = False, db: Session = Depends(get_db), user: User = MGR):
    return svc.ignore(db, wid, user, undo)


@router.post("/transactions/{wid}/record")
def record(wid: int, body: RecordIn, db: Session = Depends(get_db), user: User = MGR):
    return svc.record(db, wid, user, body.kind, body.contractor_code)

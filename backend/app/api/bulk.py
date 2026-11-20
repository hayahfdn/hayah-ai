"""Bulk changes that need a manager's explicit approval: preview first, then apply, with undo."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import MANAGERS, require_roles
from app.models import User
from app.services import bulk_delivery as svc

router = APIRouter(prefix="/api/bulk/old-delivered", tags=["bulk"])


class ApplyIn(BaseModel):
    wells: int = Field(ge=0)
    sacrifices: int = Field(ge=0)
    confirm: bool


@router.get("/preview")
def preview(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    return svc.preview(db) | {"history": svc.history(db)}


@router.post("/apply")
def apply(body: ApplyIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    if not body.confirm:
        from fastapi import HTTPException
        raise HTTPException(422, "Confirm first.")
    return svc.apply(db, user, body.model_dump())


@router.post("/{batch_id}/undo")
def undo(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    return svc.undo(db, user, batch_id)

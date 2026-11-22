"""«صيغة عقد»: the official contract and invoice for a well or a sacrifice. Employees and managers
(the people who prepare plaques and certificates). HAYAH's phone and the default delivery period
are in Settings; managers change them."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import MANAGERS, PROJECT_CREATORS, require_roles
from app.models import Project, Sacrifice, User
from app.services import contract as svc

router = APIRouter(prefix="/api/contracts", tags=["contracts"])
EDITORS = Depends(require_roles(PROJECT_CREATORS))
# Only text and a few layout choices are kept from the editor (never images, never cost).
KEYS = {"title", "subtitle", "project_no", "project_type", "owner", "owner_phone", "specs", "amount", "currency",
        "amount_words", "expected_delivery", "delivery_note", "contract_date", "terms", "hayah_phone", "site", "names_font",
        "names_size", "show_stamp", "show_terms", "accent"}


def _rec(db: Session, kind: str, number: int):
    if kind == "well":
        r = db.scalar(select(Project).where(Project.well_id == number, Project.merged_into_id.is_(None)))
    elif kind == "sacrifice":
        r = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == number))
    else:
        raise HTTPException(404, "Unknown kind")
    if not r:
        raise HTTPException(404, f"No {kind} number {number}")
    return r


class SettingsIn(BaseModel):
    hayah_phone: str = Field(default="", max_length=40)
    invoice_prefix: str = Field(default="HF", min_length=1, max_length=8, pattern=r"^[A-Za-z0-9]+$")


@router.get("/settings")
def get_contract_settings(db: Session = Depends(get_db), _: User = EDITORS):
    return svc.settings(db)


@router.put("/settings")
def put_contract_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    out = svc.save_settings(db, body.model_dump(), user)
    db.commit()
    return out


@router.get("/{kind}/{number}")
def get_contract(kind: str, number: int, db: Session = Depends(get_db), _: User = EDITORS):
    return svc.data(db, kind, _rec(db, kind, number))


class DesignIn(BaseModel):
    design: dict


@router.put("/{kind}/{number}")
def save_contract(kind: str, number: int, body: DesignIn, db: Session = Depends(get_db), user: User = EDITORS):
    rec = _rec(db, kind, number)
    design = {}
    for k, v in body.design.items():
        if k not in KEYS:
            continue
        if not isinstance(v, (str, int, float, bool)) or (isinstance(v, str) and len(v) > 4000):
            raise HTTPException(422, f"Bad value for {k}")
        design[k] = v
    svc.save(db, kind, rec, design, user)
    db.commit()
    return svc.data(db, kind, rec)

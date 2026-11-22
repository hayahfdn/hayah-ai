"""«شهادة وقفية» for each well: default text from the order, the saved design, and a log of sending.
Employees and managers only (the same people who prepare plaques and final videos)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import PROJECT_CREATORS, require_roles
from app.models import Project, User
from app.services import certificate as cert

router = APIRouter(prefix="/api/certificates", tags=["certificates"])
EDITORS = Depends(require_roles(PROJECT_CREATORS))
# Only these keys are kept from the editor (text and a few layout choices; never images).
KEYS = {"title", "intro", "project_type", "sadaqa_line", "names", "names_size", "opened_prefix", "month", "year",
        "number_label", "number", "country_label", "country", "dua", "site", "icon", "show_stamp", "names_font"}


def _well(db: Session, number: int) -> Project:
    p = db.scalar(select(Project).where(Project.well_id == number))
    if not p:
        raise HTTPException(404, f"No well number {number}")
    return p


@router.get("/well/{number}")
def get_certificate(number: int, db: Session = Depends(get_db), _: User = EDITORS):
    return cert.data(db, _well(db, number))


class DesignIn(BaseModel):
    design: dict


@router.put("/well/{number}")
def save_certificate(number: int, body: DesignIn, db: Session = Depends(get_db), user: User = EDITORS):
    p = _well(db, number)
    design = {}
    for k, v in body.design.items():
        if k not in KEYS:
            continue
        if not isinstance(v, (str, int, float, bool)) or (isinstance(v, str) and len(v) > 2000):
            raise HTTPException(422, f"Bad value for {k}")
        design[k] = v
    cert.save(db, p, design, user)
    db.commit()
    return cert.data(db, p)


class SentIn(BaseModel):
    with_video: bool = False
    method: str = Field(default="share", pattern="^(share|download)$")


@router.post("/well/{number}/sent")
def certificate_sent(number: int, body: SentIn, db: Session = Depends(get_db), user: User = EDITORS):
    p = _well(db, number)
    cert.log_sent(db, p, user, with_video=body.with_video, method=body.method)
    db.commit()
    return cert.data(db, p)

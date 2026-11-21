"""Team tasks («مهامي») and the manager board. Employees and managers only; no cost, price or money is
returned (app/services/team_flow.py)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import MANAGERS, PROJECT_CREATORS, require_roles
from app.models import Project, User
from app.services import team_flow as tf

router = APIRouter(prefix="/api/team", tags=["team tasks"])
EDITORS = Depends(require_roles(PROJECT_CREATORS))
VIEW = "^(mine|all|" + "|".join(tf.STAGES) + ")$"


def _meta(db: Session, user: User) -> dict:
    own, hp = tf.owners(db), tf.helpers(db)
    names = {p["id"]: p["name"] for p in tf.people(db)}
    return {"my_stages": tf.my_stages(db, user), "counts": tf.counts(db, user), "settings": tf.settings(db),
            "stages": [{"key": s, "label": tf.STAGE_AR[s], "steps": tf.STEPS[s],
                        "owner": {"id": own[s], "name": names.get(own[s])} if own.get(s) else None,
                        "helpers": [{"id": h, "name": names[h]} for h in hp.get(s, []) if h in names],
                        "kind": "system" if s in tf.SYSTEM_STAGES else "manager" if s in tf.MANAGER_STAGES else "person"}
                       for s in tf.STAGES],
            "step_labels": tf.STEP_AR, "people": tf.people(db), "late_days": tf.LATE_DAYS}


@router.get("/tasks")
def tasks(view: str = Query("mine", pattern=VIEW), db: Session = Depends(get_db), user: User = EDITORS):
    return {"view": view, "items": tf.tasks(db, user, view), **_meta(db, user)}


@router.get("/counts")
def counts(db: Session = Depends(get_db), user: User = EDITORS):
    return tf.counts(db, user)


def _project(db: Session, well_id: int) -> Project:
    p = db.scalar(select(Project).where(Project.well_id == well_id))
    if not p or p.merged_into_id:
        raise HTTPException(404, "Well not found")
    return p


@router.get("/order/{well_id}")
def one(well_id: int, db: Session = Depends(get_db), _: User = EDITORS):
    return tf.card_for(db, _project(db, well_id))


class StepIn(BaseModel):
    done: bool = True
    note: str | None = Field(default=None, max_length=500)


@router.post("/order/{well_id}/steps/{step}")
def set_step(well_id: int, step: str, body: StepIn, db: Session = Depends(get_db), user: User = EDITORS):
    out = tf.set_step(db, _project(db, well_id), step, body.done, user, body.note)
    db.commit()
    return out


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


@router.post("/order/{well_id}/send-to-contractor")
def send_to_contractor(well_id: int, body: NoteIn, db: Session = Depends(get_db), user: User = EDITORS):
    out = tf.send_to_contractor(db, _project(db, well_id), user, body.note)
    db.commit()
    return out


class CloseIn(BaseModel):
    on: date | None = None
    note: str | None = Field(default=None, max_length=500)


@router.post("/order/{well_id}/close")
def close(well_id: int, body: CloseIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    out = tf.close_project(db, _project(db, well_id), user, body.on, body.note)
    db.commit()
    return out


class AssignIn(BaseModel):
    stage: str
    user_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


@router.post("/order/{well_id}/assign")
def assign(well_id: int, body: AssignIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    out = tf.reassign(db, _project(db, well_id), body.stage, body.user_id, user, body.note)
    db.commit()
    return out


class SettingsIn(BaseModel):
    start_date: date | None = None
    owners: dict[str, int | None] | None = None
    helpers: dict[str, list[int]] | None = None


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    if body.start_date:
        tf.save_settings(db, body.start_date, user)
    if body.owners is not None:
        tf.save_owners(db, body.owners, user)
    if body.helpers is not None:
        tf.save_helpers(db, body.helpers, user)
    db.commit()
    return _meta(db, user)

"""Team tasks («مهامي»): each person's list of orders waiting for their part of the workflow.
Employees and managers only; no cost, price or money is returned (app/services/team_flow.py)."""
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


@router.get("/tasks")
def tasks(stage: str | None = Query(None, pattern="^(intake|customer|delivery)$"), db: Session = Depends(get_db), user: User = EDITORS):
    return {"stage": stage, "my_stage": user.team_stage, "items": tf.tasks(db, stage), "counts": tf.counts(db),
            "members": tf.members(db), "stages": [{"key": s, "label": tf.STAGE_AR[s], "steps": tf.STEPS[s]} for s in tf.STAGES],
            "step_labels": tf.STEP_AR, "settings": tf.settings(db)}


@router.get("/counts")
def counts(db: Session = Depends(get_db), user: User = EDITORS):
    c = tf.counts(db)
    return {**c, "mine": c.get(user.team_stage, 0) if user.team_stage else 0, "my_stage": user.team_stage}


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


class SettingsIn(BaseModel):
    start_date: date


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    out = tf.save_settings(db, body.start_date, user)
    db.commit()
    return out

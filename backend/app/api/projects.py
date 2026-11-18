import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ALL_ROLES, FIELD_WRITERS, MANAGERS, client_ip, require_roles
from app.models import (
    DeliveryConfirmation, MaintenanceRecord, MediaAsset, Project, ProjectEvent, Role, User,
)
from app.schemas import (
    DeliveryOut, EventOut, MaintenanceOut, MediaOut, MergeRequestIn, ProjectCreate, ProjectOut, ProjectPage,
    ProjectUpdate, ReviewOut,
)
from app.services import projects as svc
from app.services.sheets_sync import MASTER_HEADER, project_row

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _scope(user: User):
    return user.contractor_id if user.role == Role.contractor else None


@router.get("", response_model=ProjectPage)
def list_projects(q: str | None = None, country: str | None = None, construction_status: str | None = None,
                  delivery_status: str | None = None, contractor_id: int | None = None,
                  month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                  page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=5000),
                  sort: str = Query("-well_id", pattern=r"^-?(well_id|order_date|updated_at|country|construction_status)$"),
                  db: Session = Depends(get_db), user: User = Depends(require_roles(ALL_ROLES))):
    items, total = svc.list_projects(db, q=q, country=country, construction_status=construction_status,
                                     delivery_status=delivery_status, contractor_id=contractor_id, page=page,
                                     page_size=page_size, sort=sort, contractor_scope=_scope(user), month=month)
    return ProjectPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    buf = io.StringIO()
    buf.write("﻿")  # Excel-friendly UTF-8 for Arabic
    w = csv.writer(buf)
    w.writerow(MASTER_HEADER)
    for p in db.scalars(select(Project).where(Project.merged_into_id.is_(None)).order_by(Project.well_id)).unique():
        w.writerow(project_row(p))
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=hayah-projects.csv"})


@router.get("/well-id-check/{well_id}")
def well_id_check(well_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    """Used by the create form. Suggests the next number only as a hint; a person confirms it."""
    highest = db.scalar(select(func.max(Project.well_id)))
    return {"well_id": well_id, "exists": svc.get_by_well_id(db, well_id) is not None,
            "highest_existing": highest, "suggested_next": (highest or 0) + 1}


@router.post("", response_model=ProjectOut, status_code=201)
def create(body: ProjectCreate, request: Request, db: Session = Depends(get_db),
           user: User = Depends(require_roles(MANAGERS))):
    p = svc.create_project(db, body.model_dump(), actor=user, ip=client_ip(request))
    db.commit()
    return p


def _get_visible(db, well_id: int, user: User) -> Project:
    p = svc.require_project(db, well_id)
    if user.role == Role.contractor and p.contractor_id != user.contractor_id:
        raise HTTPException(404, f"No project with Well ID {well_id}")
    return p


@router.get("/{well_id}", response_model=ProjectOut)
def get(well_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(ALL_ROLES))):
    return _get_visible(db, well_id, user)


@router.patch("/{well_id}", response_model=ProjectOut)
def update(well_id: int, body: ProjectUpdate, request: Request, db: Session = Depends(get_db),
           user: User = Depends(require_roles(FIELD_WRITERS))):
    p = svc.require_project(db, well_id, for_update=True)
    data = body.model_dump(exclude_unset=True)
    expected = data.pop("expected_version", None)
    svc.update_project(db, p, data, actor=user, ip=client_ip(request), expected_version=expected)
    db.commit()
    return p


@router.get("/{well_id}/history")
def history(well_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(ALL_ROLES))):
    p = _get_visible(db, well_id, user)
    ids = [p.id] + list(db.scalars(select(Project.id).where(Project.merged_into_id == p.id)))
    events = db.scalars(select(ProjectEvent).where(ProjectEvent.project_id.in_(ids)).order_by(ProjectEvent.created_at.desc()))
    media = db.scalars(select(MediaAsset).where(MediaAsset.project_id.in_(ids)).order_by(MediaAsset.created_at.desc()))
    maint = db.scalars(select(MaintenanceRecord).where(MaintenanceRecord.project_id.in_(ids)).order_by(MaintenanceRecord.date.desc())).unique()
    deliveries = db.scalars(select(DeliveryConfirmation).where(DeliveryConfirmation.project_id.in_(ids)).order_by(DeliveryConfirmation.created_at.desc()))
    return {"events": [EventOut.model_validate(e) for e in events],
            "media": [MediaOut.model_validate(m).model_copy(update={"well_id": p.well_id}) for m in media],
            "maintenance": [MaintenanceOut.model_validate(m).model_copy(update={"well_id": p.well_id}) for m in maint],
            "deliveries": [DeliveryOut.model_validate(d).model_copy(update={"well_id": p.well_id}) for d in deliveries]}


@router.post("/merge-requests", response_model=ReviewOut, status_code=201)
def merge_request(body: MergeRequestIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    src, tgt = svc.require_project(db, body.source_well_id), svc.require_project(db, body.target_well_id)
    case = svc.request_merge(db, src, tgt, body.reason, user)
    db.commit()
    return case

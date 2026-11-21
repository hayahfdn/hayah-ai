from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ALL_ROLES, MANAGERS, require_roles
from app.models import Contractor, Project, User
from app.schemas import ContractorIn, ContractorOut, ContractorUpdate
from app.services.audit import audit, snapshot
from app.services.contractor_colors import next_color
from app.services.projects import queue_sheet_sync

router = APIRouter(prefix="/api/contractors", tags=["contractors"])


@router.get("", response_model=list[ContractorOut])
def list_contractors(db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    return list(db.scalars(select(Contractor).order_by(Contractor.code)))


@router.get("/performance")
def performance(db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    rows = db.execute(select(
        Contractor.id, Contractor.code, Contractor.name,
        func.count(Project.id),
        func.sum(case((Project.construction_status == "completed", 1), else_=0)),
        func.sum(case((Project.construction_status == "in_progress", 1), else_=0)),
        func.sum(case((Project.delivery_status == "delivered", 1), else_=0)),
        func.avg(Project.completion_date - Project.construction_start_date),
    ).outerjoin(Project, Project.contractor_id == Contractor.id).group_by(Contractor.id).order_by(Contractor.code)).all()
    return [{"id": r[0], "code": r[1], "name": r[2], "projects": r[3], "completed": int(r[4] or 0),
             "in_progress": int(r[5] or 0), "delivered": int(r[6] or 0),
             "avg_build_days": round(float(r[7]), 1) if r[7] is not None else None} for r in rows]


@router.post("", response_model=ContractorOut, status_code=201)
def create(body: ContractorIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    if db.scalar(select(Contractor).where(func.upper(Contractor.code) == body.code.upper())):
        raise HTTPException(409, "Contractor code already exists")
    c = Contractor(**body.model_dump() | {"code": body.code.upper()})
    c.color = (c.color or next_color(db)).upper()
    db.add(c)
    db.flush()
    audit(db, "contractor.create", "contractor", c.code, actor=user, after=snapshot(c))
    queue_sheet_sync(db)
    db.commit()
    return c


@router.patch("/{cid}", response_model=ContractorOut)
def update(cid: int, body: ContractorUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    c = db.get(Contractor, cid)
    if not c:
        raise HTTPException(404, "Contractor not found")
    before = snapshot(c)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "kind" and v is None:
            continue
        setattr(c, k, v.upper() if k == "color" and v else v)
    audit(db, "contractor.update", "contractor", c.code, actor=user, before=before, after=snapshot(c))
    queue_sheet_sync(db)
    db.commit()
    return c

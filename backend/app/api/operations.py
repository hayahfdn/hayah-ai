"""Delivery, maintenance, media and review endpoints."""
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ALL_ROLES, FIELD_WRITERS, MAINTENANCE_WRITERS, MANAGERS, client_ip, require_roles
from app.models import (
    ApprovalStatus, DeliveryConfirmation, InboundMessage, MaintenanceRecord, MediaAsset, MediaCategory, Project,
    ReviewCase, ReviewKind, ReviewStatus, Role, User, utcnow,
)
from app.schemas import (
    DeliveryCreate, DeliveryDecision, DeliveryOut, MaintenanceCreate, MaintenanceOut, MaintenanceUpdate, MediaOut,
    ReviewDecision, ReviewOut,
)
from app.services import delivery as delivery_svc
from app.services import maintenance as maint_svc
from app.services import media as media_svc
from app.services import projects as project_svc
from app.services.audit import audit
from app.services.intake import apply_extraction

delivery = APIRouter(prefix="/api/delivery", tags=["delivery"])
maintenance = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
media = APIRouter(prefix="/api/media", tags=["media"])
review = APIRouter(prefix="/api/review", tags=["review"])


def _wells(db: Session, project_ids) -> dict:
    ids = {i for i in project_ids if i}
    return dict(db.execute(select(Project.id, Project.well_id).where(Project.id.in_(ids))).all()) if ids else {}


# ---------------- delivery ----------------
@delivery.get("", response_model=list[DeliveryOut])
def list_deliveries(status: ApprovalStatus | None = None, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(ALL_ROLES))):
    q = select(DeliveryConfirmation).order_by(DeliveryConfirmation.created_at.desc()).limit(500)
    if status:
        q = q.where(DeliveryConfirmation.status == status)
    rows = list(db.scalars(q))
    w = _wells(db, [r.project_id for r in rows])
    return [DeliveryOut.model_validate(r).model_copy(update={"well_id": w.get(r.project_id)}) for r in rows]


@delivery.post("", response_model=DeliveryOut, status_code=201)
def create_delivery(body: DeliveryCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(FIELD_WRITERS))):
    p = project_svc.require_project(db, body.well_id)
    if user.role == Role.contractor and p.contractor_id != user.contractor_id:
        raise HTTPException(403, "This project is not assigned to you")
    dc = delivery_svc.create_pending(db, p, delivery_date=body.delivery_date, source="dashboard", requested_by=user,
                                     notes=body.notes, evidence_media_ids=body.evidence_media_ids)
    db.commit()
    return DeliveryOut.model_validate(dc).model_copy(update={"well_id": p.well_id})


@delivery.post("/{dc_id}/decision", response_model=DeliveryOut)
def decide(dc_id: int, body: DeliveryDecision, request: Request, db: Session = Depends(get_db),
           user: User = Depends(require_roles(MANAGERS))):
    dc = db.get(DeliveryConfirmation, dc_id, with_for_update=True)
    if not dc:
        raise HTTPException(404, "Confirmation not found")
    delivery_svc.decide(db, dc, approve=body.approve, actor=user, note=body.note, ip=client_ip(request))
    db.commit()
    return DeliveryOut.model_validate(dc).model_copy(update={"well_id": _wells(db, [dc.project_id]).get(dc.project_id)})


# ---------------- maintenance ----------------
@maintenance.get("", response_model=list[MaintenanceOut])
def list_maintenance(well_id: int | None = None, status: str | None = None, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(ALL_ROLES))):
    q = select(MaintenanceRecord).order_by(MaintenanceRecord.date.desc(), MaintenanceRecord.id.desc()).limit(1000)
    if well_id:
        q = q.where(MaintenanceRecord.project_id == project_svc.require_project(db, well_id).id)
    if status:
        q = q.where(MaintenanceRecord.status == status)
    rows = list(db.scalars(q).unique())
    w = _wells(db, [r.project_id for r in rows])
    return [MaintenanceOut.model_validate(r).model_copy(update={"well_id": w.get(r.project_id)}) for r in rows]


@maintenance.post("", response_model=MaintenanceOut, status_code=201)
def create_maintenance(body: MaintenanceCreate, db: Session = Depends(get_db),
                       user: User = Depends(require_roles(MAINTENANCE_WRITERS))):
    p = project_svc.require_project(db, body.well_id, for_update=True)
    rec = maint_svc.create_record(db, p, body.model_dump(exclude={"well_id"}), actor=user)
    db.commit()
    return MaintenanceOut.model_validate(rec).model_copy(update={"well_id": p.well_id})


@maintenance.patch("/{code}", response_model=MaintenanceOut)
def update_maintenance(code: str, body: MaintenanceUpdate, db: Session = Depends(get_db),
                       user: User = Depends(require_roles(MAINTENANCE_WRITERS))):
    rec = db.scalar(select(MaintenanceRecord).where(MaintenanceRecord.maintenance_code == code))
    if not rec:
        raise HTTPException(404, "Maintenance record not found")
    maint_svc.update_record(db, rec, body.model_dump(exclude_unset=True), actor=user)
    db.commit()
    return MaintenanceOut.model_validate(rec).model_copy(update={"well_id": _wells(db, [rec.project_id]).get(rec.project_id)})


# ---------------- media ----------------
@media.get("", response_model=list[MediaOut])
def list_media(well_id: int | None = None, category: MediaCategory | None = None, unassigned: bool = False,
               q: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    stmt = select(MediaAsset).order_by(MediaAsset.created_at.desc()).limit(1000)
    if well_id:
        stmt = stmt.where(MediaAsset.project_id == project_svc.require_project(db, well_id).id)
    if unassigned:
        stmt = stmt.where(MediaAsset.project_id.is_(None))
    if category:
        stmt = stmt.where(MediaAsset.category == category)
    if q:
        stmt = stmt.where(MediaAsset.filename.ilike(f"%{q}%") | MediaAsset.original_filename.ilike(f"%{q}%"))
    rows = list(db.scalars(stmt))
    w = _wells(db, [r.project_id for r in rows])
    return [MediaOut.model_validate(r).model_copy(update={"well_id": w.get(r.project_id)}) for r in rows]


@media.post("/upload", response_model=MediaOut, status_code=201)
def upload(file: UploadFile = File(...), well_id: int | None = Form(None),
           category: MediaCategory = Form(MediaCategory.construction), db: Session = Depends(get_db),
           user: User = Depends(require_roles(FIELD_WRITERS | MAINTENANCE_WRITERS))):
    project = project_svc.require_project(db, well_id) if well_id else None
    with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as tmp:
        shutil.copyfileobj(file.file, tmp)
        asset, created = media_svc.store_media(db, tmp, original_filename=file.filename, mime_type=file.content_type,
                                               project=project, category=category, source="dashboard",
                                               sender=user.full_name, actor=user)
    db.commit()
    if not created:
        raise HTTPException(409, f"This exact file is already stored as {asset.filename}")
    return MediaOut.model_validate(asset).model_copy(update={"well_id": well_id})


# ---------------- review ----------------
@review.get("", response_model=list[ReviewOut])
def list_review(status: ReviewStatus = ReviewStatus.pending, kind: ReviewKind | None = None,
                db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    q = select(ReviewCase).where(ReviewCase.status == status).order_by(ReviewCase.created_at.desc()).limit(500)
    if kind:
        q = q.where(ReviewCase.kind == kind)
    rows = list(db.scalars(q))
    msgs = {m.id: m for m in db.scalars(select(InboundMessage).where(
        InboundMessage.id.in_([r.inbound_message_id for r in rows if r.inbound_message_id])))}
    out = []
    for r in rows:
        m = msgs.get(r.inbound_message_id)
        out.append(ReviewOut.model_validate(r).model_copy(update={
            "message_text": m.text if m else None, "message_sender": (m.sender_name or m.sender_phone) if m else None,
            "message_group": m.group_label if m else None}))
    return out


@review.post("/{case_id}/decision", response_model=ReviewOut)
def decide_review(case_id: int, body: ReviewDecision, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(MANAGERS))):
    case = db.get(ReviewCase, case_id, with_for_update=True)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.status != ReviewStatus.pending:
        raise HTTPException(409, "Case already decided")
    if body.approve:
        if case.kind == ReviewKind.merge_request:
            src = project_svc.require_project(db, case.proposed["source_well_id"])
            tgt = project_svc.require_project(db, case.proposed["target_well_id"])
            project_svc.apply_merge(db, src, tgt, user)
        else:
            if not body.well_id:
                raise HTTPException(422, "Choose the Well ID this belongs to")
            project = project_svc.require_project(db, body.well_id)
            if case.kind == ReviewKind.unassigned_media and case.media_asset_id:
                asset = db.get(MediaAsset, case.media_asset_id)
                media_svc.assign_media(db, asset, project, asset.category, user)
            elif case.inbound_message_id:
                msg = db.get(InboundMessage, case.inbound_message_id)
                ex = dict(msg.extraction or {})
                event_type = body.event_type or ex.get("event_type") or "general_note"
                msg.project_id = project.id
                apply_extraction(db, project, event_type, ex, actor=user, msg=msg)
                msg.processing_status = "applied_after_review"
                for a in db.scalars(select(MediaAsset).where(MediaAsset.inbound_message_id == msg.id,
                                                             MediaAsset.project_id.is_(None))):
                    media_svc.assign_media(db, a, project, a.category, user)
    case.status = ReviewStatus.approved if body.approve else ReviewStatus.rejected
    case.resolved_by_id, case.resolved_at, case.resolution_note = user.id, utcnow(), body.note
    audit(db, f"review.{case.status.value}", "review_case", case.id, actor=user,
          after={"well_id": body.well_id, "event_type": body.event_type, "note": body.note})
    db.commit()
    return case

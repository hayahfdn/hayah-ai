"""Delivery is its own event. Construction completion or a final video never
mark a well delivered. Only an approved DeliveryConfirmation does."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ApprovalStatus, DeliveryConfirmation, DeliveryStatus, InboundMessage, Project, User, utcnow,
)
from app.services.audit import audit, snapshot
from app.services.projects import add_event, queue_sheet_sync


def create_pending(db: Session, project: Project, *, delivery_date: date | None, source: str,
                   requested_by: User | None = None, message: InboundMessage | None = None,
                   notes: str | None = None, evidence_media_ids: list[int] | None = None) -> DeliveryConfirmation:
    if message is not None:
        existing = db.scalar(select(DeliveryConfirmation).where(DeliveryConfirmation.inbound_message_id == message.id))
        if existing:
            return existing  # idempotent on the source message
    dc = DeliveryConfirmation(
        project_id=project.id, delivery_date=delivery_date or (message.received_at.date() if message else date.today()),
        source=source, inbound_message_id=message.id if message else None,
        sender_name=(message.sender_name if message else (requested_by.full_name if requested_by else None)),
        sender_phone=message.sender_phone if message else None, notes=notes,
        evidence_media_ids=evidence_media_ids or [], requested_by_id=requested_by.id if requested_by else None)
    db.add(dc)
    db.flush()
    add_event(db, project, "delivery_confirmation_received", source=source, actor=requested_by,
              actor_label=dc.sender_name, summary="Delivery confirmation waiting for manager approval",
              payload={"confirmation_id": dc.id, "delivery_date": dc.delivery_date})
    audit(db, "delivery.pending_created", "delivery_confirmation", dc.id, actor=requested_by,
          actor_label=dc.sender_name, after=snapshot(dc))
    return dc


def decide(db: Session, dc: DeliveryConfirmation, *, approve: bool, actor: User, note: str | None,
           ip: str | None = None) -> DeliveryConfirmation:
    if dc.status != ApprovalStatus.pending:
        raise HTTPException(409, f"This confirmation was already {dc.status.value}")
    project = db.get(Project, dc.project_id, with_for_update=True)
    dc.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    dc.decided_by_id, dc.decided_at, dc.decision_note = actor.id, utcnow(), note
    if approve:
        before = snapshot(project)
        project.delivery_status = DeliveryStatus.delivered
        project.delivery_date = dc.delivery_date
        project.updated_at = utcnow()
        add_event(db, project, "delivery_confirmed", source="dashboard", actor=actor,
                  summary=f"Delivery approved for {dc.delivery_date}",
                  payload={"confirmation_id": dc.id, "evidence_media_ids": dc.evidence_media_ids,
                           "sender": dc.sender_name}, idempotency_key=f"delivery-approved:{dc.id}")
        audit(db, "project.delivery_confirmed", "project", project.well_id, actor=actor, before=before,
              after=snapshot(project), ip=ip)
        queue_sheet_sync(db)
    else:
        add_event(db, project, "delivery_confirmation_rejected", source="dashboard", actor=actor,
                  summary=note or "Delivery confirmation rejected", payload={"confirmation_id": dc.id})
    audit(db, "delivery.approved" if approve else "delivery.rejected", "delivery_confirmation", dc.id,
          actor=actor, after={"status": dc.status.value, "note": note}, ip=ip)
    return dc

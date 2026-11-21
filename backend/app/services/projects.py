"""Project (well) operations. All writes go through here so that every change
is validated, versioned, written to the timeline and audit log, and queued for
Google Sheets sync in the same transaction."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ConstructionStatus, Contractor, DeliveryStatus, Project, ProjectEvent, ReviewCase, ReviewKind,
    Role, User, utcnow,
)
from app.services import addons, phones
from app.services.audit import audit, jsonable, snapshot
from app.services.jobs import enqueue

FINANCE_ROLES = {Role.super_admin, Role.operations_manager}
HIDDEN_FROM_STAFF = {"cost"}


def redact_event(ev: dict) -> dict | None:
    """Timeline entry as a non-manager may see it: cost changes removed. None = nothing left to show."""
    payload = dict(ev.get("payload") or {})
    if "fields" in payload:
        payload["fields"] = {k: v for k, v in payload["fields"].items() if k not in HIDDEN_FROM_STAFF}
    if "changes" in payload:
        changes = {k: v for k, v in payload["changes"].items() if k not in HIDDEN_FROM_STAFF}
        if not changes and payload["changes"]:
            return None
        if len(changes) != len(payload["changes"]):
            ev = {**ev, "summary": ", ".join(f"{k}: {v['from']} → {v['to']}" for k, v in changes.items())[:500]}
        payload["changes"] = changes
    return {**ev, "payload": payload}


def get_by_well_id(db: Session, well_id: int, *, for_update: bool = False) -> Project | None:
    q = select(Project).where(Project.well_id == well_id)
    if for_update:
        q = q.with_for_update()
    return db.scalar(q)


def require_project(db: Session, well_id: int, *, for_update: bool = False) -> Project:
    p = get_by_well_id(db, well_id, for_update=for_update)
    if not p:
        raise HTTPException(404, f"No project with Well ID {well_id}")
    return p


def add_event(db: Session, project: Project, event_type: str, *, source: str, summary: str | None = None,
              payload: dict | None = None, actor: User | None = None, actor_label: str | None = None,
              source_ref: str | None = None, idempotency_key: str | None = None) -> ProjectEvent | None:
    """Append to the project's timeline. Returns None if this idempotency key was already recorded."""
    if idempotency_key and db.scalar(select(ProjectEvent.id).where(ProjectEvent.idempotency_key == idempotency_key)):
        return None
    ev = ProjectEvent(project_id=project.id, event_type=event_type, source=source, summary=summary,
                      payload=jsonable(payload or {}), actor_user_id=actor.id if actor else None,
                      actor_label=actor_label or (actor.full_name if actor else source),
                      source_ref=source_ref, idempotency_key=idempotency_key)
    db.add(ev)
    return ev


def queue_sheet_sync(db: Session) -> None:
    enqueue(db, "sheets_sync", {"trigger": "change"}, coalesce=True)


def _check_contractor(db: Session, contractor_id: int | None):
    c = db.get(Contractor, contractor_id) if contractor_id is not None else None
    if contractor_id is not None and not c:
        raise HTTPException(422, "Unknown contractor")
    if c and c.kind == "sacrifices":
        raise HTTPException(422, "هذا مقاول ذبائح، ويُختار من صفحة الذبائح فقط")


def _enforce_dates(p: Project):
    if p.construction_status == ConstructionStatus.completed and not p.completion_date:
        p.completion_date = date.today()
    if p.construction_status == ConstructionStatus.in_progress and not p.construction_start_date:
        p.construction_start_date = date.today()
    # A finished well becomes "pending delivery" until an approved confirmation arrives.
    if p.construction_status == ConstructionStatus.completed and p.delivery_status == DeliveryStatus.not_ready:
        p.delivery_status = DeliveryStatus.pending


def _country_from_contractor(db: Session, p: Project, old_contractor_id: int | None = None) -> None:
    """Country is no longer typed on the forms: it follows the contractor (reports by country keep working).
    A country that was typed by hand and differs from the old contractor's country is left alone."""
    if not p.contractor_id:
        return
    new = db.get(Contractor, p.contractor_id)
    if not new or not new.country:
        return
    old = db.get(Contractor, old_contractor_id) if old_contractor_id else None
    if not p.country or (old and p.country == old.country):
        p.country = new.country


def create_project(db: Session, data: dict, *, actor: User | None, source: str = "dashboard",
                   ip: str | None = None, is_sample: bool = False) -> Project:
    if get_by_well_id(db, data["well_id"]):
        raise HTTPException(409, f"Well ID {data['well_id']} already exists")
    if actor and actor.role not in FINANCE_ROLES and data.get("cost") is not None:
        raise HTTPException(403, "Only managers can set the well cost")
    _check_contractor(db, data.get("contractor_id"))
    hints = data.pop("_phone_hints", None)
    fallback = data.pop("_phone_fallback_country", None)
    if data.get("extras") is not None:
        data["extras"] = addons.normalize(data["extras"])
    p = Project(**data, is_sample=is_sample)
    phones.apply(p, hints=hints, fallback_country=fallback)
    _country_from_contractor(db, p)
    _enforce_dates(p)
    try:
        with db.begin_nested():
            db.add(p)
            db.flush()
    except IntegrityError:
        raise HTTPException(409, f"Well ID {data['well_id']} already exists")
    add_event(db, p, "project_created", source=source, actor=actor, summary=f"Project {p.well_id} created",
              payload={"fields": snapshot(p)})
    audit(db, "project.create", "project", p.well_id, actor=actor, after=snapshot(p), ip=ip)
    from app.services.plaque_flow import maybe_create_for_new_order
    maybe_create_for_new_order(db, p, source=source, is_sample=is_sample, actor=actor)
    addons.sync_sheep(db, p, actor=actor, source=source)
    queue_sheet_sync(db)
    return p


def update_project(db: Session, project: Project, changes: dict, *, actor: User | None, source: str = "dashboard",
                   ip: str | None = None, expected_version: int | None = None,
                   allow_delivery_fields: bool = False) -> Project:
    if expected_version is not None and expected_version != project.version:
        raise HTTPException(409, "This project was changed by someone else. Reload and try again.")
    forbidden = {"well_id", "id", "version", "merged_into_id"}
    if not allow_delivery_fields:
        forbidden |= {"delivery_status", "delivery_date"}
    bad = forbidden & set(changes)
    if bad:
        raise HTTPException(422, f"These fields cannot be changed here: {', '.join(sorted(bad))}")
    if actor and actor.role == Role.contractor:
        allowed = {"construction_status", "construction_start_date", "completion_date", "notes"}
        if set(changes) - allowed:
            raise HTTPException(403, "Contractors may only update construction progress and notes")
        if actor.contractor_id is None or project.contractor_id != actor.contractor_id:
            raise HTTPException(403, "This project is not assigned to you")
    if actor and actor.role not in FINANCE_ROLES and "cost" in changes:
        raise HTTPException(403, "Only managers can change the well cost")
    if "contractor_id" in changes:
        _check_contractor(db, changes["contractor_id"])
    if changes.get("extras") is not None:
        changes = {**changes, "extras": addons.normalize(changes["extras"])}
    before = snapshot(project)
    for k, v in changes.items():
        setattr(project, k, v)
    if {"customer_phone", "customer_phone_country"} & set(changes):
        phones.apply(project)
    if "contractor_id" in changes and "country" not in changes:
        _country_from_contractor(db, project, before.get("contractor_id"))
    _enforce_dates(project)
    after = snapshot(project)
    diff = {k: {"from": before.get(k), "to": after.get(k)} for k in after if before.get(k) != after.get(k)}
    if not diff:
        return project
    project.updated_at = utcnow()
    db.flush()
    etype = "construction_update" if "construction_status" in diff else "project_updated"
    add_event(db, project, etype, source=source, actor=actor, payload={"changes": diff},
              summary=", ".join(f"{k}: {v['from']} → {v['to']}" for k, v in diff.items())[:500])
    audit(db, "project.update", "project", project.well_id, actor=actor, before=before, after=snapshot(project), ip=ip)
    if "extras" in diff:
        addons.sync_sheep(db, project, actor=actor, source=source)
    queue_sheet_sync(db)
    return project


def list_projects(db: Session, *, q: str | None = None, country: str | None = None,
                  construction_status: str | None = None, delivery_status: str | None = None,
                  contractor_id: int | None = None, page: int = 1, page_size: int = 50,
                  sort: str = "-listed_at", contractor_scope: int | None = None, month: str | None = None,
                  hide_waiting_contractor: bool = False):
    stmt = select(Project).where(Project.merged_into_id.is_(None))
    if hide_waiting_contractor:
        # Employees: a well whose plaque is approved and waiting for the contractor is the manager's next step,
        # so it is left out of their lists and search (still open by number, and on the contractor's page once
        # a contractor is set). Nothing is hidden from managers and nothing is changed (Hayah, 2026-11-19).
        from app.models import Plaque, PlaqueStatus
        waiting = select(Plaque.project_id).where(Plaque.project_id.is_not(None),
                                                  Plaque.status == PlaqueStatus.approved_for_contractor)
        stmt = stmt.where(Project.id.not_in(waiting))
    if month:
        from app.services.finance import month_bounds
        a, b = month_bounds(month)
        stmt = stmt.where(Project.order_date >= a, Project.order_date < b)
    if q:
        like = f"%{q.strip()}%"
        conds = [Project.customer_name.ilike(like), Project.city.ilike(like), Project.village.ilike(like),
                 Project.notes.ilike(like)]
        if q.strip().isdigit():
            conds.append(Project.well_id == int(q.strip()))
        from sqlalchemy import or_
        stmt = stmt.where(or_(*conds))
    if country:
        stmt = stmt.where(Project.country == country)
    if construction_status:
        stmt = stmt.where(Project.construction_status == construction_status)
    if delivery_status:
        stmt = stmt.where(Project.delivery_status == delivery_status)
    if contractor_id:
        stmt = stmt.where(Project.contractor_id == contractor_id)
    if contractor_scope is not None:
        stmt = stmt.where(Project.contractor_id == contractor_scope)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    col = getattr(Project, sort.lstrip("-"), Project.well_id)
    # newest first by default: the place each project got when it was added (projects.listed_at), then the
    # higher Well ID; editing a project never moves it (services/project_order.py)
    stmt = stmt.order_by((col.desc() if sort.startswith("-") else col.asc()).nulls_last(),
                         Project.well_id.desc() if sort.startswith("-") else Project.well_id.asc())
    items = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique())
    return items, total


def request_merge(db: Session, source: Project, target: Project, reason: str, actor: User) -> ReviewCase:
    if source.id == target.id:
        raise HTTPException(422, "Cannot merge a project into itself")
    case = ReviewCase(kind=ReviewKind.merge_request, reason=reason, project_id=source.id,
                      proposed={"source_well_id": source.well_id, "target_well_id": target.well_id,
                                "requested_by": actor.email},
                      dedupe_key=f"merge:{source.well_id}:{target.well_id}")
    try:
        with db.begin_nested():
            db.add(case)
            db.flush()
    except IntegrityError:
        raise HTTPException(409, "A merge request for these projects already exists")
    audit(db, "project.merge_requested", "project", source.well_id, actor=actor, after=case.proposed)
    return case


def apply_merge(db: Session, source: Project, target: Project, actor: User) -> None:
    """Approved merge: the source keeps all its history but is marked merged; its
    events, media and records are re-pointed to the target. Nothing is deleted."""
    from sqlalchemy import update
    from app.models import DeliveryConfirmation, InboundMessage, MaintenanceRecord, MediaAsset
    for model in (ProjectEvent, MediaAsset, MaintenanceRecord, DeliveryConfirmation, InboundMessage):
        db.execute(update(model).where(model.project_id == source.id).values(project_id=target.id))
    source.merged_into_id = target.id
    source.notes = ((source.notes or "") + f"\n[merged into {target.well_id}]").strip()
    add_event(db, target, "project_merged", source="dashboard", actor=actor,
              summary=f"Well {source.well_id} merged into {target.well_id}",
              payload={"source_well_id": source.well_id})
    audit(db, "project.merge_applied", "project", target.well_id, actor=actor,
          after={"source_well_id": source.well_id, "target_well_id": target.well_id})
    queue_sheet_sync(db)

"""Dashboard KPIs, reports, sync controls, settings, audit and health."""
from datetime import date, timedelta

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import ADMINS, ALL_ROLES, MANAGERS, PROJECT_CREATORS, get_current_user, require_roles
from app.integrations.drive import get_drive_client
from app.models import (
    ApprovalStatus, AuditLog, ConstructionStatus, Contractor, DeliveryConfirmation, DeliveryStatus, Job, JobStatus,
    MaintenanceRecord, MaintenanceStatus, Project, ReviewCase, ReviewStatus, SyncConflict, User, VideoStatus,
)
from app.schemas import AISettingsIn, ConflictResolve, SyncConflictOut
from app.services import sales_sources, sheets_sync, usage, well_types
from app.services.audit import audit
from app.services.jobs import enqueue, retry_job, run_due_jobs
from app.services.secrets_store import anthropic_key_hint, set_anthropic_key
from app.services.settings_store import get_setting, set_setting

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/nav")
def nav(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What the side menu lists for this person: month pages, contractors by country, partners.
    Finance pages (contractor ledgers, partners, banks) are for managers only; sacrifice months
    are listed for employees too (their sacrifice pages never show cost or profit)."""
    from app.models import FinanceAccount, Role
    from app.services.finance import months
    manager = user.role in MANAGERS
    m = months(db)
    out: dict = {"current": m["current"], "wells": m["wells"], "sacrifices": m["sacrifices"] if user.role in PROJECT_CREATORS else [],
                 "contractors": [], "partners": [], "banks": []}
    if user.role != Role.contractor:
        cons = db.scalars(select(Contractor).where(Contractor.is_active.is_(True)).order_by(Contractor.code))
        out["contractors"] = [{"id": c.id, "code": c.code, "name": c.name, "country": c.country or "", "color": c.color}
                              for c in cons]
    if manager:
        accs = list(db.scalars(select(FinanceAccount).where(FinanceAccount.is_active.is_(True))
                               .order_by(FinanceAccount.sort_order, FinanceAccount.id)))
        out["partners"] = [{"code": a.code, "name": a.name} for a in accs if a.kind == "partner"]
        out["banks"] = [{"code": a.code, "name": a.name} for a in accs if a.kind == "bank"]
    return out


@router.get("/ops/counts")
def ops_counts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The live red/orange/green numbers for the menu and dashboard (polled every few seconds).
    Counts only, never money. Employees and managers only."""
    from app.deps import PROJECT_CREATORS
    from app.services import final_video, plaque_flow
    if user.role not in PROJECT_CREATORS:
        return {}
    new_orders = db.scalar(select(func.count()).select_from(Project).where(
        Project.merged_into_id.is_(None), Project.is_sample.is_(False), Project.construction_status == ConstructionStatus.new_order))
    from app.services import wa_inbox
    return {"plaques": plaque_flow.counts(db, for_manager=user.role in MANAGERS), "videos": final_video.counts(db), "orders": {"new": new_orders or 0},
            "whatsapp": {**wa_inbox.counts(db), "enabled": wa_inbox.enabled(db)}}


def _monthly_trend(db: Session, months: int = 12) -> dict:
    """Counts per month for the small charts on the dashboard cards (no money): well orders, wells finished,
    wells delivered and sacrifices, for the last `months` months ending with this month."""
    today = date.today()
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    keys.reverse()
    start = date(int(keys[0][:4]), int(keys[0][5:]), 1)
    out = {"months": keys}
    for name, table, col, extra in [("orders", "projects", "order_date", "merged_into_id is null"),
                                    ("completed", "projects", "completion_date", "merged_into_id is null"),
                                    ("delivered", "projects", "delivery_date", "merged_into_id is null"),
                                    ("sacrifices", "sacrifices", "order_date", "true")]:
        rows = dict(db.execute(text(f"select to_char(date_trunc('month', {col}), 'YYYY-MM'), count(*) from {table} "
                                    f"where {extra} and {col} >= :s and {col} <= :e group by 1"), {"s": start, "e": today}).all())
        out[name] = [int(rows.get(k, 0)) for k in keys]
    return out


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    live = Project.merged_into_id.is_(None)
    count = lambda *c: db.scalar(select(func.count()).select_from(Project).where(live, *c))  # noqa: E731
    kpis = {
        "total_projects": count(),
        "new_orders": count(Project.construction_status == ConstructionStatus.new_order),
        "in_progress": count(Project.construction_status.in_([ConstructionStatus.in_progress, ConstructionStatus.scheduled])),
        "completed": count(Project.construction_status == ConstructionStatus.completed),
        "delivered": count(Project.delivery_status == DeliveryStatus.delivered),
        "pending_delivery": count(Project.delivery_status == DeliveryStatus.pending),
        "videos_processing": count(Project.video_status.in_([VideoStatus.raw_received, VideoStatus.processing, VideoStatus.in_review])),
        "videos_completed": count(Project.video_status == VideoStatus.completed),
        "maintenance_cases": db.scalar(select(func.count()).select_from(MaintenanceRecord).where(
            MaintenanceRecord.status.in_([MaintenanceStatus.open, MaintenanceStatus.in_progress]))),
        "pending_review": db.scalar(select(func.count()).select_from(ReviewCase).where(ReviewCase.status == ReviewStatus.pending)),
        "pending_delivery_approvals": db.scalar(select(func.count()).select_from(DeliveryConfirmation).where(
            DeliveryConfirmation.status == ApprovalStatus.pending)),
    }
    by_country = db.execute(select(Project.country, func.count()).where(live).group_by(Project.country)
                            .order_by(func.count().desc())).all()
    by_status = db.execute(select(Project.construction_status, func.count()).where(live)
                           .group_by(Project.construction_status)).all()
    recent = db.execute(text("""select e.created_at, p.well_id, e.event_type, e.summary, e.actor_label, e.source
                                from project_events e join projects p on p.id = e.project_id
                                order by e.created_at desc limit 15""")).mappings().all()
    return {"kpis": kpis, "trend": _monthly_trend(db), "by_country": [{"country": c or "—", "count": n} for c, n in by_country],
            "by_construction_status": [{"status": s.value if hasattr(s, "value") else s, "count": n} for s, n in by_status],
            "recent_activity": [dict(r) for r in recent], "sheets": sheets_sync.status(db)}


@router.get("/reports/summary")
def report(start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
           user: User = Depends(require_roles(ALL_ROLES))):
    end = end or date.today()
    start = start or end - timedelta(days=365)
    live = Project.merged_into_id.is_(None)
    monthly = db.execute(text("""select to_char(date_trunc('month', order_date), 'YYYY-MM') m, count(*) n,
                                 coalesce(sum(sale_amount),0) amount from projects
                                 where merged_into_id is null and order_date between :s and :e group by 1 order by 1"""),
                         {"s": start, "e": end}).all()
    delivered = db.execute(text("""select to_char(date_trunc('month', delivery_date), 'YYYY-MM') m, count(*) from projects
                                   where merged_into_id is null and delivery_date between :s and :e group by 1 order by 1"""),
                           {"s": start, "e": end}).all()
    by_type = db.execute(select(Project.well_type, func.count()).where(live).group_by(Project.well_type)).all()
    by_payment = db.execute(select(Project.payment_status, func.count(), func.coalesce(func.sum(Project.sale_amount), 0))
                            .where(live).group_by(Project.payment_status)).all()
    grp = func.coalesce(Project.source_group, "Unknown")
    by_source = db.execute(select(grp, func.count(), func.coalesce(func.sum(Project.sale_amount), 0))
                           .where(live, Project.order_date.between(start, end)).group_by(grp).order_by(func.count().desc())).all()
    maint = db.execute(select(MaintenanceRecord.problem_type, func.count(), func.coalesce(func.sum(MaintenanceRecord.repair_cost), 0))
                       .group_by(MaintenanceRecord.problem_type)).all()
    return {"start": start, "end": end,
            "orders_by_month": [{"month": m, "orders": n, "amount": float(a)} for m, n, a in monthly],
            "deliveries_by_month": [{"month": m, "delivered": n} for m, n in delivered],
            "by_well_type": [{"well_type": t or "—", "count": n} for t, n in by_type],
            "by_sales_source": [{"source": g, "count": n, "amount": float(a)} for g, n, a in by_source],
            "by_payment_status": [{"status": s.value, "count": n, "amount": float(a)} for s, n, a in by_payment],
            "maintenance_by_problem": [{"problem_type": p, "count": n, "cost": float(c) if user.role in MANAGERS else None}
                                       for p, n, c in maint]}


# ---------- Google Sheets sync ----------
@router.get("/sync/status")
def sync_status(db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    return sheets_sync.status(db)


@router.post("/sync/run")
def sync_now(db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    audit(db, "sync.manual_run", "sync", "sheets", actor=user)
    db.commit()
    try:
        run = sheets_sync.run_sync(db, trigger="manual")
        return {"status": run.status, "stats": run.stats}
    except Exception as exc:  # recorded on the SyncRun; queue an automatic retry
        enqueue(db, "sheets_sync", {"trigger": "retry"}, coalesce=True)
        db.commit()
        raise HTTPException(502, f"Sync failed and will retry automatically: {exc}")


@router.get("/sync/conflicts", response_model=list[SyncConflictOut])
def conflicts(status: str = "open", db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    return list(db.scalars(select(SyncConflict).where(SyncConflict.status == status).order_by(SyncConflict.id.desc())))


@router.post("/sync/conflicts/{cid}/resolve", response_model=SyncConflictOut)
def resolve(cid: int, body: ConflictResolve, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    c = db.get(SyncConflict, cid)
    if not c:
        raise HTTPException(404, "Conflict not found")
    sheets_sync.resolve_conflict(db, c, body.keep, user)
    db.commit()
    return c


# ---------- jobs ----------
@router.get("/jobs")
def jobs(status: JobStatus | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    q = select(Job).order_by(Job.id.desc()).limit(200)
    if status:
        q = q.where(Job.status == status)
    return [{"id": j.id, "kind": j.kind, "status": j.status.value, "attempts": j.attempts, "max_attempts": j.max_attempts,
             "next_run_at": j.next_run_at, "last_error": (j.last_error or "")[:500], "created_at": j.created_at}
            for j in db.scalars(q)]


@router.post("/jobs/{job_id}/retry")
def retry(job_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    retry_job(db, j)
    audit(db, "job.retry", "job", j.id, actor=user)
    db.commit()
    return {"ok": True}


@router.post("/jobs/run-now")
def run_now(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    return run_due_jobs(db)


# ---------- settings ----------
@router.get("/settings")
def get_settings_view(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    s = get_settings()
    return {
        "integrations": {
            "sheets": {"backend": s.sheets_backend, "configured": s.sheets_backend == "mock" or bool(s.sheets_spreadsheet_id)},
            "drive": {"backend": s.drive_backend},
            "whatsapp": {"backend": s.whatsapp_backend, "verify_token_set": bool(s.whatsapp_verify_token),
                         "app_secret_set": bool(s.whatsapp_app_secret), "phone_number_id_set": bool(s.whatsapp_phone_number_id)},
            "ai": {"backend": s.ai_backend, "api_key": anthropic_key_hint(db), "api_key_set": anthropic_key_hint(db)["set"], "model": s.anthropic_model},
        },
        "ai": get_setting(db, "ai"), "well_types": get_setting(db, "well_types"),
        "countries": get_setting(db, "countries"), "animal_types": get_setting(db, "animal_types"), "branding": get_setting(db, "branding"),
        "usage_this_month": usage.summary(db), "ai_cost_this_month_usd": usage.month_ai_cost(db),
    }


@router.put("/settings/ai")
def put_ai(body: AISettingsIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    before = get_setting(db, "ai")
    set_setting(db, "ai", body.model_dump(), user.id)
    audit(db, "settings.ai", "settings", "ai", actor=user, before=before, after=body.model_dump())
    db.commit()
    return body


class APIKeyIn(BaseModel):
    api_key: str = Field(default="", max_length=300)


@router.put("/settings/ai-key")
def put_ai_key(body: APIKeyIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    """Paste (or clear, with an empty value) the Anthropic API key. It is stored encrypted and never shown again."""
    key = body.api_key.strip()
    if key and not key.startswith("sk-ant-"):
        raise HTTPException(422, "That doesn't look like an Anthropic API key (it starts with sk-ant-)")
    set_anthropic_key(db, key or None, user.id)
    audit(db, "settings.ai_key", "settings", "ai", actor=user, after={"set": bool(key), "last4": key[-4:] if key else None})
    db.commit()
    return anthropic_key_hint(db)


@router.get("/settings/lists")
def get_lists(db: Session = Depends(get_db), _: User = Depends(require_roles(ALL_ROLES))):
    """Dropdown values used by the sheets. Well types are always the four HAYAH types."""
    from app.services import addons
    out = {k: get_setting(db, k).get("values", []) for k in ("countries", "animal_types")}
    return {"well_types": list(well_types.TYPES), "sales_sources": sales_sources.group_names(db), **out,
            **addons.options(db)}


# ---------------- unified sales sources (managed here, no code change needed) ----------------
class SourceGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    values: list[str] = []


@router.get("/admin/sales-sources")
def get_sources(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    return sales_sources.overview(db)


@router.put("/admin/sales-sources")
def put_sources(body: list[SourceGroupIn], db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    r = sales_sources.save_groups(db, [g.model_dump() for g in body], user)
    db.commit()
    return {**sales_sources.overview(db), "records_changed": r["records_changed"]}


@router.put("/settings/lists/{key}")
def put_list(key: str, values: list[str], db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    if key not in ("well_types", "countries", "animal_types", "well_addons", "sacrifice_addons"):
        raise HTTPException(404, "Unknown list")
    clean = sorted({v.strip()[:80] for v in values if v.strip()})
    if key in ("well_addons", "sacrifice_addons"):  # keep the order typed (the form shows them in this order)
        clean = list(dict.fromkeys(v.strip()[:80].replace(",", " ").replace("،", " ") for v in values if v.strip()))
    if key == "well_types":  # one name per type: long names fold into the four types
        clean = [t for t in well_types.TYPES if t in {well_types.normalize(v) for v in clean}] or list(well_types.TYPES)
    set_setting(db, key, {"values": clean}, user.id)
    audit(db, f"settings.{key}", "settings", key, actor=user, after={"values": clean})
    db.commit()
    return {"values": clean}


# ---------------- well types: one name per type ----------------
@router.get("/admin/well-types")
def well_types_status(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    conn = db.connection()
    counts = db.execute(select(Project.well_type, func.count()).where(Project.merged_into_id.is_(None))
                        .group_by(Project.well_type)).all()
    return {"types": well_types.TYPES, "legacy": well_types.LEGACY,
            "counts": [{"value": v, "count": n} for v, n in sorted(counts, key=lambda r: -r[1])],
            "pending": well_types.preview(conn), "unknown": well_types.unknown(conn), "runs": well_types.runs(conn)}


@router.post("/admin/well-types/normalize")
def well_types_normalize(db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    out = well_types.normalize_rows(db.connection(), actor_label=user.full_name, actor_id=user.id)
    db.commit()
    return out


@router.post("/admin/well-types/undo/{audit_id}")
def well_types_undo(audit_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    try:
        out = well_types.undo_rows(db.connection(), audit_id, actor_label=user.full_name, actor_id=user.id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return out


@router.get("/audit")
def audit_log(entity_type: str | None = None, entity_id: str | None = None, limit: int = 200,
              db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    return [{"id": a.id, "at": a.at, "actor": a.actor_label, "action": a.action, "entity_type": a.entity_type,
             "entity_id": a.entity_id, "before": a.before, "after": a.after, "ip": a.ip} for a in db.scalars(q)]


@router.get("/health")
def health(db: Session = Depends(get_db)):
    out = {"database": "ok"}
    try:
        db.execute(text("select 1"))
    except Exception as e:  # noqa: BLE001
        out["database"] = f"error: {e}"
    out["failed_jobs"] = db.scalar(select(func.count()).select_from(Job).where(Job.status == JobStatus.failed))
    out["status"] = "ok" if out["database"] == "ok" else "degraded"
    return out


@router.get("/health/full")
def health_full(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    out = health(db)
    out["sheets"] = sheets_sync.status(db)["state"]
    try:
        q = get_drive_client().storage_quota()
        out["drive"] = {"usage_gb": round(q["usage"] / 1024**3, 2),
                        "limit_gb": round(q["limit"] / 1024**3, 2) if q.get("limit") else None,
                        "percent": round(100 * q["usage"] / q["limit"], 1) if q.get("limit") else None}
    except Exception as e:  # noqa: BLE001
        out["drive"] = {"error": str(e)}
    return out

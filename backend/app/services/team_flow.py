"""Who does what on each well order (Hayah, 21 Nov 2026).

Three parts, one after the other, each owned by one person (users.team_stage):

  intake   غازي   استلام الطلب ← تحديد الدولة ← اختيار المقاول
  customer شذى    التواصل مع العميل ← تصميم اللوحة ← إرسالها للموافقة ← تسجيل الموافقة
  delivery غيداء  مراجعة رقم الطلب والهاتف ← رفع الفيديو النهائي ← جاهز للتسليم ← استكمال التسليم

Only three steps are ticked by hand and kept in team_steps: received, contacted, checked.
Everything else is read from the order itself, its plaque and its final video, so the existing
pages (designer, plaque WhatsApp icon, final video page, delivery tiles) move the tasks forward
on their own and nothing is entered twice.

An order sits in the first part that is not finished. Delivered, cancelled and merged orders and
orders dated before the start date (Settings, default 1 Nov 2026) are left out, so the imported
history does not flood the lists. No cost, price or money is ever returned from here.
"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    ConstructionStatus, DeliveryStatus, FinalVideo, FinalVideoStatus as V, Plaque, PlaqueStatus as S, PlaqueVersion,
    Project, TeamStep, User, utcnow,
)
from app.services.audit import audit
from app.services.settings_store import get_setting, set_setting

STAGES = ("intake", "customer", "delivery")
STAGE_AR = {"intake": "استلام الطلبات وتوزيعها", "customer": "التواصل مع العملاء واللوحات", "delivery": "مراجعة الطلبات والتسليم"}
STEPS = {
    "intake": ["received", "country", "contractor"],
    "customer": ["contacted", "designed", "sent", "approved"],
    "delivery": ["checked", "video", "ready", "delivered"],
}
STEP_AR = {
    "received": "استلام الطلب", "country": "تحديد الدولة", "contractor": "اختيار المقاول",
    "contacted": "التواصل مع العميل", "designed": "تصميم اللوحة", "sent": "إرسالها للموافقة", "approved": "تسجيل موافقة العميل",
    "checked": "مراجعة رقم الطلب والهاتف", "video": "رفع الفيديو النهائي", "ready": "جاهز للتسليم", "delivered": "استكمال التسليم",
}
MANUAL = {"received": "intake", "contacted": "customer", "checked": "delivery"}
DEFAULT_START = "2026-11-01"
APPROVED = {S.customer_approved, S.approved_for_contractor, S.sent_to_contractor}
SENT = {S.awaiting_customer} | APPROVED


# ---------------------------------------------------------------- settings
def settings(db: Session) -> dict:
    s = get_setting(db, "team_flow") or {}
    return {"start_date": s.get("start_date") or DEFAULT_START}


def save_settings(db: Session, start_date: date, actor: User) -> dict:
    before = settings(db)
    set_setting(db, "team_flow", {"start_date": start_date.isoformat()}, actor.id)
    audit(db, "team.settings", "setting", "team_flow", actor=actor, before=before, after=settings(db))
    return settings(db)


def members(db: Session) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {s: [] for s in STAGES}
    for u in db.scalars(select(User).where(User.is_active.is_(True), User.team_stage.isnot(None)).order_by(User.full_name)):
        if u.team_stage in out:
            out[u.team_stage].append({"id": u.id, "name": u.full_name})
    return out


# ---------------------------------------------------------------- reading one order
def _phone_ok(p: Project) -> bool:
    return p.customer_phone_status == "valid" and bool(p.customer_phone_e164)


def steps_of(p: Project, pl: Plaque | None, has_file: bool, fv: FinalVideo | None, manual: dict[str, TeamStep]) -> dict:
    """Every step of the order: done or not, and by whom / when for the hand-ticked ones."""
    st = pl.status if pl else None
    vs = fv.status if fv else V.not_uploaded
    sent = bool(pl and (pl.sent_to_customer_at or st in SENT))
    done = {
        "received": "received" in manual,
        "country": bool((p.country or "").strip()),
        "contractor": p.contractor_id is not None,
        # The plaque WhatsApp icon sends the first message with the plaque, so it counts as contact too.
        "contacted": "contacted" in manual or sent,
        "designed": has_file or st in APPROVED,
        "sent": sent,
        "approved": st in APPROVED,
        "checked": "checked" in manual,
        "video": vs != V.not_uploaded,
        "ready": vs in (V.ready_for_delivery, V.sent_to_customer),
        "delivered": vs == V.sent_to_customer or p.delivery_status == DeliveryStatus.delivered,
    }
    out = {}
    for k, v in done.items():
        m = manual.get(k)
        out[k] = {"done": v, "label": STEP_AR[k], "by": m.done_by if m else None,
                  "at": m.done_at.isoformat() if m else None, "note": m.note if m else None}
    return out


def stage_of(steps: dict) -> str | None:
    for s in STAGES:
        if not all(steps[k]["done"] for k in STEPS[s]):
            return s
    return None


def _card(p: Project, pl: Plaque | None, has_file: bool, fv: FinalVideo | None, manual: dict) -> dict:
    steps = steps_of(p, pl, has_file, fv, manual)
    stage = stage_of(steps)
    nxt = next((k for k in STEPS[stage] if not steps[k]["done"]), None) if stage else None
    return {
        "well_id": p.well_id, "order_date": p.order_date.isoformat() if p.order_date else None,
        "customer_name": p.customer_name, "dedication": p.dedication,
        "customer_phone": p.customer_phone, "customer_phone_e164": p.customer_phone_e164,
        "customer_phone_status": p.customer_phone_status, "phone_ok": _phone_ok(p),
        "shopify_order": p.shopify_order, "sales_source": p.sales_source,
        "country": p.country, "contractor_id": p.contractor_id,
        "contractor_code": p.contractor.code if p.contractor else None,
        "contractor_name": p.contractor.name if p.contractor else None,
        "well_type": p.well_type, "construction_status": p.construction_status.value,
        "plaque_id": pl.id if pl else None, "plaque_status": pl.status.value if pl else None,
        "plaque_missing": list(pl.missing or []) if pl else [],
        "video_status": (fv.status if fv else V.not_uploaded).value,
        "stage": stage, "next_step": nxt, "steps": steps,
    }


def _active_query(db: Session):
    start = date.fromisoformat(settings(db)["start_date"])
    return (select(Project).where(
        Project.merged_into_id.is_(None),
        Project.construction_status != ConstructionStatus.cancelled,
        Project.delivery_status != DeliveryStatus.delivered,
        or_(Project.order_date >= start, Project.order_date.is_(None) & (Project.created_at >= start)),
    ).order_by(Project.order_date.asc().nullslast(), Project.well_id.asc()))


def _load(db: Session, projects: list[Project]) -> list[dict]:
    ids = [p.id for p in projects]
    if not ids:
        return []
    plaques = {pl.project_id: pl for pl in db.scalars(select(Plaque).where(Plaque.project_id.in_(ids)))}
    vids = [pl.current_version_id for pl in plaques.values() if pl.current_version_id]
    with_file = set(db.scalars(select(PlaqueVersion.id).where(
        PlaqueVersion.id.in_(vids), or_(PlaqueVersion.media_id.isnot(None), PlaqueVersion.drive_file_id.isnot(None))))) if vids else set()
    videos = {fv.project_id: fv for fv in db.scalars(select(FinalVideo).where(FinalVideo.project_id.in_(ids)))}
    manual: dict[int, dict[str, TeamStep]] = {}
    for t in db.scalars(select(TeamStep).where(TeamStep.project_id.in_(ids))):
        manual.setdefault(t.project_id, {})[t.step] = t
    out = []
    for p in projects:
        pl = plaques.get(p.id)
        c = _card(p, pl, bool(pl and pl.current_version_id in with_file), videos.get(p.id), manual.get(p.id, {}))
        if pl and c["stage"] == "customer":  # what the plaque still needs, as of now (country may have been set since)
            from app.services.plaque_flow import compute_missing
            c["plaque_missing"] = compute_missing(db, pl, p)
        out.append(c)
    return out


def tasks(db: Session, stage: str | None = None, limit: int = 300) -> list[dict]:
    cards = _load(db, list(db.scalars(_active_query(db))))
    cards = [c for c in cards if c["stage"]]
    if stage:
        cards = [c for c in cards if c["stage"] == stage]
    return cards[:limit]


def counts(db: Session) -> dict[str, int]:
    out = {s: 0 for s in STAGES}
    for c in tasks(db, limit=100000):
        out[c["stage"]] += 1
    return out


def card_for(db: Session, p: Project) -> dict:
    return _load(db, [p])[0]


# ---------------------------------------------------------------- ticking a step by hand
def set_step(db: Session, p: Project, step: str, done: bool, actor: User, note: str | None = None) -> dict:
    if step not in MANUAL:
        raise HTTPException(422, "This step is completed from its own page, not ticked by hand")
    row = db.scalar(select(TeamStep).where(TeamStep.project_id == p.id, TeamStep.step == step).with_for_update())
    if done:
        if step == "checked" and not _phone_ok(p):
            raise HTTPException(409, "رقم هاتف العميل غير صحيح أو بلا رمز الدولة. صحّحه أولاً ثم أكّد المراجعة.")
        if step == "checked" and not p.well_id:
            raise HTTPException(409, "Order number is missing")
        if row:
            return card_for(db, p)
        db.add(TeamStep(project_id=p.id, step=step, done_at=utcnow(), done_by_id=actor.id, done_by=actor.full_name,
                        note=(note or "").strip() or None))
    else:
        if not row:
            return card_for(db, p)
        db.delete(row)
    from app.services.projects import add_event
    add_event(db, p, "team_step", source="dashboard", actor=actor,
              summary=("✓ " if done else "↺ ") + STEP_AR[step] + (f" · {note.strip()}" if note and note.strip() else ""),
              payload={"step": step, "done": done, "note": note})
    audit(db, "team.step", "project", p.id, actor=actor, after={"well_id": p.well_id, "step": step, "done": done, "note": note})
    db.flush()
    return card_for(db, p)

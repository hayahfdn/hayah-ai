"""Who does what on each well order (Hayah, 21 Nov 2026, second version).

Eight stages, one after the other. Each stage has ONE responsible person (app setting "team_owners");
the manager can move one order's stage to someone else (team_assignments). A person's task is done only
when it is closed and documented (who, when, how), not when the work was started.

  1 intake      غازي   استلام الطلب ← تحديد الدولة ← اختيار المقاول
  2 design      شذى    إرسال الرسالة الأولى ← تصميم اللوحة ← إرسالها للعميل
  3 approval    شذى    تسجيل موافقة العميل (أو اعتماد المديرة مباشرة)
  4 contractor  غازي   إرسال اللوحة للمقاول ← إرسال قائمة المتطلبات ← وصول الفيديو من المقاول
  5 review      غيداء  تدقيق الهاتف والطلب ← رفع الفيديو ← جاهز للتسليم
  6 certificate النظام  تجهيز الشهادة الوقفية وحفظها في ملف المشروع (automatic at «جاهز للتسليم»)
  7 delivery    شذى    إرسال الفيديو والشهادة للعميل ← تأكيد التسليم
  8 close       المديرة تسجيل تاريخ التسليم وإغلاق المشروع

Hand-ticked steps are kept in team_steps with who/when/note; the others are read from the order, its
plaque, its final video and its certificate, so the usual pages move the tasks forward too.
Delivered, cancelled and merged orders and orders before the start date are left out.
No cost, price or money is ever returned from here.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    ConstructionStatus, DeliveryStatus, FinalVideo, FinalVideoStatus as V, Plaque, PlaqueStatus as S, PlaqueVersion,
    Project, ProjectEvent, Role, TeamAssignment, TeamStep, User, utcnow,
)
from app.services.audit import audit
from app.services.settings_store import get_setting, set_setting

STAGES = ("intake", "design", "approval", "contractor", "review", "certificate", "delivery", "close")
STAGE_AR = {
    "intake": "استلام الطلب", "design": "التواصل والتصميم", "approval": "اعتماد اللوحة",
    "contractor": "إرسال للمقاول", "review": "مراجعة ورفع الفيديو", "certificate": "تجهيز الشهادة",
    "delivery": "التسليم النهائي", "close": "إغلاق المشروع",
}
STEPS = {
    "intake": ["received", "country", "contractor"],
    "design": ["contacted", "designed", "sent"],
    "approval": ["approved"],
    "contractor": ["plaque_sent", "requirements", "video_received"],
    "review": ["checked", "video", "ready"],
    "certificate": ["certificate"],
    "delivery": ["sent_customer", "confirmed"],
    "close": ["closed"],
}
STEP_AR = {
    "received": "استلام الطلب", "country": "تحديد الدولة", "contractor": "اختيار المقاول",
    "contacted": "إرسال الرسالة الأولى", "designed": "تصميم اللوحة", "sent": "إرسالها للعميل",
    "approved": "تسجيل موافقة العميل",
    "plaque_sent": "إرسال اللوحة للمقاول", "requirements": "إرسال قائمة المتطلبات", "video_received": "وصول الفيديو",
    "checked": "تدقيق الهاتف والطلب", "video": "رفع الفيديو", "ready": "جاهز للتسليم",
    "certificate": "تجهيز الشهادة وحفظها",
    "sent_customer": "إرسال الفيديو والشهادة", "confirmed": "تأكيد التسليم",
    "closed": "تسجيل تاريخ التسليم وإغلاق المشروع",
}
# Steps ticked by hand (documented with name, time and a note) and the stage they belong to.
MANUAL = {"received": "intake", "contacted": "design", "requirements": "contractor", "video_received": "contractor",
          "checked": "review", "confirmed": "delivery"}
SYSTEM_STAGES = {"certificate"}   # done by the system; a manager steps in if needed
MANAGER_STAGES = {"close"}        # the manager closes the project
DEFAULT_START = "2026-11-01"
LATE_DAYS = 2                     # a task untouched for longer than this shows as late on the manager board
APPROVED = {S.customer_approved, S.approved_for_contractor, S.sent_to_contractor}
SENT = {S.awaiting_customer} | APPROVED
MANAGERS = {Role.super_admin, Role.operations_manager}


# ---------------------------------------------------------------- settings
def settings(db: Session) -> dict:
    s = get_setting(db, "team_flow") or {}
    return {"start_date": s.get("start_date") or DEFAULT_START}


def save_settings(db: Session, start_date: date, actor: User) -> dict:
    before = settings(db)
    set_setting(db, "team_flow", {"start_date": start_date.isoformat()}, actor.id)
    audit(db, "team.settings", "setting", "team_flow", actor=actor, before=before, after=settings(db))
    return settings(db)


def owners(db: Session) -> dict[str, int | None]:
    raw = get_setting(db, "team_owners") or {}
    return {s: (int(raw[s]) if raw.get(s) else None) for s in STAGES if s not in SYSTEM_STAGES}


def save_owners(db: Session, new: dict[str, int | None], actor: User) -> dict:
    before = owners(db)
    out = dict(before)
    for stage, uid in new.items():
        if stage not in out:
            raise HTTPException(422, f"Unknown stage: {stage}")
        if uid is not None:
            u = db.get(User, uid)
            if not u or not u.is_active or u.role not in (Role.super_admin, Role.operations_manager, Role.staff):
                raise HTTPException(422, "Choose an active employee or manager")
        out[stage] = uid
    set_setting(db, "team_owners", out, actor.id)
    audit(db, "team.owners", "setting", "team_owners", actor=actor, before=before, after=out)
    return out


def _users(db: Session) -> dict[int, User]:
    return {u.id: u for u in db.scalars(select(User).where(User.role.in_([Role.super_admin, Role.operations_manager, Role.staff])))}


def people(db: Session) -> list[dict]:
    return [{"id": u.id, "name": u.full_name, "role": u.role.value}
            for u in sorted(_users(db).values(), key=lambda x: x.full_name) if u.is_active]


def my_stages(db: Session, user: User) -> list[str]:
    return [s for s, uid in owners(db).items() if uid == user.id]


# ---------------------------------------------------------------- reading one order
def _phone_ok(p: Project) -> bool:
    return p.customer_phone_status == "valid" and bool(p.customer_phone_e164)


def steps_of(p: Project, pl: Plaque | None, has_file: bool, fv: FinalVideo | None, manual: dict[str, TeamStep],
             cert_saved: bool, cert_sent: bool) -> dict:
    st = pl.status if pl else None
    vs = fv.status if fv else V.not_uploaded
    sent = bool(pl and (pl.sent_to_customer_at or st in SENT))
    delivered = p.delivery_status == DeliveryStatus.delivered
    done = {
        "received": "received" in manual,
        "country": bool((p.country or "").strip()),
        "contractor": p.contractor_id is not None,
        "contacted": "contacted" in manual or sent,
        "designed": has_file or st in APPROVED,
        "sent": sent,
        "approved": st in APPROVED,
        "plaque_sent": st == S.sent_to_contractor,
        "requirements": "requirements" in manual,
        "video_received": "video_received" in manual or vs != V.not_uploaded,
        "checked": "checked" in manual,
        "video": vs != V.not_uploaded,
        "ready": vs in (V.ready_for_delivery, V.sent_to_customer),
        "certificate": cert_saved,
        "sent_customer": vs == V.sent_to_customer or cert_sent,
        "confirmed": "confirmed" in manual,
        "closed": delivered,
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


def _days(since: datetime | None) -> int | None:
    if not since:
        return None
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return max(0, (utcnow() - since).days)


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
    certs = {(pid, et) for pid, et in db.execute(select(ProjectEvent.project_id, ProjectEvent.event_type).where(
        ProjectEvent.project_id.in_(ids), ProjectEvent.event_type.in_(["certificate_saved", "certificate_sent"])).distinct())}
    last = dict(db.execute(select(ProjectEvent.project_id, func.max(ProjectEvent.created_at))
                           .where(ProjectEvent.project_id.in_(ids)).group_by(ProjectEvent.project_id)).all())
    assigned = {(a.project_id, a.stage): a for a in db.scalars(select(TeamAssignment).where(TeamAssignment.project_id.in_(ids)))}
    own, users = owners(db), _users(db)
    out = []
    for p in projects:
        pl = plaques.get(p.id)
        fv = videos.get(p.id)
        steps = steps_of(p, pl, bool(pl and pl.current_version_id in with_file), fv, manual.get(p.id, {}),
                         (p.id, "certificate_saved") in certs, (p.id, "certificate_sent") in certs)
        stage = stage_of(steps)
        nxt = next((k for k in STEPS[stage] if not steps[k]["done"]), None) if stage else None
        a = assigned.get((p.id, stage)) if stage else None
        owner_id = a.user_id if a else own.get(stage) if stage else None
        owner = users.get(owner_id) if owner_id else None
        since = last.get(p.id) or p.updated_at
        days = _days(since)
        missing = list(pl.missing or []) if pl else []
        if pl and stage in ("design", "approval"):
            from app.services.plaque_flow import compute_missing
            missing = compute_missing(db, pl, p)
        out.append({
            "well_id": p.well_id, "order_date": p.order_date.isoformat() if p.order_date else None,
            "customer_name": p.customer_name, "dedication": p.dedication,
            "customer_phone": p.customer_phone, "customer_phone_e164": p.customer_phone_e164,
            "customer_phone_status": p.customer_phone_status, "phone_ok": _phone_ok(p),
            "shopify_order": p.shopify_order, "sales_source": p.sales_source,
            "country": p.country, "contractor_id": p.contractor_id,
            "contractor_code": p.contractor.code if p.contractor else None,
            "contractor_name": p.contractor.name if p.contractor else None,
            "contractor_phone": p.contractor.phone if p.contractor else None,
            "well_type": p.well_type, "construction_status": p.construction_status.value,
            "plaque_id": pl.id if pl else None, "plaque_status": pl.status.value if pl else None,
            "plaque_missing": missing, "video_status": (fv.status if fv else V.not_uploaded).value,
            "stage": stage, "stage_label": STAGE_AR.get(stage) if stage else None, "next_step": nxt,
            "waiting_customer": stage == "approval" and bool(pl and pl.status == S.awaiting_customer),
            "owner": {"id": owner.id, "name": owner.full_name} if owner else None,
            "owner_kind": "system" if stage in SYSTEM_STAGES else "manager" if stage in MANAGER_STAGES and not owner else "person",
            "reassigned": bool(a), "since": since.isoformat() if since else None, "days": days,
            "late": days is not None and days > LATE_DAYS, "steps": steps,
        })
    return out


def _active_query(db: Session):
    start = date.fromisoformat(settings(db)["start_date"])
    return (select(Project).where(
        Project.merged_into_id.is_(None),
        Project.construction_status != ConstructionStatus.cancelled,
        Project.delivery_status != DeliveryStatus.delivered,
        or_(Project.order_date >= start, Project.order_date.is_(None) & (Project.created_at >= start)),
    ).order_by(Project.order_date.asc().nullslast(), Project.well_id.asc()))


def all_cards(db: Session) -> list[dict]:
    return [c for c in _load(db, list(db.scalars(_active_query(db)))) if c["stage"]]


def tasks(db: Session, user: User, view: str = "mine", limit: int = 500) -> list[dict]:
    """view: mine (orders whose current stage is mine), all, or one stage key."""
    cards = all_cards(db)
    if view == "mine":
        cards = [c for c in cards if (c["owner"] and c["owner"]["id"] == user.id)
                 or (user.role in MANAGERS and c["owner_kind"] in ("manager", "system") and not c["owner"])]
    elif view in STAGES:
        cards = [c for c in cards if c["stage"] == view]
    return cards[:limit]


def counts(db: Session, user: User) -> dict:
    cards = all_cards(db)
    out: dict = {s: 0 for s in STAGES}
    for c in cards:
        out[c["stage"]] += 1
    mine = [c for c in cards if (c["owner"] and c["owner"]["id"] == user.id)
            or (user.role in MANAGERS and c["owner_kind"] in ("manager", "system") and not c["owner"])]
    out["mine"] = len(mine)
    out["late"] = sum(c["late"] for c in cards)
    out["mine_late"] = sum(c["late"] for c in mine)
    return out


def card_for(db: Session, p: Project) -> dict:
    return _load(db, [p])[0]


# ---------------------------------------------------------------- who may act
def check_can_act(db: Session, p: Project, stage: str, actor: User) -> None:
    """Each stage has one responsible person; the manager can always step in."""
    if actor.role in MANAGERS:
        return
    if stage in MANAGER_STAGES or stage in SYSTEM_STAGES:
        raise HTTPException(403, "هذه المرحلة للإدارة فقط")
    a = db.scalar(select(TeamAssignment).where(TeamAssignment.project_id == p.id, TeamAssignment.stage == stage))
    owner_id = a.user_id if a else owners(db).get(stage)
    if owner_id != actor.id:
        who = db.get(User, owner_id).full_name if owner_id and db.get(User, owner_id) else "غير محدد"
        raise HTTPException(403, f"هذه المهمة («{STAGE_AR[stage]}») مسؤولية {who}. تستطيع المديرة نقلها إليك.")


# ---------------------------------------------------------------- actions
def set_step(db: Session, p: Project, step: str, done: bool, actor: User, note: str | None = None) -> dict:
    if step not in MANUAL:
        raise HTTPException(422, "This step is completed from its own page, not ticked by hand")
    check_can_act(db, p, MANUAL[step], actor)
    row = db.scalar(select(TeamStep).where(TeamStep.project_id == p.id, TeamStep.step == step).with_for_update())
    note = (note or "").strip() or None
    if done:
        if step == "checked" and not _phone_ok(p):
            raise HTTPException(409, "رقم هاتف العميل غير صحيح أو بلا رمز الدولة. صحّحه أولاً ثم أكّد المراجعة.")
        if step in ("requirements", "confirmed") and not note:
            raise HTTPException(422, "اكتب ملاحظة قصيرة للتوثيق (مثلاً: كيف أُرسلت أو كيف تأكّد التسليم)")
        if row:
            return card_for(db, p)
        db.add(TeamStep(project_id=p.id, step=step, done_at=utcnow(), done_by_id=actor.id, done_by=actor.full_name, note=note))
    else:
        if not row:
            return card_for(db, p)
        db.delete(row)
    _log(db, p, actor, "team_step", ("✓ " if done else "↺ ") + STEP_AR[step] + (f" · {note}" if note else ""),
         {"step": step, "done": done, "note": note})
    db.flush()
    return card_for(db, p)


def send_to_contractor(db: Session, p: Project, actor: User, note: str | None = None) -> dict:
    """غازي records that the approved plaque was sent to the order's contractor."""
    check_can_act(db, p, "contractor", actor)
    from app.services import plaque_flow
    pl = plaque_flow.get_plaque(db, p, for_update=True)
    if not pl or pl.status != S.approved_for_contractor:
        raise HTTPException(409, "اللوحة غير معتمدة بعد، أو سبق تسجيل إرسالها للمقاول")
    if not p.contractor_id:
        raise HTTPException(409, "اختر المقاول أولاً")
    plaque_flow.send_to_contractor(db, pl, contractor_id=p.contractor_id, country=p.country, on=None, actor=actor, note=note)
    db.flush()
    return card_for(db, p)


def close_project(db: Session, p: Project, actor: User, on: date | None = None, note: str | None = None) -> dict:
    """The manager records the delivery date and closes the project's cycle."""
    if actor.role not in MANAGERS:
        raise HTTPException(403, "إغلاق المشروع للإدارة فقط")
    c = card_for(db, p)
    if c["stage"] != "close":
        raise HTTPException(409, f"لم تكتمل المراحل السابقة بعد (المرحلة الحالية: {c['stage_label']})")
    from app.services.projects import update_project
    update_project(db, p, {"delivery_status": DeliveryStatus.delivered, "delivery_date": on or date.today()},
                   actor=actor, allow_delivery_fields=True)
    _log(db, p, actor, "team_closed", "✓ إغلاق المشروع" + (f" · {note}" if note else ""), {"on": (on or date.today()).isoformat(), "note": note})
    db.flush()
    return card_for(db, p)


def reassign(db: Session, p: Project, stage: str, user_id: int | None, actor: User, note: str | None = None) -> dict:
    """The manager moves one order's stage to another person (None = back to the stage's usual owner)."""
    if actor.role not in MANAGERS:
        raise HTTPException(403, "نقل المهمة للإدارة فقط")
    if stage not in STAGES or stage in SYSTEM_STAGES:
        raise HTTPException(422, "Unknown stage")
    row = db.scalar(select(TeamAssignment).where(TeamAssignment.project_id == p.id, TeamAssignment.stage == stage))
    if user_id is None:
        if row:
            db.delete(row)
        who = "المسؤول الأساسي"
    else:
        u = db.get(User, user_id)
        if not u or not u.is_active or u.role not in (Role.super_admin, Role.operations_manager, Role.staff):
            raise HTTPException(422, "Choose an active employee or manager")
        if row:
            row.user_id, row.assigned_by, row.assigned_at, row.note = u.id, actor.full_name, utcnow(), note
        else:
            db.add(TeamAssignment(project_id=p.id, stage=stage, user_id=u.id, assigned_by=actor.full_name, note=note))
        who = u.full_name
    _log(db, p, actor, "team_reassigned", f"نقل مهمة «{STAGE_AR[stage]}» إلى {who}" + (f" · {note}" if note else ""),
         {"stage": stage, "user_id": user_id, "note": note})
    db.flush()
    return card_for(db, p)


def _log(db: Session, p: Project, actor: User, event: str, summary: str, payload: dict) -> None:
    from app.services.projects import add_event
    add_event(db, p, event, source="dashboard", actor=actor, summary=summary[:500], payload=payload)
    audit(db, f"team.{event.removeprefix('team_')}", "project", p.id, actor=actor, after={"well_id": p.well_id, **payload})

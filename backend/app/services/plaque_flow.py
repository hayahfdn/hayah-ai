"""Plaque workflow for every order (well or sacrifice).

New order -> automatic draft (version 1, never changed) -> employee completes anything missing
-> sent to the customer -> customer approves or asks for changes -> approved and ready for the
contractor -> sent to the contractor (contractor, country and date recorded).

Rules (Hayah, 19 Nov 2026):
- Nothing is guessed. Missing name, gender/living-deceased, well type, animal or country keep the
  plaque in "draft" with the missing items listed.
- Every save is a new version; earlier versions stay and can be reopened.
- A plaque leaves the approved list only when its sending to a contractor is recorded.
- Every status change is written to the order's timeline (wells) and to the audit log.
- No cost or price is ever returned from here, so employees can use all of it.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Contractor, MediaAsset, Plaque, PlaqueStatus as S, PlaqueVersion, Project, Sacrifice, User, utcnow,
)
from app.services import prayers
from app.services.audit import audit

AUTO_SOURCES = {"shopify", "dashboard", "whatsapp"}  # not workbook imports, seeds or the AI box
OPEN = [S.draft, S.ready_for_review, S.awaiting_customer, S.needs_changes, S.customer_approved]
LABELS_AR = {S.draft: "قيد الإنشاء", S.ready_for_review: "جاهزة للمراجعة", S.awaiting_customer: "بانتظار موافقة العميل",
             S.needs_changes: "تحتاج إلى تعديل", S.customer_approved: "تم اعتمادها من العميل",
             S.approved_for_contractor: "معتمدة وجاهزة للإرسال للمقاول", S.sent_to_contractor: "تم إرسال اللوحة للمقاول"}
# Where an employee may move a plaque by hand. Sending to the contractor has its own action.
MOVES = {
    S.draft: {S.ready_for_review},
    S.ready_for_review: {S.awaiting_customer, S.customer_approved, S.needs_changes},
    S.awaiting_customer: {S.customer_approved, S.needs_changes},
    S.needs_changes: {S.awaiting_customer, S.ready_for_review, S.customer_approved},
    S.customer_approved: {S.needs_changes},
    S.approved_for_contractor: {S.needs_changes},
    S.sent_to_contractor: {S.needs_changes},
}


# ---------------------------------------------------------------- order data
def record_of(db: Session, plaque: Plaque):
    return db.get(Project, plaque.project_id) if plaque.project_id else db.get(Sacrifice, plaque.sacrifice_id)


def order_name(rec) -> str:
    if isinstance(rec, Project):
        return (rec.dedication or rec.customer_name or "").strip()
    return (rec.dedication or rec.donor_name or "").strip()


# The name printed on the plaque (Hayah, 21 Nov 2026): name only, kinship or job words kept, but no
# "صدقة جارية عن" / "لروح" in front and no prayers like "رحمهم الله". Same rules as plaqueName in
# frontend/src/plaque/render.ts. The prayer kind is still read from the full text.
_NAME_LEAD = re.compile(r"^[\s:،,.\-]*(?:(?:صدق[ةه](?:\s+جاري[ةه])?|وقف|إهداء|اهداء|هدية|ثواب)(?:\s*[:،,]\s*|\s+|$))?"
                        r"(?:(?:عن|على|إلى|الى|لـ)(?:\s*[:،,]\s*|\s+))?(?:(?:لروح|روح|لأرواح|لارواح|أرواح|ارواح)(?:\s*[:،,]\s*|\s+))?")
_NAME_PRAYER = re.compile(r"\s*\(?\s*(?:(?:رحم|يرحم|غفر|تقبل|حفظ|يحفظ)(?:ه|ها|هم|هما|هن)?\s+الله(?:\s+(?:له|لها|لهم|لهما|منه|منها|منهم|منهما))?"
                          r"|رحم[ةه]\s+الله\s+(?:عليه|عليها|عليهم|عليهما))(?:\s+(?:تعالى|جميعا|جميعاً))?(?:\s+و(?:غفر|رحم)\s*(?:له|لها|لهم|لهما))?\s*\)?")


def plaque_name(text: str | None) -> str:
    out = []
    for line in (text or "").split("\n"):
        line = _NAME_LEAD.sub("", _NAME_PRAYER.sub(" ", line), count=1)
        line = re.sub(r"^[\s:،,.\-]+|[\s:،,.\-]+$", "", re.sub(r"\s+", " ", line))
        if line:
            out.append(line)
    return "\n".join(out)


def _country(db: Session, rec) -> str | None:
    c = db.get(Contractor, rec.contractor_id) if rec.contractor_id else None
    if c and c.country:
        return c.country
    return getattr(rec, "country", None)


def compute_missing(db: Session, plaque: Plaque, rec, name: str | None = None) -> list[str]:
    name = order_name(rec) if name is None else name.strip()
    out = []
    if not name:
        out.append("name")
    if not plaque.anonymous and (not plaque.honoree_gender or not plaque.honoree_state):
        out.append("gender_state")
    if isinstance(rec, Project) and not rec.well_type:
        out.append("well_type")
    if isinstance(rec, Sacrifice) and not rec.animal_type:
        out.append("animal")
    if not _country(db, rec) and not design_flag(db, plaque):
        out.append("country")
    return out


def design_flag(db: Session, plaque: Plaque) -> str | None:
    """The flag chosen on the plaque in the designer. The flag is the country on the plaque, so a
    plaque with a flag is not missing its country, even before a contractor is chosen (the country
    only follows the contractor, and the contractor is chosen after the customer approves)."""
    v = db.get(PlaqueVersion, plaque.current_version_id) if plaque.current_version_id else None
    flag = ((v.design or {}).get("flag") if v else None) or None
    return flag if isinstance(flag, str) and flag.strip() else None


# ---------------------------------------------------------------- creating
def get_plaque(db: Session, rec, for_update: bool = False) -> Plaque | None:
    col = Plaque.project_id if isinstance(rec, Project) else Plaque.sacrifice_id
    q = select(Plaque).where(col == rec.id)
    return db.scalar(q.with_for_update() if for_update else q)


def create_draft(db: Session, rec, *, actor: User | None = None, source: str = "auto") -> Plaque:
    """The automatic draft for an order. Returns the existing plaque if there is one."""
    existing = get_plaque(db, rec)
    if existing:
        return existing
    well = isinstance(rec, Project)
    name = order_name(rec)
    c = prayers.classify(name)
    pl = Plaque(kind="well" if well else "sacrifice", project_id=rec.id if well else None,
                sacrifice_id=None if well else rec.id, anonymous=c["kind"] in ("anon_m", "anon_f"),
                honoree_gender=c["gender"] if c["sure"] else None, honoree_state=c["state"] if c["sure"] else None,
                dua_kind=c["kind"])
    db.add(pl)
    db.flush()
    pl.missing = compute_missing(db, pl, rec)
    pl.status = S.draft if pl.missing else S.ready_for_review
    shown = plaque_name(name) or plaque_name(rec.customer_name if well else rec.donor_name) or name
    design = {"template": "hayah_square" if well else "sacrifice_portrait", "auto": True, "name": shown,
              "dua_kind": c["kind"], "dua_sure": c["sure"]}
    v = PlaqueVersion(plaque_id=pl.id, version=1, design=design, source="auto",
                      created_by_id=actor.id if actor else None, actor_label=actor.full_name if actor else "system")
    db.add(v)
    db.flush()
    pl.current_version_id = v.id
    _log(db, pl, rec, "plaque_draft_created", actor,
         f"Automatic plaque draft · {LABELS_AR[pl.status]}" + (f" · missing: {', '.join(pl.missing)}" if pl.missing else ""),
         {"missing": pl.missing, "dua_kind": c["kind"], "sure": c["sure"], "source": source})
    return pl


def maybe_create_for_new_order(db: Session, rec, *, source: str, is_sample: bool = False, actor: User | None = None) -> None:
    if source in AUTO_SOURCES and not is_sample:
        create_draft(db, rec, actor=actor, source=source)


# ---------------------------------------------------------------- versions
def add_version(db: Session, rec, *, design: dict, actor: User | None, media_id: int | None = None,
                drive_file_id: str | None = None, filename: str | None = None, event_id: str | None = None) -> PlaqueVersion:
    pl = get_plaque(db, rec, for_update=True) or create_draft(db, rec, actor=actor, source="dashboard")
    n = (db.scalar(select(func.max(PlaqueVersion.version)).where(PlaqueVersion.plaque_id == pl.id)) or 0) + 1
    v = PlaqueVersion(plaque_id=pl.id, version=n, design={k: v for k, v in design.items() if k != "auto"},
                      media_id=media_id, drive_file_id=drive_file_id, filename=filename, source="dashboard",
                      event_id=event_id, created_by_id=actor.id if actor else None,
                      actor_label=actor.full_name if actor else None)
    db.add(v)
    db.flush()
    pl.current_version_id = v.id
    # The employee picked the prayer in the designer: that confirms gender and living/deceased.
    kind, sure = design.get("dua_kind"), design.get("dua_sure")
    if not kind and isinstance(design.get("name"), str):  # older designs: read the name on the plaque
        c = prayers.classify(design["name"])
        kind, sure = c["kind"], c["sure"]
    if kind in prayers.FACTS and sure is not False:
        g, st = prayers.FACTS[kind]
        pl.dua_kind = kind
        pl.anonymous = kind in ("anon_m", "anon_f")
        if g and st:
            pl.honoree_gender, pl.honoree_state = g, st
    pl.missing = compute_missing(db, pl, rec, design.get("name") if isinstance(design.get("name"), str) else None)
    if pl.status == S.draft and not pl.missing:
        pl.status = S.ready_for_review
    pl.updated_at = utcnow()
    _log(db, pl, rec, "plaque_version_saved", actor, f"Plaque version {n} saved", {"version": n, "media_id": media_id})
    return v


# ---------------------------------------------------------------- status
def _has_file(db: Session, pl: Plaque) -> bool:
    v = db.get(PlaqueVersion, pl.current_version_id) if pl.current_version_id else None
    return bool(v and (v.media_id or v.drive_file_id))


def set_status(db: Session, pl: Plaque, to: S, actor: User, note: str | None = None) -> Plaque:
    rec = record_of(db, pl)
    refresh_missing(db, pl, rec, promote=False)
    if to not in MOVES.get(pl.status, set()):
        raise HTTPException(409, f"A plaque that is '{LABELS_AR[pl.status]}' cannot move to '{LABELS_AR[to]}'")
    if to in (S.ready_for_review, S.awaiting_customer, S.customer_approved) and pl.missing:
        raise HTTPException(409, "Complete the missing plaque information first: " + ", ".join(pl.missing))
    if to in (S.awaiting_customer, S.customer_approved) and not _has_file(db, pl):
        raise HTTPException(409, "Open the plaque in the designer and save it first, so there is a file to send.")
    before = pl.status
    pl.status = to
    now = utcnow()
    if to == S.awaiting_customer:
        pl.sent_to_customer_at = now
    if to in (S.customer_approved, S.needs_changes) and before in (S.awaiting_customer, S.ready_for_review, S.needs_changes):
        pl.customer_decision_at, pl.customer_decision_by, pl.customer_note = now, actor.full_name, note
    pl.updated_at = now
    _log(db, pl, rec, "plaque_status", actor, f"{LABELS_AR[before]} → {LABELS_AR[to]}" + (f" · {note}" if note else ""),
         {"from": before.value, "to": to.value, "note": note})
    if to == S.customer_approved:
        _approve_current(db, pl, rec, actor)
    if to == S.needs_changes and isinstance(rec, Project) and rec.plaque_status == "approved":
        rec.plaque_status = "draft"  # the order no longer has a final plaque until it is approved again
    return pl


def _approve_current(db: Session, pl: Plaque, rec, actor: User | None) -> None:
    """Customer approved: the current version becomes the approved plaque and goes straight to
    the approved plaques section for the contractor."""
    pl.approved_version_id = pl.current_version_id
    pl.status = S.approved_for_contractor
    v = db.get(PlaqueVersion, pl.current_version_id)
    if isinstance(rec, Project) and v and v.media_id:
        rec.plaque_status, rec.plaque_media_id = "approved", v.media_id
        rec.plaque_approved_at, rec.plaque_approved_by = utcnow(), actor.full_name if actor else None
    _log(db, pl, rec, "plaque_status", actor, f"{LABELS_AR[S.customer_approved]} → {LABELS_AR[S.approved_for_contractor]}",
         {"from": S.customer_approved.value, "to": S.approved_for_contractor.value, "version_id": pl.approved_version_id})


def approve_from_designer(db: Session, rec, version: PlaqueVersion, actor: User) -> Plaque:
    """The designer's 'customer approved this plaque' button (and the older approve button)."""
    pl = get_plaque(db, rec, for_update=True) or create_draft(db, rec, actor=actor, source="dashboard")
    pl.current_version_id = version.id
    if pl.status == S.sent_to_contractor:
        raise HTTPException(409, "This plaque was already sent to the contractor. Mark it 'needs changes' first.")
    if pl.missing:
        raise HTTPException(409, "Complete the missing plaque information first: " + ", ".join(pl.missing))
    before = pl.status
    pl.status, pl.customer_decision_at, pl.customer_decision_by = S.customer_approved, utcnow(), actor.full_name
    _log(db, pl, rec, "plaque_status", actor, f"{LABELS_AR[before]} → {LABELS_AR[S.customer_approved]}",
         {"from": before.value, "to": S.customer_approved.value})
    _approve_current(db, pl, rec, actor)
    return pl


def send_to_contractor(db: Session, pl: Plaque, *, contractor_id: int, country: str | None, on: date | None,
                       actor: User, note: str | None = None) -> Plaque:
    if pl.status != S.approved_for_contractor:
        raise HTTPException(409, "Only an approved plaque can be recorded as sent to the contractor")
    c = db.get(Contractor, contractor_id)
    if not c:
        raise HTTPException(422, "Unknown contractor")
    country = (country or c.country or "").strip()
    if not country:
        raise HTTPException(422, "Choose the contractor's country")
    rec = record_of(db, pl)
    pl.contractor_id, pl.contractor_country = c.id, country[:80]
    pl.sent_to_contractor_on, pl.sent_to_contractor_by = on or date.today(), actor.full_name
    pl.status, pl.updated_at = S.sent_to_contractor, utcnow()
    if rec.contractor_id is None:  # the order had no contractor yet: it gets this one
        if isinstance(rec, Project):
            from app.services.projects import update_project
            update_project(db, rec, {"contractor_id": c.id}, actor=actor)
        else:
            from app.services.finance import update_sacrifice
            update_sacrifice(db, rec, {"contractor_id": c.id}, actor=actor)
    _log(db, pl, rec, "plaque_sent_to_contractor", actor,
         f"{LABELS_AR[S.sent_to_contractor]}: {c.name} ({c.code}) · {country} · {pl.sent_to_contractor_on.isoformat()}"
         + (f" · {note}" if note else ""),
         {"contractor_id": c.id, "country": country, "on": pl.sent_to_contractor_on.isoformat(), "note": note})
    return pl


def _log(db: Session, pl: Plaque, rec, event: str, actor: User | None, summary: str, payload: dict) -> None:
    if isinstance(rec, Project):
        from app.services.projects import add_event
        add_event(db, rec, event, source="dashboard" if actor else "system", actor=actor, summary=summary[:500],
                  payload={"plaque_id": pl.id, **payload})
    audit(db, f"plaque.{event.removeprefix('plaque_')}", "plaque", pl.id, actor=actor,
          actor_label=None if actor else "system",
          after={"order": ("well " if isinstance(rec, Project) else "sacrifice ") + str(number(rec)), "status": pl.status.value,
                 "summary": summary, **payload})
    db.flush()


# ---------------------------------------------------------------- reading
def number(rec) -> int:
    return rec.well_id if isinstance(rec, Project) else rec.sacrifice_no


def refresh_missing(db: Session, pl: Plaque, rec, promote: bool = True) -> None:
    """The order may have changed since the plaque was saved (contractor chosen, well type or name
    filled in): read what is missing again, so the plaque never stays blocked by old information."""
    cur = db.get(PlaqueVersion, pl.current_version_id) if pl.current_version_id else None
    name = (cur.design or {}).get("name") if cur else None
    now = compute_missing(db, pl, rec, name if isinstance(name, str) else None)
    if now != (pl.missing or []):
        pl.missing = now
        if promote and pl.status == S.draft and not now:
            pl.status = S.ready_for_review


def row(db: Session, pl: Plaque, rec=None, versions: bool = False) -> dict:
    rec = rec or record_of(db, pl)
    refresh_missing(db, pl, rec)
    cur = db.get(PlaqueVersion, pl.current_version_id) if pl.current_version_id else None
    appr = db.get(PlaqueVersion, pl.approved_version_id) if pl.approved_version_id else None
    con = db.get(Contractor, pl.contractor_id) if pl.contractor_id else None
    show = appr if pl.status in (S.approved_for_contractor, S.sent_to_contractor) and appr else cur
    out = {
        "id": pl.id, "kind": pl.kind, "number": number(rec), "status": pl.status.value, "status_ar": LABELS_AR[pl.status],
        "missing": pl.missing or [], "name": order_name(rec), "customer_name": rec.customer_name if isinstance(rec, Project) else rec.donor_name,
        "customer_phone": rec.customer_phone, "customer_phone_e164": rec.customer_phone_e164,
        "customer_phone_status": rec.customer_phone_status,
        "order_date": rec.order_date.isoformat() if rec.order_date else None, "shopify_order": rec.shopify_order,
        "type": rec.well_type if isinstance(rec, Project) else rec.animal_type,
        "order_country": _country(db, rec),
        "order_contractor_id": rec.contractor_id,
        "honoree_gender": pl.honoree_gender, "honoree_state": pl.honoree_state, "anonymous": pl.anonymous,
        "dua_kind": pl.dua_kind,
        "version": cur.version if cur else None, "file_version_id": show.id if show and (show.media_id or show.drive_file_id) else None,
        "design": (show.design if show else {}) or {},
        "sent_to_customer_at": pl.sent_to_customer_at, "customer_decision_at": pl.customer_decision_at,
        "customer_decision_by": pl.customer_decision_by, "customer_note": pl.customer_note,
        "contractor": {"id": con.id, "code": con.code, "name": con.name, "color": con.color} if con else None,
        "contractor_country": pl.contractor_country,
        "sent_to_contractor_on": pl.sent_to_contractor_on.isoformat() if pl.sent_to_contractor_on else None,
        "sent_to_contractor_by": pl.sent_to_contractor_by, "updated_at": pl.updated_at, "created_at": pl.created_at,
    }
    from app.services import plaque_whatsapp
    out["whatsapp"] = plaque_whatsapp.info(db, pl, rec)
    if versions:
        vs = db.scalars(select(PlaqueVersion).where(PlaqueVersion.plaque_id == pl.id).order_by(PlaqueVersion.version.desc()))
        out["versions"] = [{"id": v.id, "version": v.version, "source": v.source, "actor_label": v.actor_label,
                            "created_at": v.created_at, "has_file": bool(v.media_id or v.drive_file_id),
                            "approved": v.id == pl.approved_version_id, "design": v.design} for v in vs]
    return out


def list_plaques(db: Session, statuses: list[S], kind: str | None = None, q: str | None = None, limit: int = 300) -> list[dict]:
    stmt = select(Plaque).where(Plaque.status.in_(statuses))
    if kind in ("well", "sacrifice"):
        stmt = stmt.where(Plaque.kind == kind)
    rows = list(db.scalars(stmt.order_by(Plaque.updated_at.desc()).limit(limit)))
    out = [row(db, p) for p in rows]
    if q:
        ql = q.strip().lower()
        out = [r for r in out if ql in str(r["number"]) or ql in (r["name"] or "").lower()
               or ql in (r["customer_name"] or "").lower() or ql in (r["customer_phone_e164"] or "")]
    return out


def counts(db: Session, for_manager: bool = True) -> dict:
    by = dict(db.execute(select(Plaque.status, func.count()).group_by(Plaque.status)).all())
    g = lambda *ss: sum(by.get(s, 0) for s in ss)  # noqa: E731
    return {"needs_confirmation": g(*OPEN), "draft": g(S.draft), "ready_for_review": g(S.ready_for_review),
            "awaiting_customer": g(S.awaiting_customer), "needs_changes": g(S.needs_changes),
            "ready_for_contractor": g(S.approved_for_contractor) if for_manager else 0,
            "sent_to_contractor": g(S.sent_to_contractor)}


def version_file(db: Session, v: PlaqueVersion) -> tuple[bytes, str, str]:
    from app.integrations.drive import get_drive_client
    fid, mime, name = v.drive_file_id, "image/png", v.filename or f"plaque-v{v.version}.png"
    if v.media_id:
        a = db.get(MediaAsset, v.media_id)
        fid, mime, name = a.drive_file_id, a.mime_type, a.filename
    if not fid:
        raise HTTPException(404, "This version has no file yet (open it in the designer and save)")
    try:
        return get_drive_client().download(fid), mime, name
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Could not read the plaque file: {e}")


def zip_files(db: Session, ids: list[int]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for pid in ids[:200]:
            pl = db.get(Plaque, pid)
            if not pl:
                continue
            vid = pl.approved_version_id or pl.current_version_id
            v = db.get(PlaqueVersion, vid) if vid else None
            if not v or not (v.media_id or v.drive_file_id):
                continue
            data, _, name = version_file(db, v)
            rec = record_of(db, pl)
            z.writestr(f"{'well' if pl.kind == 'well' else 'sacrifice'}-{number(rec)}_{name}", data)
    return buf.getvalue()

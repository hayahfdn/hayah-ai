"""«صيغة عقد»: the official contract (and invoice) for a well or a sacrifice (Hayah, 22 Nov 2026).

The contract is drawn in the browser like the plaques and the certificate. The server gives the
order's own facts (project number, type, owner, add-ons, amount received, dates), HAYAH's phone
from Settings, and keeps the edited design in the audit log (action contract.saved), so no new
table is needed.

Invoice numbers are gap-free and given once, on the first save of a contract (Counter "invoice"):
HF-<year>-0001, HF-<year>-0002 ... The number never changes afterwards, even if the order is
renumbered, because the saved contract is linked to the record's own id.

The amount on the contract is the selling price (what the customer paid). Cost, profit and any
finance figure are never part of it, so employees can prepare contracts (Hayah's visibility rule).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Counter, Project, Sacrifice, User
from app.services.audit import audit, jsonable
from app.services.settings_store import get_setting, set_setting

SAVED = "contract.saved"
SETTING = "contract"
DEFAULT_SETTINGS = {"hayah_phone": "+447350295849",  # Hayah, 22 Nov 2026
                    "delivery_days": 90, "invoice_prefix": "HF"}


def settings(db: Session) -> dict:
    s = {**DEFAULT_SETTINGS, **get_setting(db, SETTING)}
    s["delivery_days"] = int(s.get("delivery_days") or 90)
    return s


def save_settings(db: Session, values: dict, actor: User) -> dict:
    before = settings(db)
    after = {**before, **{k: v for k, v in values.items() if k in DEFAULT_SETTINGS}}
    set_setting(db, SETTING, after, actor.id)
    audit(db, "settings.contract", "settings", SETTING, actor=actor, before=before, after=after)
    return after


def _entity(kind: str) -> str:
    return "contract_well" if kind == "well" else "contract_sacrifice"


def _last(db: Session, kind: str, rec_id: int) -> AuditLog | None:
    return db.scalar(select(AuditLog).where(AuditLog.action == SAVED, AuditLog.entity_type == _entity(kind),
                                            AuditLog.entity_id == str(rec_id)).order_by(AuditLog.id.desc()).limit(1))


def next_invoice(db: Session, prefix: str, today: date | None = None) -> str:
    c = db.scalar(select(Counter).where(Counter.name == "invoice").with_for_update())
    if not c:
        c = Counter(name="invoice", value=0)
        db.add(c)
        db.flush()
    c.value += 1
    return f"{prefix or 'HF'}-{(today or date.today()).year}-{c.value:04d}"


def _expected(order: date | None, delivery: date | None, days: int) -> tuple[date, bool]:
    """Delivery date when the order has one; otherwise order date (or today) + the days in Settings."""
    if delivery:
        return delivery, False
    return (order or date.today()) + timedelta(days=days), True


def facts(db: Session, kind: str, rec: Project | Sacrifice) -> dict:
    days = settings(db)["delivery_days"]
    if kind == "well":
        p: Project = rec  # type: ignore[assignment]
        exp, guessed = _expected(p.order_date, p.delivery_date, days)
        return {
            "number": p.well_id, "well_type": p.well_type, "extras": p.extras, "owner": p.customer_name,
            "dedication": p.dedication, "amount": jsonable(p.sale_amount), "currency": p.currency or "USD",
            "country": (p.contractor.country if p.contractor else None) or p.country,
            "order_date": jsonable(p.order_date), "expected_delivery": exp.isoformat(), "delivery_guessed": guessed,
            "owner_phone": p.customer_phone_e164 or p.customer_phone,
        }
    s: Sacrifice = rec  # type: ignore[assignment]
    exp, guessed = _expected(s.order_date, s.delivery_date, days)
    return {
        "number": s.sacrifice_no, "animal_type": s.animal_type, "intention": s.intention, "extras": s.extras,
        "owner": s.donor_name, "dedication": s.dedication, "amount": jsonable(s.sale_price), "currency": s.currency or "USD",
        "country": s.contractor.country if s.contractor else None,
        "order_date": jsonable(s.order_date), "expected_delivery": exp.isoformat(), "delivery_guessed": guessed,
        "owner_phone": s.customer_phone_e164 or s.customer_phone,
    }


def data(db: Session, kind: str, rec: Project | Sacrifice) -> dict:
    last = _last(db, kind, rec.id)
    st = settings(db)
    after = (last.after or {}) if last else {}
    return {
        "kind": kind, "facts": facts(db, kind, rec), "hayah_phone": st["hayah_phone"],
        "invoice_no": after.get("invoice_no"), "design": after.get("design"),
        "issued_at": after.get("issued_at"), "saved_at": jsonable(last.at) if last else None,
        "saved_by": last.actor_label if last else None,
    }


def save(db: Session, kind: str, rec: Project | Sacrifice, design: dict, actor: User) -> None:
    """Saves the edited contract. The first save gives the invoice number and the issue date."""
    last = _last(db, kind, rec.id)
    prev = (last.after or {}) if last else {}
    invoice = prev.get("invoice_no") or next_invoice(db, settings(db)["invoice_prefix"])
    issued = prev.get("issued_at") or date.today().isoformat()
    audit(db, SAVED, _entity(kind), rec.id, actor=actor,
          after={"invoice_no": invoice, "issued_at": issued, "number": facts(db, kind, rec)["number"], "design": design})

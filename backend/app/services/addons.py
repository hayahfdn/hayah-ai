"""Add-ons (الإضافات) on wells and sacrifices (Hayah, 20 Nov 2026).

- Add-ons are their own field (the `extras` column), never mixed into the well type.
  They are stored as one text, items separated by ", " so the sheets and old data keep working.
  The lists offered on the forms are in Settings (`well_addons`, `sacrifice_addons`).
- A sheep (خروف) bought as an add-on of a well becomes its own sacrifice, automatically:
  selling price 99 USD, linked to the well (sacrifices.parent_project_id), donor/dedication/phone
  from the well, intention "صدقة". It shows on the sacrifices page and can be edited there.
  The sheep stays listed in the well's add-ons.
- Money is counted once: the 99 belongs to the sacrifice; the well's selling price is the well
  (and its other add-ons) only. Removing the sheep from the well never deletes the sacrifice
  (nothing is deleted automatically); the caller gets a warning to review it.
- Imports (workbook, sheets) never create sacrifices: their sheep, if any, were already typed
  in the sacrifices sheet. Shopify links its own sheep sacrifice (services/shopify.py).
"""
from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Project, Sacrifice, User
from app.services.settings_store import get_setting

SHEEP_NAMES = {"خروف", "خاروف", "sheep", "lamb"}
SHEEP_PRICE = Decimal("99.00")
DEFAULT_WELL_ADDONS = ["خزان", "سيراميك", "خروف"]
DEFAULT_SACRIFICE_ADDONS = ["إطعام"]
NO_AUTO_SOURCES = {"workbook_import", "import", "sheets", "shopify"}
_SPLIT = re.compile(r"\s*[,،;+]\s*")
_QTY = re.compile(r"^(.*?)\s*(?:[×x*]\s*(\d+)|\((\d+)\))$")


def split(text: str | None) -> list[str]:
    return [t.strip() for t in _SPLIT.split(text or "") if t.strip()]


def join(items: list[str]) -> str | None:
    seen, out = set(), []
    for i in items:
        i = (i or "").strip()
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return ", ".join(out)[:200] or None


def normalize(text: str | None) -> str | None:
    """'خزان، سيراميك + خروف' -> 'خزان, سيراميك, خروف' (same items, one separator)."""
    return join(split(text)) if text is not None else None


def _name_qty(token: str) -> tuple[str, int]:
    m = _QTY.match(token.strip())
    if m:
        return m.group(1).strip(), int(m.group(2) or m.group(3))
    return token.strip(), 1


def is_sheep(token: str) -> bool:
    name, _ = _name_qty(token)
    return name.lower() in SHEEP_NAMES


def sheep_count(text: str | None) -> int:
    return sum(_name_qty(t)[1] for t in split(text) if is_sheep(t))


def options(db: Session) -> dict:
    return {"well_addons": get_setting(db, "well_addons").get("values") or DEFAULT_WELL_ADDONS,
            "sacrifice_addons": get_setting(db, "sacrifice_addons").get("values") or DEFAULT_SACRIFICE_ADDONS}


def _next_sacrifice_no(db: Session) -> int:
    hi = db.scalar(select(func.max(Sacrifice.sacrifice_no)).where(Sacrifice.is_sample.is_(False))) or 0
    return hi + 1


def linked(db: Session, project: Project) -> list[Sacrifice]:
    return list(db.scalars(select(Sacrifice).where(Sacrifice.parent_project_id == project.id).order_by(Sacrifice.sacrifice_no)))


def sync_sheep(db: Session, project: Project, *, actor: User | None, source: str) -> dict:
    """Make sure every sheep in the well's add-ons has its own linked sacrifice.
    Returns {"created": [numbers], "extra": [numbers kept although the sheep was removed]}."""
    out = {"created": [], "extra": []}
    if source in NO_AUTO_SOURCES:
        return out
    from app.services import finance as fin
    from app.services import projects as psvc
    want, have = sheep_count(project.extras), linked(db, project)
    for _ in range(max(0, want - len(have))):
        data = {"sacrifice_no": _next_sacrifice_no(db), "order_date": project.order_date,
                "donor_name": project.customer_name, "customer_phone": project.customer_phone,
                "customer_phone_country": project.customer_phone_country, "animal_type": "خروف",
                "sale_price": SHEEP_PRICE, "currency": "USD", "payment_method": project.payment_method,
                "sales_source": project.sales_source, "source_group": project.source_group,
                "shopify_order": project.shopify_order, "intention": "صدقة", "dedication": project.dedication,
                "parent_project_id": project.id,
                "notes": f"خروف مضاف مع البئر {project.well_id} (إضافة) · Sheep add-on of well {project.well_id}"}
        s = fin.create_sacrifice(db, {k: v for k, v in data.items() if v is not None}, actor=actor,
                                 is_sample=project.is_sample, source=source)
        out["created"].append(s.sacrifice_no)
    if out["created"]:
        psvc.add_event(db, project, "addon_sacrifice_created", source=source, actor=actor,
                       summary="خروف (إضافة) → ذبيحة " + ", ".join(map(str, out["created"])),
                       payload={"sacrifices": out["created"], "sale_price": str(SHEEP_PRICE)})
        db.expire(project, ["addon_sacrifices"])
    if want < len(have):
        out["extra"] = [s.sacrifice_no for s in have[want:]]
    return out

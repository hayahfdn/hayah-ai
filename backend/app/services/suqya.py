"""«سقيا الماء في الحرم» records: numbering and creation, shared by the dashboard and the Shopify import.
Numbers come from Counter "suqya" (gap-free, under a row lock): a number can be typed once, the next ones
follow it."""
from __future__ import annotations

import re
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Counter, Suqya
from app.services import phones
from app.services.audit import audit

_BOXES = re.compile(r"(\d[\d,]*)\s*(?:عبوة|عبوات|bottles?|boxes?)", re.I)
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def next_no(db: Session) -> int:
    c = db.get(Counter, "suqya")
    top = db.scalar(select(func.max(Suqya.suqya_no))) or 0
    return max(c.value if c else 0, top) + 1


def boxes_in(text: str | None, default: int = 100) -> int:
    """'100 عبوة' / '500 عبوة مياه تُوزَّع ...' -> 100 / 500."""
    m = _BOXES.search((text or "").translate(_AR_DIGITS))
    return int(m.group(1).replace(",", "")) if m else default


def create(db: Session, fields: dict, *, no: int | None = None, actor=None, actor_label: str | None = None) -> Suqya:
    c = db.scalar(select(Counter).where(Counter.name == "suqya").with_for_update())
    if not c:
        c = Counter(name="suqya", value=0)
        db.add(c)
        db.flush()
    no = no or next_no(db)
    if db.scalar(select(Suqya.id).where(Suqya.suqya_no == no)):
        raise HTTPException(409, f"سقيا number {no} already exists")
    c.value = max(c.value, no)
    hints = fields.pop("_phone_hints", None)
    fallback = fields.pop("_phone_fallback_country", None)
    s = Suqya(suqya_no=no, quantity=100, order_date=date.today(),
              created_by=getattr(actor, "full_name", None) or actor_label)
    for k, v in fields.items():
        if isinstance(v, str):
            v = v.strip() or None
        if k == "quantity" and not v:
            continue
        setattr(s, k, v)
    phones.apply(s, hints=hints, fallback_country=fallback)
    db.add(s)
    db.flush()
    audit(db, "suqya.create", "suqya", no, actor=actor, actor_label=actor_label, after=view(s))
    return s


def view(s: Suqya) -> dict:
    return {"suqya_no": s.suqya_no, "order_date": s.order_date.isoformat() if s.order_date else None, "quantity": s.quantity,
            "donor_name": s.donor_name, "dua": s.dua, "customer_name": s.customer_name, "customer_phone": s.customer_phone,
            "customer_phone_e164": s.customer_phone_e164, "sale_price": str(s.sale_price) if s.sale_price is not None else None,
            "shopify_order": s.shopify_order, "sales_source": s.sales_source, "notes": s.notes}

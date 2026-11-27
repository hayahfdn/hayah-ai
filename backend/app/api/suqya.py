"""«سقيا الماء في الحرم» (Hayah, 27 Nov 2026): a small order type of its own with HAYAH numbers, and the
portrait plaque made from it (drawn in the browser like the other plaques).

Employees and managers only, the same people who prepare plaques. Selling price only, never a cost.
Numbers come from Counter "suqya": the first one can be typed (e.g. 104), the next ones follow it.
Backgrounds people upload are kept in the database (app setting "suqya_backgrounds") so the nightly
backup has them; they are never deleted, so a saved plaque always opens again.
"""
import re
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import MANAGERS, PROJECT_CREATORS, require_roles
from app.models import Suqya, User, utcnow
from app.services import phones
from app.services import suqya as svc
from app.services.audit import audit
from app.services.settings_store import get_setting, set_setting

router = APIRouter(prefix="/api/suqya", tags=["suqya"])
EDITORS = Depends(require_roles(PROJECT_CREATORS))
MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
# Only these keys are kept from the plaque editor (text and a few layout choices; images by id only).
DESIGN_KEYS = {"intro", "hadith", "number_label", "month_text", "qty_before", "qty_after", "sadaqa_label", "name",
               "name_size", "name_font", "dua", "site", "footer", "bg", "show_logo"}
BUILTIN_BG = [{"id": "haram", "name": "الحرم المكي · Haram", "src": "/suqya/haram-bg.jpg", "builtin": True}]
_DATA_URL = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")
MAX_IMAGE_BYTES = 4_000_000
FIELDS = ("order_date", "quantity", "donor_name", "dua", "customer_name", "customer_phone", "customer_phone_country",
          "sale_price", "notes")


def month_text(d: date | None) -> str:
    d = d or date.today()
    return f"{MONTHS_AR[d.month - 1]} {d.year}"


def out(s: Suqya) -> dict:
    return {
        "suqya_no": s.suqya_no, "order_date": s.order_date.isoformat() if s.order_date else None, "quantity": s.quantity,
        "donor_name": s.donor_name, "dua": s.dua, "customer_name": s.customer_name, "customer_phone": s.customer_phone,
        "customer_phone_country": s.customer_phone_country, "customer_phone_e164": s.customer_phone_e164,
        "customer_phone_status": s.customer_phone_status,
        "sale_price": float(s.sale_price) if s.sale_price is not None else None, "currency": s.currency, "notes": s.notes,
        "design": s.design, "plaque_saved_at": s.plaque_saved_at, "plaque_saved_by": s.plaque_saved_by,
        "sent_at": s.sent_at, "sent_by": s.sent_by, "created_by": s.created_by, "created_at": s.created_at,
        "month_text": month_text(s.order_date), "shopify_order": s.shopify_order, "sales_source": s.sales_source,
        "dedication": s.dedication,
    }


def _next_no(db: Session) -> int:
    return svc.next_no(db)


def _get(db: Session, no: int) -> Suqya:
    s = db.scalar(select(Suqya).where(Suqya.suqya_no == no))
    if not s:
        raise HTTPException(404, f"No سقيا number {no}")
    return s


class SuqyaIn(BaseModel):
    suqya_no: int | None = Field(default=None, gt=0, lt=10_000_000)
    order_date: date | None = None
    quantity: int | None = Field(default=None, gt=0, lt=1_000_000)
    donor_name: str | None = Field(default=None, max_length=300)
    dua: str | None = Field(default=None, max_length=80)
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=40)
    customer_phone_country: str | None = Field(default=None, max_length=60)
    sale_price: Decimal | None = Field(default=None, ge=0, lt=10_000_000)
    notes: str | None = Field(default=None, max_length=4000)


def _apply(s: Suqya, body: SuqyaIn, fields: set[str]) -> None:
    for k in FIELDS:
        if k in fields:
            v = getattr(body, k)
            if isinstance(v, str):
                v = v.strip() or None
            if k == "quantity" and v is None:
                continue
            setattr(s, k, v)
    if fields & {"customer_phone", "customer_phone_country"}:
        phones.apply(s)


@router.get("")
def list_suqya(q: str | None = None, db: Session = Depends(get_db), _: User = EDITORS):
    stmt = select(Suqya).order_by(Suqya.suqya_no.desc()).limit(300)
    if q and q.strip():
        t = f"%{q.strip()}%"
        cond = (Suqya.donor_name.ilike(t) | Suqya.customer_name.ilike(t) | Suqya.customer_phone.ilike(t)
                | Suqya.shopify_order.ilike(t))
        if q.strip().isdigit():
            cond = cond | (Suqya.suqya_no == int(q.strip()))
        stmt = stmt.where(cond)
    return {"items": [out(s) for s in db.scalars(stmt)], "next_no": _next_no(db)}


@router.post("", status_code=201)
def create(body: SuqyaIn, db: Session = Depends(get_db), user: User = EDITORS):
    fields = {k: getattr(body, k) for k in body.model_fields_set - {"suqya_no"} if k in FIELDS}
    s = svc.create(db, fields, no=body.suqya_no, actor=user)
    db.commit()
    return out(s)


def _audit_view(s: Suqya) -> dict:
    return svc.view(s)


@router.get("/backgrounds")
def backgrounds(db: Session = Depends(get_db), _: User = EDITORS):
    return BUILTIN_BG + [{**i, "builtin": False} for i in get_setting(db, "suqya_backgrounds").get("items", [])]


class ImageIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    data_url: str = Field(max_length=MAX_IMAGE_BYTES)


@router.post("/backgrounds", status_code=201)
def add_background(body: ImageIn, db: Session = Depends(get_db), user: User = EDITORS):
    if not _DATA_URL.match(body.data_url):
        raise HTTPException(415, "Upload a PNG, JPEG or WebP image")
    lib = get_setting(db, "suqya_backgrounds")
    item = {"id": uuid.uuid4().hex[:12], "name": body.name.strip(), "src": body.data_url, "by": user.full_name}
    lib["items"] = [*lib.get("items", []), item]
    set_setting(db, "suqya_backgrounds", lib, user.id)
    audit(db, "suqya_background.add", "settings", item["id"], actor=user, after={"name": item["name"], "bytes": len(body.data_url)})
    db.commit()
    return {**item, "builtin": False}


@router.get("/{no}")
def one(no: int, db: Session = Depends(get_db), _: User = EDITORS):
    return out(_get(db, no))


@router.patch("/{no}")
def update(no: int, body: SuqyaIn, db: Session = Depends(get_db), user: User = EDITORS):
    s = _get(db, no)
    before = _audit_view(s)
    if body.suqya_no and body.suqya_no != no:
        raise HTTPException(422, "The سقيا number cannot be changed here")
    _apply(s, body, body.model_fields_set - {"suqya_no"})
    s.updated_at = utcnow()
    audit(db, "suqya.update", "suqya", no, actor=user, before=before, after=_audit_view(s))
    db.commit()
    return out(s)


class DesignIn(BaseModel):
    design: dict


@router.put("/{no}/design")
def save_design(no: int, body: DesignIn, db: Session = Depends(get_db), user: User = EDITORS):
    s = _get(db, no)
    design = {}
    for k, v in body.design.items():
        if k not in DESIGN_KEYS:
            continue
        if not isinstance(v, (str, int, float, bool)) or (isinstance(v, str) and len(v) > 2000):
            raise HTTPException(422, f"Bad value for {k}")
        design[k] = v
    before = s.design
    s.design = design
    s.plaque_saved_at, s.plaque_saved_by = utcnow(), user.full_name
    audit(db, "suqya.plaque_saved", "suqya", no, actor=user, before={"design": before}, after={"design": design})
    db.commit()
    return out(s)


class SentIn(BaseModel):
    method: str = Field(default="share", pattern="^(share|download)$")


@router.post("/{no}/sent")
def sent(no: int, body: SentIn, db: Session = Depends(get_db), user: User = EDITORS):
    s = _get(db, no)
    s.sent_at, s.sent_by = utcnow(), user.full_name
    audit(db, "suqya.sent", "suqya", no, actor=user, after={"method": body.method, "to": s.customer_phone_e164})
    db.commit()
    return out(s)


@router.delete("/{no}", status_code=204)
def delete(no: int, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    s = _get(db, no)
    audit(db, "suqya.delete", "suqya", no, actor=user, before={**_audit_view(s), "design": s.design})
    db.delete(s)
    db.commit()
    return Response(status_code=204)

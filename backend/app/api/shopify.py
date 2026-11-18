"""Shopify: settings (admin), webhook receiver (public, signed), sync and reports."""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ADMINS, MANAGERS, require_roles
from app.integrations import shopify as api
from app.models import Role, User, utcnow
from app.services import secrets_store
from app.services import shopify as svc
from app.services import shopify_history as hist
from app.services.audit import audit
from app.services.jobs import enqueue

router = APIRouter(prefix="/api/shopify", tags=["shopify"])
SALES_VIEWERS = {Role.super_admin, Role.operations_manager, Role.staff}  # selling price only; contractors never


class ShopifySettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_domain: str | None = Field(default=None, max_length=200)
    client_id: str | None = Field(default=None, max_length=200)
    client_secret: str | None = Field(default=None, max_length=300)  # empty string clears it
    access_token: str | None = Field(default=None, max_length=300)   # empty string clears it
    enabled: bool | None = None
    only_paid: bool | None = None
    import_from: date | None = None
    well_id_start: int | None = Field(default=None, gt=0, lt=10**12)
    sacrifice_no_start: int | None = Field(default=None, gt=0, lt=10**12)


def _err(exc: Exception):
    raise HTTPException(502, str(exc))


@router.get("/settings")
def get_settings_(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    return svc.public_status(db)


@router.put("/settings")
def put_settings(body: ShopifySettingsIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    data = body.model_dump(exclude_unset=True)
    secret = data.pop("client_secret", None)
    token = data.pop("access_token", None)
    if "import_from" in data and data["import_from"]:
        data["import_from"] = data["import_from"].isoformat()
    try:
        svc.save_config(db, data, user.id)
    except api.ShopifyError as exc:
        raise HTTPException(422, str(exc))
    if secret is not None:
        if secret and (len(secret) < 16 or secret.startswith("shpat_")):
            raise HTTPException(422, "That doesn't look like the app's client secret (Dev Dashboard > your app > Settings)")
        secrets_store.set_secret(db, svc.SECRET_CLIENT, secret.strip() or None, user.id)
        secrets_store.set_secret(db, svc.SECRET_CC, None, user.id)
    if token is not None:
        if token and not token.startswith(("shpat_", "shpca_", "shpua_")):
            raise HTTPException(422, "An Admin API access token starts with shpat_")
        secrets_store.set_secret(db, svc.SECRET_TOKEN, token.strip() or None, user.id)
    audit(db, "settings.shopify", "settings", "shopify", actor=user,
          after={**data, "client_secret_changed": secret is not None, "access_token_changed": token is not None})
    db.commit()
    return svc.public_status(db)


@router.post("/test")
def test(db: Session = Depends(get_db), _: User = Depends(require_roles(ADMINS))):
    try:
        shop = svc.test_connection(db)
    except api.ShopifyError as exc:
        _err(exc)
    db.commit()
    return {"ok": True, "shop": shop}


class WebhooksIn(BaseModel):
    base_url: str = Field(max_length=300)


@router.post("/register-webhooks")
def register(body: WebhooksIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    try:
        r = svc.register_webhooks(db, body.base_url)
    except api.ShopifyError as exc:
        _err(exc)
    audit(db, "shopify.webhooks_registered", "settings", "shopify", actor=user, after=r)
    db.commit()
    return r


@router.post("/sync")
def sync(full: bool = False, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    if not svc.is_configured(db):
        raise HTTPException(409, "Shopify is not set up yet (Settings > Shopify)")
    try:
        r = svc.sync_now(db, full=full)
    except api.ShopifyError as exc:
        _err(exc)
    audit(db, "shopify.sync", "settings", "shopify", actor=user, after=r)
    db.commit()
    return r


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Shopify calls this for order events. Verified with the app's client secret; work happens in the worker."""
    body = await request.body()
    if len(body) > 5 * 1024 * 1024:
        raise HTTPException(413, "Payload too large")
    secret = secrets_store.get_secret(db, svc.SECRET_CLIENT)
    if not secret or not api.verify_hmac(body, request.headers.get("X-Shopify-Hmac-Sha256"), secret):
        raise HTTPException(401, "Bad signature")
    cfg = svc.config(db)
    shop = (request.headers.get("X-Shopify-Shop-Domain") or "").lower()
    if cfg["store_domain"] and shop and shop != cfg["store_domain"]:
        raise HTTPException(401, "Unknown store")
    topic = request.headers.get("X-Shopify-Topic") or ""
    if not topic.startswith("orders/"):
        return {"ignored": topic}
    if not cfg.get("enabled"):
        return {"ignored": "disabled"}
    try:
        order = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    wid = request.headers.get("X-Shopify-Webhook-Id") or request.headers.get("X-Shopify-Event-Id")
    enqueue(db, "shopify_order", {"topic": topic, "order": order},
            key=f"shopify:{wid}" if wid else f"shopify:{topic}:{order.get('id')}:{order.get('updated_at')}")
    svc._state(db, last_webhook_at=utcnow().isoformat())
    db.commit()
    return {"queued": True}


@router.get("/orders")
def orders(db: Session = Depends(get_db), _: User = Depends(require_roles(SALES_VIEWERS))):
    return svc.recent_orders(db)  # selling prices and record numbers only; no costs


@router.get("/summary")
def summary(start: date | None = None, end: date | None = None, db: Session = Depends(get_db),
            _: User = Depends(require_roles(SALES_VIEWERS))):
    end = end or date.today()
    start = start or end - timedelta(days=365)
    return {"start": start, "end": end, **svc.sales_summary(db, start, end)}


# ---------------- past orders (before the live start date) ----------------
class HistoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: date | None = None  # empty = since the store's first order


class AddIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: str | None = Field(default=None, max_length=30)  # empty = every past order not in the workbook


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: int
    number: int = Field(gt=0, lt=10**12)  # Well ID or sacrifice number


@router.get("/history")
def history(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGERS))):
    return {**hist.summary(db), "review": hist.review_orders(db), "before": hist._cut_day(svc.config(db))}


@router.post("/history")
def history_run(body: HistoryIn, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    if not svc.is_configured(db):
        raise HTTPException(409, "Shopify is not set up yet (Settings > Shopify)")
    try:
        r = hist.run(db, start=body.start, user=user)
    except api.ShopifyError as exc:
        _err(exc)
    db.commit()
    return r


@router.post("/history/add")
def history_add(body: AddIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    r = hist.add_missing(db, order_name=body.order, user=user)
    db.commit()
    return r


@router.post("/history/link")
def history_link(body: LinkIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGERS))):
    r = hist.link_unit(db, item_id=body.item_id, number=body.number, user=user)
    db.commit()
    return r

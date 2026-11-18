"""Shopify orders -> wells and sacrifices.

Each paid Shopify order becomes HAYAH records automatically:
- a well product (title has "بئر" / "well")      -> one well per unit, with the next Well ID
- a sacrifice product (خروف / ماعز / بقرة ...)    -> one sacrifice per unit, with the next number
- an add-on (has the "للمشروع" property, e.g. extra water tank, feeding)
                                                  -> added to the extras and selling price of
                                                     the well/sacrifice it was bought for
- anything else                                   -> recorded on the order, nothing created

Rules:
- Never twice. The Shopify order id and each line-item unit are unique in the
  database, every import runs under one lock, and an order whose number is
  already typed in the workbook (Shopify column) is linked, not re-created.
- Numbers come from a simple rule (highest real number + 1, or the start number
  set in Settings), never from AI.
- Nothing is deleted. A cancelled or refunded order marks its records (payment
  "refunded" + a note) so a manager can decide.
- The admin's app keys live encrypted in the database (Settings > Shopify).
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.integrations import shopify as api
from app.models import PaymentStatus, Project, Sacrifice, ShopifyOrder, ShopifyOrderItem, utcnow
from app.services import finance as fin
from app.services import projects as psvc
from app.services import secrets_store
from app.services.audit import audit
from app.services.jobs import handler
from app.services.settings_store import get_setting, set_setting

log = logging.getLogger("hayah.shopify")
LOCK_ID = 7_406_119  # pg advisory lock: one Shopify import at a time
SETTING = "shopify"
STATE = "shopify_state"
SECRET_CLIENT = "shopify_client_secret"
SECRET_TOKEN = "shopify_access_token"
SECRET_CC = "shopify_cc_token"
TOPICS = ["ORDERS_CREATE", "ORDERS_PAID", "ORDERS_CANCELLED"]
CENT = Decimal("0.01")

DEFAULTS = {
    "store_domain": "", "client_id": "", "enabled": False, "only_paid": True,
    "import_from": None,           # orders created before this date are left alone (the workbook has them)
    "well_id_start": None,         # optional: first Well ID to use
    "sacrifice_no_start": None,    # optional: first sacrifice number to use
    "timezone": "UTC", "shop_name": None, "api_version": api.API_VERSION,
    "well_keywords": ["بئر", "well"],
    "sacrifice_keywords": ["خروف", "ماعز", "بقرة", "عجل", "أضحية", "اضحية", "عقيقة", "ذبيحة",
                           "sheep", "goat", "cow", "qurbani", "udhiyah", "aqiqah"],
    "dedication_keys": ["الإهداء", "الاهداء", "إهداء", "اهداء", "Dedication", "Dedicated to", "Name on plaque"],
    "phone_keys": ["رقم الهاتف (WhatsApp)", "رقم الهاتف", "WhatsApp", "Phone"],
    "donor_keys": ["اسم صاحب الطلب", "Donor name", "Your name"],
    "intention_keys": ["الغرض", "نوع الطلب", "Purpose", "Intention"],
    "country_keys": ["الدولة المطلوبة", "الدولة", "Country"],
    "addon_keys": ["للمشروع", "For project"],
}
WELL_TYPES = [("شمسي", ["شمسي", "شمسية", "solar"]), ("عميق", ["عميق", "deep"]),
              ("متوسط", ["متوسط", "medium"]), ("يدوي", ["يدوي", "يدوية", "hand"])]
ANIMALS = {"خروف": ["خروف", "sheep", "lamb"], "ماعز": ["ماعز", "goat"], "بقرة": ["بقرة", "عجل", "cow", "calf"]}
COUNTRY_AR = {"باكستان": "Pakistan", "نيبال": "Nepal", "بنغلاديش": "Bangladesh", "بنجلاديش": "Bangladesh",
              "الهند": "India", "تنزانيا": "Tanzania"}
SOURCES = {"ig": "Instagram", "instagram": "Instagram", "fb": "Facebook", "facebook": "Facebook",
           "google": "Google", "chatgpt": "ChatGPT", "tiktok": "TikTok", "snapchat": "Snapchat", "youtube": "YouTube",
           "whatsapp": "WhatsApp", "wa": "WhatsApp", "x": "X", "twitter": "X"}


# ---------------- settings ----------------
def config(db: Session) -> dict:
    return {**DEFAULTS, **get_setting(db, SETTING)}


def save_config(db: Session, changes: dict, user_id: int | None) -> dict:
    cfg = config(db)
    if "store_domain" in changes:
        changes["store_domain"] = api.normalize_domain(changes["store_domain"])
    cfg.update({k: v for k, v in changes.items() if k in DEFAULTS})
    if cfg.get("enabled") and not cfg.get("import_from"):
        # Safety: never pull in old orders the workbook already has, unless the admin picks an earlier date.
        cfg["import_from"] = date.today().isoformat()
    set_setting(db, SETTING, cfg, user_id)
    return cfg


def public_status(db: Session) -> dict:
    cfg = config(db)
    st = get_setting(db, STATE)
    return {**cfg, "client_secret": secrets_store.secret_hint(db, SECRET_CLIENT),
            "access_token": secrets_store.secret_hint(db, SECRET_TOKEN),
            "configured": is_configured(db), "last_sync_at": st.get("last_sync_at"),
            "last_sync_result": st.get("last_sync_result"), "last_webhook_at": st.get("last_webhook_at"),
            "webhooks": st.get("webhooks")}


def is_configured(db: Session) -> bool:
    cfg = config(db)
    has_auth = bool(secrets_store.get_secret(db, SECRET_TOKEN)) or (
        bool(cfg["client_id"]) and bool(secrets_store.get_secret(db, SECRET_CLIENT)))
    return bool(cfg["store_domain"]) and has_auth


def _state(db: Session, **changes) -> None:
    st = get_setting(db, STATE)
    st.update(changes)
    set_setting(db, STATE, st)


# ---------------- talking to Shopify ----------------
def access_token(db: Session) -> str:
    token = secrets_store.get_secret(db, SECRET_TOKEN)
    if token:
        return token
    cfg = config(db)
    cached = secrets_store.secret_meta(db, SECRET_CC)
    if cached.get("expires_at", 0) > time.time() and cached.get("domain") == cfg["store_domain"]:
        tok = secrets_store.get_secret(db, SECRET_CC)
        if tok:
            return tok
    secret = secrets_store.get_secret(db, SECRET_CLIENT)
    if not (cfg["store_domain"] and cfg["client_id"] and secret):
        raise api.ShopifyError("Shopify is not set up yet (Settings > Shopify)")
    tok, exp = api.client_credentials_token(cfg["store_domain"], cfg["client_id"], secret)
    secrets_store.set_secret(db, SECRET_CC, tok, None, {"expires_at": exp, "domain": cfg["store_domain"]})
    return tok


def gql(db: Session, query: str, variables: dict | None = None) -> dict:
    cfg = config(db)
    return api.graphql(cfg["store_domain"], access_token(db), query, variables, cfg.get("api_version") or api.API_VERSION)


def test_connection(db: Session) -> dict:
    data = gql(db, "{ shop { name myshopifyDomain ianaTimezone currencyCode } }")["shop"]
    save_config(db, {"timezone": data.get("ianaTimezone") or "UTC", "shop_name": data.get("name")}, None)
    return data


def register_webhooks(db: Session, base_url: str) -> dict:
    """Subscribe the store's order webhooks to this server. Safe to repeat."""
    uri = base_url.rstrip("/") + "/api/shopify/webhook"
    if not uri.startswith("https://"):
        raise api.ShopifyError("Webhooks need the site's https:// address")
    existing = gql(db, "{ webhookSubscriptions(first: 100) { nodes { id topic uri } } }")["webhookSubscriptions"]["nodes"]
    have = {(w["topic"], w["uri"]) for w in existing}
    created, errors = [], []
    for topic in TOPICS:
        if (topic, uri) in have:
            continue
        r = gql(db, """mutation($topic: WebhookSubscriptionTopic!, $sub: WebhookSubscriptionInput!) {
            webhookSubscriptionCreate(topic: $topic, webhookSubscription: $sub) {
              webhookSubscription { id topic } userErrors { field message } } }""",
                {"topic": topic, "sub": {"uri": uri, "format": "JSON"}})["webhookSubscriptionCreate"]
        if r["userErrors"]:
            errors.append(f"{topic}: {r['userErrors'][0]['message']}")
        else:
            created.append(topic)
    result = {"uri": uri, "active": sorted({t for t, u in have if u == uri} | set(created)), "errors": errors}
    _state(db, webhooks=result)
    return result


ORDERS_QUERY = """query($first: Int!, $after: String, $q: String) {
  orders(first: $first, after: $after, query: $q, sortKey: UPDATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes { id name createdAt displayFinancialStatus cancelledAt note phone email
      customAttributes { key value }
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      customer { firstName lastName defaultPhoneNumber { phoneNumber } }
      billingAddress { name phone }
      lineItems(first: 50) { nodes { id title variantTitle quantity
        customAttributes { key value }
        originalUnitPriceSet { shopMoney { amount } }
        discountAllocations { allocatedAmountSet { shopMoney { amount } } } } } } } }"""


def sync_now(db: Session, *, full: bool = False, max_pages: int = 20) -> dict:
    """Fetch orders changed since the last sync (catches anything a webhook missed)."""
    cfg = config(db)
    st = get_setting(db, STATE)
    since = None if full else st.get("last_sync_at")
    started = utcnow()
    parts = []
    if since:
        parts.append(f"updated_at:>='{(datetime.fromisoformat(since) - timedelta(minutes=30)).isoformat()}'")
    if cfg.get("import_from"):
        parts.append(f"created_at:>='{cfg['import_from']}'")
    q = " AND ".join(parts) or None
    after, counts = None, {"orders_seen": 0, "created_wells": 0, "created_sacrifices": 0, "errors": []}
    for _ in range(max_pages):
        page = gql(db, ORDERS_QUERY, {"first": 50, "after": after, "q": q})["orders"]
        for node in page["nodes"]:
            counts["orders_seen"] += 1
            try:
                r = import_order(db, normalize_graphql(node), source="sync")
                db.commit()
            except Exception as exc:  # one bad order must not stop the others
                db.rollback()
                log.exception("shopify order %s failed", node.get("name"))
                counts["errors"].append(f"{node.get('name')}: {getattr(exc, 'detail', exc)}"[:300])
                continue
            counts["created_wells"] += r.get("created_wells", 0)
            counts["created_sacrifices"] += r.get("created_sacrifices", 0)
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    _state(db, last_sync_at=started.isoformat(), last_sync_result=counts)
    db.commit()
    return counts


# ---------------- order normalization ----------------
def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, ROUND_HALF_UP)


def _attrs(items, k="name", v="value") -> dict:
    out = {}
    for a in items or []:
        key = str(a.get(k) or "").strip()
        if key and key not in out:
            out[key] = str(a.get(v) or "").strip()
    return out


def normalize_rest(o: dict) -> dict:
    """Webhook payload (REST JSON) -> the shape import_order uses."""
    cust = o.get("customer") or {}
    bill = o.get("billing_address") or {}
    lines = []
    for li in o.get("line_items") or []:
        disc = sum((_money(d.get("amount")) for d in li.get("discount_allocations") or []), Decimal(0))
        lines.append({"id": int(li["id"]), "title": li.get("title") or "", "variant_title": li.get("variant_title"),
                      "quantity": int(li.get("quantity") or 1), "unit_price": _money(li.get("price")),
                      "discount": disc, "props": _attrs(li.get("properties"))})
    return {"id": int(o["id"]), "name": o.get("name") or f"#{o.get('order_number')}",
            "created_at": o.get("created_at"), "financial_status": (o.get("financial_status") or "").lower(),
            "cancelled": bool(o.get("cancelled_at")), "total": _money(o.get("current_total_price") or o.get("total_price")),
            "currency": o.get("currency") or "USD", "note": o.get("note"),
            "attrs": _attrs(o.get("note_attributes")),
            "customer_name": " ".join(x for x in [cust.get("first_name"), cust.get("last_name")] if x) or bill.get("name"),
            "phone": o.get("phone") or cust.get("phone") or bill.get("phone"),
            "landing": o.get("landing_site"), "referrer": o.get("referring_site"), "lines": lines}


def normalize_graphql(n: dict) -> dict:
    cust = n.get("customer") or {}
    bill = n.get("billingAddress") or {}
    lines = []
    for li in (n.get("lineItems") or {}).get("nodes") or []:
        disc = sum((_money(d["allocatedAmountSet"]["shopMoney"]["amount"]) for d in li.get("discountAllocations") or []), Decimal(0))
        lines.append({"id": api.gid_number(li["id"]), "title": li.get("title") or "", "variant_title": li.get("variantTitle"),
                      "quantity": int(li.get("quantity") or 1),
                      "unit_price": _money(li["originalUnitPriceSet"]["shopMoney"]["amount"]),
                      "discount": disc, "props": _attrs(li.get("customAttributes"), "key")})
    money = (n.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    attrs = _attrs(n.get("customAttributes"), "key")
    return {"id": api.gid_number(n["id"]), "name": n["name"], "created_at": n.get("createdAt"),
            "financial_status": (n.get("displayFinancialStatus") or "").lower(), "cancelled": bool(n.get("cancelledAt")),
            "total": _money(money.get("amount")), "currency": money.get("currencyCode") or "USD", "note": n.get("note"),
            "attrs": attrs,
            "customer_name": " ".join(x for x in [cust.get("firstName"), cust.get("lastName")] if x) or bill.get("name"),
            "phone": n.get("phone") or (cust.get("defaultPhoneNumber") or {}).get("phoneNumber") or bill.get("phone"),
            "landing": attrs.get("landing_page"), "referrer": attrs.get("referrer"), "lines": lines}


# ---------------- mapping helpers ----------------
def _prop(props: dict, keys: list[str]) -> str | None:
    low = {k.lower(): v for k, v in props.items()}
    for k in keys:
        v = low.get(k.lower())
        if v:
            return v
    return None


def classify(line: dict, cfg: dict) -> str:
    if _prop(line["props"], cfg["addon_keys"]):
        return "addon"
    title = f"{line['title']} {line.get('variant_title') or ''}".lower()
    if any(k.lower() in title for k in cfg["well_keywords"]):
        return "well"
    if any(k.lower() in title for k in cfg["sacrifice_keywords"]):
        return "sacrifice"
    return "other"


def well_type(title: str) -> str | None:
    t = title.lower()
    for value, words in WELL_TYPES:
        if any(w in t for w in words):
            return value
    return None


def animal_type(title: str) -> str:
    t = title.lower()
    for value, words in ANIMALS.items():
        if any(w in t for w in words):
            return value
    return title[:60]


def country(value: str | None, known: list[str]) -> str | None:
    if not value:
        return None
    v = value.strip()
    for c in known:
        if c.lower() == v.lower():
            return c
    return COUNTRY_AR.get(v)


def sales_source(o: dict) -> str:
    src = (o["attrs"].get("utm_source") or "").strip()
    if "{{" in src:
        src = ""
    if not src and o.get("referrer"):
        host = urlparse(o["referrer"] if "//" in o["referrer"] else "//" + o["referrer"]).hostname or ""
        src = host.removeprefix("www.").removeprefix("l.").removeprefix("m.").split(".")[0]
    nice = SOURCES.get(src.lower().split(".")[0], src) if src else ""
    return f"Shopify ({nice})"[:120] if nice else "Shopify"


def order_day(o: dict, tz: str) -> date | None:
    if not o.get("created_at"):
        return None
    dt = datetime.fromisoformat(str(o["created_at"]).replace("Z", "+00:00"))
    try:
        return dt.astimezone(ZoneInfo(tz or "UTC")).date()
    except Exception:  # unknown zone name
        return dt.date()


def _order_no(name: str) -> str:
    return (name or "").strip().lstrip("#").strip()


def _next_well_id(db: Session, cfg: dict) -> int:
    hi = db.scalar(select(func.max(Project.well_id)).where(Project.is_sample.is_(False))) or 0
    return max(hi + 1, int(cfg.get("well_id_start") or 0))


def _next_sacrifice_no(db: Session, cfg: dict) -> int:
    hi = db.scalar(select(func.max(Sacrifice.sacrifice_no)).where(Sacrifice.is_sample.is_(False))) or 0
    return max(hi + 1, int(cfg.get("sacrifice_no_start") or 0))


def _existing_in_workbook(db: Session, name: str):
    """Wells/sacrifices whose Shopify column already holds this order number (typed by hand or imported)."""
    no = _order_no(name)
    if not no:
        return [], []
    norm = lambda col: func.replace(func.trim(col), "#", "")  # noqa: E731
    linked_p = select(ShopifyOrderItem.project_id).where(ShopifyOrderItem.project_id.is_not(None))
    linked_s = select(ShopifyOrderItem.sacrifice_id).where(ShopifyOrderItem.sacrifice_id.is_not(None))
    ps = list(db.scalars(select(Project).where(norm(Project.shopify_order) == no, Project.id.not_in(linked_p))).unique())
    ss = list(db.scalars(select(Sacrifice).where(norm(Sacrifice.shopify_order) == no, Sacrifice.id.not_in(linked_s))).unique())
    return ps, ss


# ---------------- the import ----------------
def import_order(db: Session, o: dict, *, source: str = "webhook") -> dict:
    """Create the wells/sacrifices for one order. Safe to call any number of times."""
    db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": LOCK_ID})
    cfg = config(db)
    row = db.scalar(select(ShopifyOrder).where(ShopifyOrder.shopify_id == o["id"]))
    paid = o["financial_status"] in {"paid", "partially_paid", "partially_refunded"}
    refunded = o["financial_status"] in {"refunded", "voided"}
    if row is None:
        day = order_day(o, cfg["timezone"])
        if cfg.get("import_from") and day and day < date.fromisoformat(cfg["import_from"]):
            return {"status": "before_start"}
        row = ShopifyOrder(shopify_id=o["id"], name=o["name"], source=source, status="new")
        db.add(row)
    row.created_at_shop = datetime.fromisoformat(str(o["created_at"]).replace("Z", "+00:00")) if o.get("created_at") else None
    row.financial_status, row.total, row.currency = o["financial_status"], o["total"], o["currency"]
    row.customer_name = (o.get("customer_name") or "")[:200] or None
    row.raw = _jsonable_order(o)
    row.updated_at = utcnow()
    db.flush()

    result = {"status": row.status, "created_wells": 0, "created_sacrifices": 0}
    if o["cancelled"] or refunded:
        if not row.cancelled:
            _mark_cancelled(db, row, o)
        row.cancelled = True
        result["status"] = row.status
        return result
    if row.status in {"imported", "already_in_workbook", "nothing_to_import", "needs_review"}:
        if paid:
            _mark_paid(db, row)
        return result
    if cfg.get("only_paid", True) and not paid:
        row.status, row.message = "waiting_payment", f"Not paid yet ({o['financial_status'] or 'pending'})"
        result["status"] = row.status
        return result

    # Already typed in the workbook? Link instead of creating a second copy.
    ps, ss = _existing_in_workbook(db, o["name"])
    if ps or ss:
        for p in ps:
            db.add(ShopifyOrderItem(order_id=row.id, line_item_id=-p.id, unit=1, title="(workbook row)", kind="well",
                                    amount=p.sale_amount, project_id=p.id))
        for s in ss:
            db.add(ShopifyOrderItem(order_id=row.id, line_item_id=-(10**9 + s.id), unit=1, title="(workbook row)",
                                    kind="sacrifice", amount=s.sale_price, sacrifice_id=s.id))
        row.status = "already_in_workbook"
        row.message = (f"Order {o['name']} is already in the workbook: "
                       + ", ".join([f"well {p.well_id}" for p in ps] + [f"sacrifice {s.sacrifice_no}" for s in ss]))
        result["status"] = row.status
        audit(db, "shopify.order_linked", "shopify_order", o["name"], actor_label="Shopify", after={"message": row.message})
        return result

    mains, addons, others = [], [], []
    for li in o["lines"]:
        kind = classify(li, cfg)
        (addons if kind == "addon" else others if kind == "other" else mains).append((kind, li))
    units = []  # one entry per well/sacrifice to create
    for kind, li in mains:
        net = (li["unit_price"] - (li["discount"] / li["quantity"])).quantize(CENT, ROUND_HALF_UP)
        for u in range(1, li["quantity"] + 1):
            units.append({"kind": kind, "line": li, "unit": u, "amount": net, "extras": []})
    problems = []
    for _, li in addons:
        target = _prop(li["props"], cfg["addon_keys"]) or ""
        matches = [x for x in units if x["line"]["title"].strip() == target.strip()] or units
        if not matches:
            problems.append(f"add-on '{li['title']}' has no well or sacrifice in this order")
            continue
        net = (li["unit_price"] - (li["discount"] / li["quantity"])).quantize(CENT, ROUND_HALF_UP)
        for i in range(li["quantity"]):
            x = matches[i % len(matches)]
            x["amount"] += net
            x["extras"].append(li["title"] + (f" ({li['variant_title']})" if li.get("variant_title") else ""))
        db.add(ShopifyOrderItem(order_id=row.id, line_item_id=li["id"], unit=1, title=li["title"][:300], kind="addon",
                                amount=net * li["quantity"]))
    for _, li in others:
        db.add(ShopifyOrderItem(order_id=row.id, line_item_id=li["id"], unit=1, title=li["title"][:300], kind="other",
                                amount=li["unit_price"] * li["quantity"]))
        problems.append(f"'{li['title']}' is not a well or sacrifice, so nothing was created for it")

    day = order_day(o, cfg["timezone"])
    src = sales_source(o)
    made = []
    for x in units:
        li, props = x["line"], x["line"]["props"]
        donor = _prop(props, cfg["donor_keys"]) or o.get("customer_name")
        phone = (_prop(props, cfg["phone_keys"]) or o.get("phone") or "")[:40] or None
        ded = _prop(props, cfg["dedication_keys"])
        mapped = {k.lower() for k in cfg["dedication_keys"] + cfg["phone_keys"] + cfg["donor_keys"]
                  + cfg["intention_keys"] + cfg["country_keys"]}
        extra_props = [f"{k}: {v}" for k, v in props.items() if not k.startswith("_") and k.lower() not in mapped and v]
        notes = "\n".join([f"From Shopify order {o['name']}" + (f" ({x['unit']} of {li['quantity']})" if li["quantity"] > 1 else "")]
                          + extra_props + ([f"Order note: {o['note']}"] if o.get("note") else []))
        extras = ", ".join(x["extras"])[:200] or None
        if x["kind"] == "well":
            data = {"well_id": _next_well_id(db, cfg), "order_date": day, "customer_name": (donor or "")[:200] or None,
                    "customer_phone": phone, "country": country(_prop(props, cfg["country_keys"]), get_setting(db, "countries").get("values", [])),
                    "well_type": well_type(f"{li['title']} {li.get('variant_title') or ''}"), "sales_source": src,
                    "sale_amount": x["amount"], "currency": o["currency"][:3], "payment_method": "Shopify",
                    "payment_status": PaymentStatus.paid if paid else PaymentStatus.unpaid,
                    "extras": extras, "shopify_order": o["name"][:60], "dedication": ded, "notes": notes}
            p = psvc.create_project(db, data, actor=None, source="shopify")
            db.add(ShopifyOrderItem(order_id=row.id, line_item_id=li["id"], unit=x["unit"], title=li["title"][:300],
                                    kind="well", amount=x["amount"], project_id=p.id))
            made.append(f"well {p.well_id}")
            result["created_wells"] += 1
        else:
            data = {"sacrifice_no": _next_sacrifice_no(db, cfg), "order_date": day, "donor_name": (donor or "")[:200] or None,
                    "animal_type": animal_type(f"{li['title']} {li.get('variant_title') or ''}"), "sale_price": x["amount"],
                    "currency": o["currency"][:3], "payment_method": "Shopify", "extras": extras, "sales_source": src,
                    "shopify_order": o["name"][:60], "intention": (_prop(props, cfg["intention_keys"]) or "")[:120] or None,
                    "dedication": ded, "notes": "\n".join(filter(None, [notes, f"Phone: {phone}" if phone else None]))}
            s = fin.create_sacrifice(db, data, actor=None, source="shopify")
            db.add(ShopifyOrderItem(order_id=row.id, line_item_id=li["id"], unit=x["unit"], title=li["title"][:300],
                                    kind="sacrifice", amount=x["amount"], sacrifice_id=s.id))
            made.append(f"sacrifice {s.sacrifice_no}")
            result["created_sacrifices"] += 1
        db.flush()

    if not units:
        row.status = "nothing_to_import"
    elif problems:
        row.status = "needs_review"
    else:
        row.status = "imported"
    row.message = "; ".join(([f"Created {', '.join(made)}"] if made else []) + problems) or None
    result["status"] = row.status
    audit(db, "shopify.order_imported", "shopify_order", o["name"], actor_label="Shopify",
          after={"status": row.status, "message": row.message, "source": source})
    return result


def _linked(db: Session, row: ShopifyOrder):
    items = list(db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id)))
    ps = [db.get(Project, i.project_id) for i in items if i.project_id]
    ss = [db.get(Sacrifice, i.sacrifice_id) for i in items if i.sacrifice_id]
    return ps, ss


def _mark_paid(db: Session, row: ShopifyOrder) -> None:
    ps, _ = _linked(db, row)
    for p in ps:
        if p.payment_status == PaymentStatus.unpaid:
            psvc.update_project(db, p, {"payment_status": PaymentStatus.paid}, actor=None, source="shopify")


def _mark_cancelled(db: Session, row: ShopifyOrder, o: dict) -> None:
    """Never delete: mark the records so a manager can decide what to do."""
    note = f"Shopify order {o['name']} was cancelled/refunded on {date.today().isoformat()}. Check before building."
    ps, ss = _linked(db, row)
    for p in ps:
        psvc.update_project(db, p, {"payment_status": PaymentStatus.refunded,
                                    "notes": ((p.notes or "") + "\n" + note).strip()}, actor=None, source="shopify")
    for s in ss:
        fin.update_sacrifice(db, s, {"notes": ((s.notes or "") + "\n" + note).strip()}, actor=None, source="shopify")
    row.status = "cancelled"
    row.message = note if (ps or ss) else f"Cancelled/refunded in Shopify ({o['financial_status'] or 'cancelled'})"
    audit(db, "shopify.order_cancelled", "shopify_order", o["name"], actor_label="Shopify", after={"message": row.message})


def _jsonable_order(o: dict) -> dict:
    def j(v):
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, dict):
            return {k: j(x) for k, x in v.items()}
        if isinstance(v, list):
            return [j(x) for x in v]
        return v
    return j(o)


# ---------------- reports ----------------
def sales_summary(db: Session, start: date, end: date) -> dict:
    rows = db.execute(text("""
        select to_char(date_trunc('month', o.created_at_shop), 'YYYY-MM') m, i.kind, count(*) n, coalesce(sum(i.amount), 0) a
        from shopify_order_items i join shopify_orders o on o.id = i.order_id
        where i.kind in ('well', 'sacrifice') and not o.cancelled
          and o.created_at_shop::date between :s and :e
        group by 1, 2 order by 1"""), {"s": start, "e": end}).all()
    months: dict[str, dict] = {}
    for m, kind, n, a in rows:
        r = months.setdefault(m, {"month": m, "wells": 0, "wells_amount": 0.0, "sacrifices": 0, "sacrifices_amount": 0.0})
        key = "wells" if kind == "well" else "sacrifices"
        r[key] += n
        r[key + "_amount"] += float(a)
    orders = db.scalar(text("""select count(*) from shopify_orders where not cancelled
                               and created_at_shop::date between :s and :e"""), {"s": start, "e": end})
    by_source = db.execute(text("""
        select coalesce(p.sales_source, s.sales_source, 'Shopify') src, count(*), coalesce(sum(i.amount), 0)
        from shopify_order_items i join shopify_orders o on o.id = i.order_id
        left join projects p on p.id = i.project_id left join sacrifices s on s.id = i.sacrifice_id
        where i.kind in ('well', 'sacrifice') and not o.cancelled
          and o.created_at_shop::date between :s and :e group by 1 order by 3 desc"""), {"s": start, "e": end}).all()
    total = sum(r["wells_amount"] + r["sacrifices_amount"] for r in months.values())
    return {"orders": orders or 0, "total_amount": total, "by_month": list(months.values()),
            "by_source": [{"source": s, "count": n, "amount": float(a)} for s, n, a in by_source]}


def recent_orders(db: Session, limit: int = 100) -> list[dict]:
    out = []
    for r in db.scalars(select(ShopifyOrder).order_by(ShopifyOrder.created_at_shop.desc().nulls_last()).limit(limit)):
        items = db.execute(select(ShopifyOrderItem.kind, Project.well_id, Sacrifice.sacrifice_no)
                           .outerjoin(Project, Project.id == ShopifyOrderItem.project_id)
                           .outerjoin(Sacrifice, Sacrifice.id == ShopifyOrderItem.sacrifice_id)
                           .where(ShopifyOrderItem.order_id == r.id)).all()
        out.append({"name": r.name, "created_at": r.created_at_shop, "financial_status": r.financial_status,
                    "cancelled": r.cancelled, "total": float(r.total or 0), "currency": r.currency,
                    "customer_name": r.customer_name, "status": r.status, "message": r.message, "source": r.source,
                    "well_ids": [w for k, w, _ in items if w], "sacrifice_nos": [s for k, _, s in items if s]})
    return out


# ---------------- background jobs ----------------
@handler("shopify_order")
def _job_order(db: Session, payload: dict):
    o = normalize_rest(payload["order"])
    r = import_order(db, o, source="webhook")
    db.commit()
    return r


@handler("shopify_sync")
def _job_sync(db: Session, payload: dict):
    if not (config(db).get("enabled") and is_configured(db)):
        return {"skipped": True}
    return sync_now(db)

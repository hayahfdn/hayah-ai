"""Shopify orders -> wells and sacrifices.

Each paid Shopify order becomes HAYAH records automatically:
- a well product (title has "بئر" / "well")      -> one well per unit, with the next Well ID
- a sacrifice product (خروف / ماعز / بقرة ...)    -> one sacrifice per unit, with the next number
- a water (سقيا) product, e.g. "100 عبوة"          -> one سقيا project per unit, with the next سقيا number;
                                                     bought as an add-on of a well/sacrifice it is still its own
                                                     سقيا (its price moves to the سقيا), details from that project
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
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import Text, func, select, text
from sqlalchemy.orm import Session

from app.integrations import shopify as api
from app.models import PaymentStatus, Project, Sacrifice, ShopifyOrder, ShopifyOrderItem, Suqya, utcnow
from app.services import addons
from app.services import finance as fin
from app.services import projects as psvc
from app.services import secrets_store
from app.services import suqya as suqya_svc
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
    # Water for the guests of al-Haram (Hayah, 27 Nov 2026): its own project type, even when bought as an add-on.
    "suqya_keywords": ["سقيا", "سقي الماء", "ضيوف الرحمن", "عبوة مياه", "عبوات مياه", "suqya", "water bottles"],
    # Older orders have add-ons without the "للمشروع" property: these words in the title mark one.
    "addon_keywords": ["إضافة", "اضافة", "سيراميك", "خزان", "دلو", "إطعام", "اطعام",
                       "ceramic", "tank", "bucket", "feeding", "add-on"],
    "sacrifice_addon_keywords": ["إطعام", "اطعام", "feeding"],
    # Add-ons that are projects of their own: e.g. the 99 USD sheep bought with a well becomes a normal
    # sacrifice (own number, plaque, video) linked to the same Shopify order. Matched by the Shopify
    # product ID first, then by the exact product title. More products can be added here later.
    "standalone_addons": [{"product_ids": [15429437489372], "titles": ["خروف", "Sheep", "Lamb"],
                           "kind": "sacrifice", "intention": "صدقة", "animal": "خروف"}],
    "standalone_from_order": 1225,  # orders before this number keep the old behaviour (Hayah, 2026-11-19)
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
    nodes { id name createdAt displayFinancialStatus cancelledAt note phone
      customAttributes { key value }
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      billingAddress { name phone countryCodeV2 }
      lineItems(first: 50) { nodes { id title variantTitle quantity
        product { id }
        customAttributes { key value }
        originalUnitPriceSet { shopMoney { amount } }
        discountAllocations { allocatedAmountSet { shopMoney { amount } } } } } } } }"""


# The app only has read_orders (+ read_all_orders): no `customer` (that needs read_customers).
# If the store also blocks the billing name/phone/email (protected customer data), retry with an order-only
# query; the donor name and WhatsApp number come from the line properties anyway.
def orders_page(db: Session, query: str, variables: dict) -> dict:
    try:
        return gql(db, query, variables)["orders"]
    except api.ShopifyError as exc:
        if "access denied" not in str(exc).lower():
            raise
        log.warning("shopify: customer fields blocked, using the order-only query (%s)", exc)
    # (also without the product ID, in case the app lacks read_products: add-ons then match by title)
    small = query.replace("note phone\n", "note\n").replace("      billingAddress { name phone countryCodeV2 }\n", "").replace("        product { id }\n", "")
    return gql(db, small, variables)["orders"]


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
        page = orders_page(db, ORDERS_QUERY, {"first": 50, "after": after, "q": q})
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
            counts["created_suqya"] = counts.get("created_suqya", 0) + r.get("created_suqya", 0)
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    try:
        split = split_imported_addons(db)
        if split:
            counts["addons_split"] = split
        water = import_missing_suqya(db)
        if water:
            counts["suqya_created"] = water
        fixed = repair_phone_countries(db)
        if fixed:
            counts["phones_completed"] = fixed
        db.commit()
    except Exception:  # never let this stop the sync itself
        db.rollback()
        log.exception("shopify: splitting imported add-ons failed")
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


def slim_rest(o: dict) -> dict:
    """Keep only what HAYAH uses from a webhook order (no address, email or payment details) before it is queued."""
    cust, bill = o.get("customer") or {}, o.get("billing_address") or {}
    keep = ("id", "name", "order_number", "created_at", "updated_at", "financial_status", "cancelled_at",
            "current_total_price", "total_price", "currency", "note", "note_attributes", "phone",
            "landing_site", "referring_site")
    return {**{k: o.get(k) for k in keep},
            "customer": {"first_name": cust.get("first_name"), "last_name": cust.get("last_name"), "phone": cust.get("phone")},
            "billing_address": {"name": bill.get("name"), "phone": bill.get("phone"), "country_code": bill.get("country_code")},
            "line_items": [{k: li.get(k) for k in ("id", "product_id", "title", "variant_title", "quantity", "price",
                                                    "discount_allocations", "properties")}
                           for li in o.get("line_items") or []]}


def normalize_rest(o: dict) -> dict:
    """Webhook payload (REST JSON) -> the shape import_order uses."""
    cust = o.get("customer") or {}
    bill = o.get("billing_address") or {}
    lines = []
    for li in o.get("line_items") or []:
        disc = sum((_money(d.get("amount")) for d in li.get("discount_allocations") or []), Decimal(0))
        lines.append({"id": int(li["id"]), "title": li.get("title") or "", "variant_title": li.get("variant_title"),
                      "quantity": int(li.get("quantity") or 1), "unit_price": _money(li.get("price")),
                      "discount": disc, "props": _attrs(li.get("properties")),
                      "product_id": int(li["product_id"]) if li.get("product_id") else None})
    return {"id": int(o["id"]), "name": o.get("name") or f"#{o.get('order_number')}",
            "created_at": o.get("created_at"), "financial_status": (o.get("financial_status") or "").lower(),
            "cancelled": bool(o.get("cancelled_at")), "total": _money(o.get("current_total_price") or o.get("total_price")),
            "currency": o.get("currency") or "USD", "note": o.get("note"),
            "attrs": _attrs(o.get("note_attributes")),
            "customer_name": " ".join(x for x in [cust.get("first_name"), cust.get("last_name")] if x) or bill.get("name"),
            "phone": o.get("phone") or cust.get("phone") or bill.get("phone"),
            "country_code": bill.get("country_code"),  # the customer's country (only the code is kept)
            "landing": o.get("landing_site"), "referrer": o.get("referring_site"), "lines": lines}


def _first_props(n: dict) -> dict:
    for li in (n.get("lineItems") or {}).get("nodes") or []:
        props = _attrs(li.get("customAttributes"), "key")
        if props:
            return props
    return {}


def normalize_graphql(n: dict) -> dict:
    cust = n.get("customer") or {}
    bill = n.get("billingAddress") or {}
    lines = []
    for li in (n.get("lineItems") or {}).get("nodes") or []:
        disc = sum((_money(d["allocatedAmountSet"]["shopMoney"]["amount"]) for d in li.get("discountAllocations") or []), Decimal(0))
        lines.append({"id": api.gid_number(li["id"]), "title": li.get("title") or "", "variant_title": li.get("variantTitle"),
                      "quantity": int(li.get("quantity") or 1),
                      "unit_price": _money(li["originalUnitPriceSet"]["shopMoney"]["amount"]),
                      "discount": disc, "props": _attrs(li.get("customAttributes"), "key"),
                      "product_id": api.gid_number(li["product"]["id"]) if (li.get("product") or {}).get("id") else None})
    money = (n.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    attrs = _attrs(n.get("customAttributes"), "key")
    return {"id": api.gid_number(n["id"]), "name": n["name"], "created_at": n.get("createdAt"),
            "financial_status": (n.get("displayFinancialStatus") or "").lower(), "cancelled": bool(n.get("cancelledAt")),
            "total": _money(money.get("amount")), "currency": money.get("currencyCode") or "USD", "note": n.get("note"),
            "attrs": attrs,
            "customer_name": " ".join(x for x in [cust.get("firstName"), cust.get("lastName")] if x) or bill.get("name")
            or _prop(_first_props(n), DEFAULTS["donor_keys"]),
            "phone": n.get("phone") or (cust.get("defaultPhoneNumber") or {}).get("phoneNumber") or bill.get("phone"),
            "country_code": bill.get("countryCodeV2"),
            "landing": attrs.get("landing_page"), "referrer": attrs.get("referrer"), "lines": lines}


# ---------------- mapping helpers ----------------
def _prop(props: dict, keys: list[str]) -> str | None:
    low = {k.lower(): v for k, v in props.items()}
    for k in keys:
        v = low.get(k.lower())
        if v:
            return v
    return None


def is_suqya(line: dict, cfg: dict) -> bool:
    title = f"{line['title']} {line.get('variant_title') or ''}".lower()
    return any(k.lower() in title for k in cfg.get("suqya_keywords") or DEFAULTS["suqya_keywords"])


def classify(line: dict, cfg: dict) -> str:
    if is_suqya(line, cfg):
        return "suqya"
    if _prop(line["props"], cfg["addon_keys"]):
        return "addon"
    if any(k.lower() in line["title"].lower() for k in cfg["addon_keywords"]):
        return "addon"  # e.g. "إضافة سيراميك للبئر" (its variant names the well it is for)
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


ORGANIC_MEDIUMS = {"", "social", "bio", "link_in_bio", "profile", "organic", "story", "post"}


def sales_source(o: dict) -> str:
    """The order's source as received, e.g. "Shopify (Instagram)" or "Shopify (Insta Ads · Gulf - Reels)".
    Insta Ads: an Instagram visit that came from an ad (a campaign name, or Meta's unfilled {{...}} ad template);
    the bio link (utm_content link_in_bio, medium social) is plain Instagram (Hayah, 2026-11-19).
    The unified group used by reports is worked out from this text (app/services/sales_sources.py)."""
    a = o["attrs"]
    src = (a.get("utm_source") or "").strip()
    medium = (a.get("utm_medium") or "").strip()
    template = "{{" in src
    if template:
        src, medium = "", ""
    host = ""
    if o.get("referrer"):
        host = urlparse(o["referrer"] if "//" in o["referrer"] else "//" + o["referrer"]).hostname or ""
        host = host.removeprefix("www.").removeprefix("l.").removeprefix("m.").split(".")[0]
    nice = SOURCES.get((src or host).lower().split(".")[0], src or host) if (src or host) else ""
    if nice == "Instagram" and (template or medium.lower() not in ORGANIC_MEDIUMS
                                or (a.get("utm_content") or "").lower() not in {"", "link_in_bio"} and medium.lower() != "social"):
        camp = (a.get("utm_campaign") or "").strip()
        camp = "" if "{{" in camp else camp
        return (f"Shopify (Insta Ads · {camp})" if camp else "Shopify (Insta Ads)")[:120]
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
    from app.services.renumber import next_sacrifice_no
    return next_sacrifice_no(db, cfg.get("sacrifice_no_start"))


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
    if row.source != "history":  # a past order keeps the copy the history import matched from
        row.raw = _jsonable_order(o)
    row.updated_at = utcnow()
    db.flush()

    result = {"status": row.status, "created_wells": 0, "created_sacrifices": 0, "created_suqya": 0}
    if o["cancelled"] or refunded:
        if not row.cancelled:
            _mark_cancelled(db, row, o)
        row.cancelled = True
        result["status"] = row.status
        return result
    if row.source == "history":  # a past order: handled by the history import, never re-created here
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

    units, problems = _plan(db, row, o, cfg)
    made = []
    for x in units:
        made.append(_create_unit(db, row, o, x, cfg, paid))
        result[{"well": "created_wells", "suqya": "created_suqya"}.get(x["kind"], "created_sacrifices")] += 1

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


def _net(li: dict) -> Decimal:
    return (li["unit_price"] - (li["discount"] / li["quantity"])).quantize(CENT, ROUND_HALF_UP)


def _plan(db: Session, row: ShopifyOrder, o: dict, cfg: dict) -> tuple[list[dict], list[str]]:
    """Split an order into units (one per well/sacrifice) with their add-ons folded in.
    Records the add-on and other lines on the order. Returns (units, problems)."""
    mains, addons, others = [], [], []
    for li in o["lines"]:
        kind = classify(li, cfg)
        (addons if kind == "addon" else others if kind == "other" else mains).append((kind, li))
    units = []
    for kind, li in mains:
        if kind == "suqya":
            continue
        for u in range(1, li["quantity"] + 1):
            units.append({"kind": kind, "line": li, "unit": u, "amount": _net(li), "extras": []})
    for kind, li in mains:  # water: own سقيا per unit; as an add-on, who it is for comes from that project
        if kind != "suqya":
            continue
        target = (_prop(li["props"], cfg["addon_keys"]) or "").strip()
        parents = ([x for x in units if x["line"]["title"].strip() == target] or units) if target else []
        for u in range(1, li["quantity"] + 1):
            units.append({"kind": "suqya", "line": li, "unit": u, "amount": _net(li), "extras": [],
                          "parent": parents[(u - 1) % len(parents)] if parents else None, "rule": {}})
    problems = []
    have = {(i.line_item_id, i.unit) for i in db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id))}
    own = [] if _order_number(o["name"]) < int(cfg.get("standalone_from_order") or 0) else \
        [(li, rule) for li in [li for _, li in addons] if (rule := standalone_rule(li, cfg))]
    own_ids = {li["id"] for li, _ in own}
    addons = [(k, li) for k, li in addons if li["id"] not in own_ids]
    for li, rule in own:  # e.g. a sheep bought with a well: its own sacrifice, details from that well
        target = (_prop(li["props"], cfg["addon_keys"]) or "").strip()
        parents = [x for x in units if x["line"]["title"].strip() == target] or [x for x in units if x["kind"] == "well"] or units
        for u in range(1, li["quantity"] + 1):
            units.append({"kind": rule["kind"], "line": li, "unit": u, "amount": _net(li), "extras": [],
                          "parent": parents[(u - 1) % len(parents)] if parents else None, "rule": rule})
    for _, li in addons:
        target = (_prop(li["props"], cfg["addon_keys"]) or li.get("variant_title") or "").strip()
        matches = [x for x in units if x["line"]["title"].strip() == target]
        if not matches:
            want = "sacrifice" if any(k.lower() in li["title"].lower() for k in cfg["sacrifice_addon_keywords"]) else "well"
            matches = [x for x in units if x["kind"] == want] or units
        if not matches:
            problems.append(f"add-on '{li['title']}' has no well or sacrifice in this order")
            continue
        net = _net(li)
        for i in range(li["quantity"]):
            x = matches[i % len(matches)]
            x["amount"] += net
            x["extras"].append(li["title"] + (f" ({li['variant_title']})" if li.get("variant_title") else ""))
        if (li["id"], 1) not in have:
            db.add(ShopifyOrderItem(order_id=row.id, line_item_id=li["id"], unit=1, title=li["title"][:300], kind="addon",
                                    amount=net * li["quantity"]))
    for _, li in others:
        if (li["id"], 1) not in have:
            db.add(ShopifyOrderItem(order_id=row.id, line_item_id=li["id"], unit=1, title=li["title"][:300], kind="other",
                                    amount=li["unit_price"] * li["quantity"]))
        problems.append(f"'{li['title']}' is not a well or sacrifice, so nothing was created for it")
    return units, problems


def standalone_rule(li: dict, cfg: dict) -> dict | None:
    """The rule that makes this add-on line a project of its own, if any (product ID, else exact title)."""
    if not _prop(li["props"], cfg["addon_keys"]):
        return None
    for rule in cfg.get("standalone_addons") or []:
        if li.get("product_id") and li["product_id"] in (rule.get("product_ids") or []):
            return rule
        if li["title"].strip().lower() in {t.strip().lower() for t in rule.get("titles") or []}:
            return rule
    return None


def _order_number(name: str) -> int:
    no = _order_no(name)
    return int(no) if no.isdigit() else 0


def _unit_fields(db: Session, o: dict, x: dict, cfg: dict) -> dict:
    if x.get("parent"):  # an add-on of its own: who it is for comes from the well it was bought with
        f = _unit_fields(db, o, x["parent"], cfg)
        return {**f, "intention": (x.get("rule") or {}).get("intention") or f["intention"],
                "title": f"{x['line']['title']} {x['line'].get('variant_title') or ''}"}
    li, props = x["line"], x["line"]["props"]
    return {"donor": _prop(props, cfg["donor_keys"]) or o.get("customer_name"),
            "phone": (_prop(props, cfg["phone_keys"]) or o.get("phone") or "")[:40] or None,
            "dedication": _prop(props, cfg["dedication_keys"]),
            "intention": (_prop(props, cfg["intention_keys"]) or "")[:120] or None,
            "country": country(_prop(props, cfg["country_keys"]), get_setting(db, "countries").get("values", [])),
            "title": f"{li['title']} {li.get('variant_title') or ''}"}


def _create_unit(db: Session, row: ShopifyOrder, o: dict, x: dict, cfg: dict, paid: bool,
                 item: ShopifyOrderItem | None = None, match: str | None = None) -> str:
    """Create the well or sacrifice for one unit and link it. Returns e.g. 'well 1350'."""
    li, props = x["line"], x["line"]["props"]
    f = _unit_fields(db, o, x, cfg)
    mapped = {k.lower() for k in cfg["dedication_keys"] + cfg["phone_keys"] + cfg["donor_keys"]
              + cfg["intention_keys"] + cfg["country_keys"]}
    extra_props = [f"{k}: {v}" for k, v in props.items() if not k.startswith("_") and k.lower() not in mapped and v]
    if x.get("parent"):
        p_li = x["parent"]["line"]
        extra_props = [f"Add-on bought with {p_li['title']} in the same order"]
    notes = "\n".join([f"From Shopify order {o['name']}" + (f" ({x['unit']} of {li['quantity']})" if li["quantity"] > 1 else "")]
                      + extra_props + ([f"Order note: {o['note']}"] if o.get("note") else []))
    extras = ", ".join(x["extras"])[:200] or None
    day, src = order_day(o, cfg["timezone"]), sales_source(o)
    item = item or ShopifyOrderItem(order_id=row.id, line_item_id=li["id"], unit=x["unit"])
    item.title, item.kind, item.amount, item.match = li["title"][:300], x["kind"], x["amount"], match
    if x["kind"] == "suqya":
        s = suqya_svc.create(db, {
            "order_date": day, "quantity": suqya_svc.boxes_in(f"{li.get('variant_title') or ''} {li['title']}"),
            "donor_name": ((f["dedication"] or f["donor"] or "") if not x.get("parent") else (f["dedication"] or f["donor"] or ""))[:300] or None,
            "customer_name": (f["donor"] or o.get("customer_name") or "")[:200] or None,
            "customer_phone": f["phone"], "_phone_hints": [o.get("phone")], "_phone_fallback_country": o.get("country_code"),
            "sale_price": x["amount"], "currency": o["currency"][:3], "shopify_order": o["name"][:60], "sales_source": src,
            "dedication": f["dedication"], "notes": notes}, actor_label="Shopify")
        item.suqya_id = s.id
        db.add(item)
        db.flush()
        return f"سقيا {s.suqya_no}"
    if x["kind"] == "well":
        data = {"well_id": _next_well_id(db, cfg), "order_date": day, "customer_name": (f["donor"] or "")[:200] or None,
                "customer_phone": f["phone"], "_phone_hints": [o.get("phone")], "_phone_fallback_country": o.get("country_code"), "country": f["country"], "well_type": well_type(f["title"]), "sales_source": src,
                "sale_amount": x["amount"], "currency": o["currency"][:3], "payment_method": "Shopify",
                "payment_status": PaymentStatus.paid if paid else PaymentStatus.unpaid,
                "extras": extras, "shopify_order": o["name"][:60], "dedication": f["dedication"], "notes": notes}
        p = psvc.create_project(db, data, actor=None, source="shopify")
        item.project_id = p.id
        x["created_project"] = p
        label = f"well {p.well_id}"
    else:
        well = (x.get("parent") or {}).get("created_project")
        data = {"sacrifice_no": _next_sacrifice_no(db, cfg), "parent_project_id": well.id if well is not None else None, "order_date": day, "donor_name": (f["donor"] or "")[:200] or None,
                "animal_type": (x.get("rule") or {}).get("animal") or animal_type(f["title"]), "sale_price": x["amount"],
                "customer_phone": f["phone"], "_phone_hints": [o.get("phone")], "_phone_fallback_country": o.get("country_code"),
                "currency": o["currency"][:3], "payment_method": "Shopify", "extras": extras, "sales_source": src,
                "shopify_order": o["name"][:60], "intention": f["intention"],
                "dedication": f["dedication"], "notes": "\n".join(filter(None, [notes, f"Phone: {f['phone']}" if f["phone"] else None]))}
        sac = fin.create_sacrifice(db, data, actor=None, source="shopify")
        item.sacrifice_id = sac.id
        label = f"sacrifice {sac.sacrifice_no}"
        if well is not None:  # the sheep stays listed in the well's add-ons; its price is on the sacrifice only
            listed, n = addons.split(well.extras), len(addons.linked(db, well))
            if addons.sheep_count(well.extras) != n:
                listed = [e for e in listed if not addons.is_sheep(e)] + [li["title"] if n == 1 else f"{li['title']} ×{n}"]
            psvc.update_project(db, well, {"notes": ((well.notes or "") + f"\n{li['title']} add-on: sacrifice {sac.sacrifice_no}").strip(),
                                           "extras": addons.join(listed)}, actor=None, source="shopify")
    db.add(item)
    db.flush()
    return label


def split_imported_addons(db: Session) -> list[str]:
    """Orders imported before the standalone add-on rule (from #standalone_from_order on) whose sheep was
    folded into the well: create the sacrifice now, take only its price off the well and drop it from the
    well's extras. Safe to run any number of times (the add-on item is converted, so it runs once)."""
    cfg = config(db)
    start = int(cfg.get("standalone_from_order") or 0)
    done = []
    rows = db.scalars(select(ShopifyOrder).where(ShopifyOrder.status.in_(["imported", "needs_review"]),
                                                 ShopifyOrder.cancelled.is_(False), ShopifyOrder.raw.is_not(None)))
    for row in list(rows):
        if _order_number(row.name) < start:
            continue
        o = _from_raw_order(row.raw)
        before = len(done)
        items = list(db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id)))
        folded = [i for i in items if i.kind == "addon"]
        for li in o["lines"]:
            rule = standalone_rule(li, cfg)
            item = next((i for i in folded if i.line_item_id == li["id"]), None)
            if not rule or item is None:
                continue
            target = (_prop(li["props"], cfg["addon_keys"]) or "").strip()
            wells = [i for i in items if i.kind == "well" and i.project_id]
            parent_items = [i for i in wells if (i.title or "").strip() == target] or wells
            if not parent_items:
                continue
            parent_line = next((p for p in o["lines"] if p["id"] == parent_items[0].line_item_id), None)
            if parent_line is None:
                continue
            net = _net(li)
            for u in range(1, li["quantity"] + 1):
                pi = parent_items[(u - 1) % len(parent_items)]
                well = db.get(Project, pi.project_id)
                parent = {"kind": "well", "line": parent_line, "unit": pi.unit, "amount": well.sale_amount,
                          "extras": [], "created_project": well}
                x = {"kind": rule["kind"], "line": li, "unit": u, "amount": net, "extras": [], "parent": parent, "rule": rule}
                if u == 1:
                    db.delete(item)  # the folded add-on row becomes unit 1 of the new sacrifice
                    db.flush()
                label = _create_unit(db, row, o, x, cfg, paid=True)
                # only the price moves to the sacrifice; the sheep stays in the well's add-ons (linked)
                psvc.update_project(db, well, {"sale_amount": (well.sale_amount or Decimal(0)) - net},
                                    actor=None, source="shopify")
                pi.amount = (pi.amount or Decimal(0)) - net
                done.append(f"{row.name}: {label} (well {well.well_id} -{net})")
        if len(done) > before:
            audit(db, "shopify.addon_split", "shopify_order", row.name, actor_label="Shopify", after={"done": done[before:]})
    return done


def import_missing_suqya(db: Session) -> list[str]:
    """Orders seen before سقيا became its own project type (27 Nov 2026): make the سقيا projects they are missing.
    A water line recorded as "other" is linked to its new سقيا; one folded into a well/sacrifice as an add-on
    moves its price from that project to the سقيا and leaves its extras. Cancelled orders are never touched.
    Safe to run any number of times (each line unit is created once)."""
    cfg = config(db)
    done = []
    rows = db.scalars(select(ShopifyOrder).where(ShopifyOrder.cancelled.is_(False), ShopifyOrder.raw.is_not(None))
                      .order_by(ShopifyOrder.created_at_shop))
    for row in list(rows):
        raw = row.raw or {}
        if not any(is_suqya({"title": li.get("title") or "", "variant_title": li.get("variant_title")}, cfg)
                   for li in raw.get("lines") or []):
            continue
        if (row.financial_status or "") in {"refunded", "voided"} or row.status in {"cancelled", "waiting_payment", "new"}:
            continue
        o = _from_raw_order(raw)
        items = list(db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id)))
        before = len(done)
        for li in o["lines"]:
            if not is_suqya(li, cfg):
                continue
            mine = [i for i in items if i.line_item_id == li["id"]]
            if any(i.suqya_id for i in mine):
                continue
            target = (_prop(li["props"], cfg["addon_keys"]) or "").strip()
            parent = None
            for i in mine:
                if i.kind == "addon":  # folded into a project: take its price back from that project
                    net = i.amount or Decimal(0)
                    owners = [x for x in items if x.kind in ("well", "sacrifice") and (x.project_id or x.sacrifice_id)]
                    owner = next((x for x in owners if (x.title or "").strip() == target), owners[0] if owners else None)
                    if owner is not None:
                        rec = db.get(Project, owner.project_id) if owner.project_id else db.get(Sacrifice, owner.sacrifice_id)
                        kept = [e for e in addons.split(rec.extras) if not e.startswith(li["title"])]
                        if owner.project_id:
                            psvc.update_project(db, rec, {"sale_amount": (rec.sale_amount or Decimal(0)) - net,
                                                          "extras": addons.join(kept)}, actor=None, source="shopify")
                        else:
                            fin.update_sacrifice(db, rec, {"sale_price": (rec.sale_price or Decimal(0)) - net,
                                                           "extras": addons.join(kept)}, actor=None, source="shopify")
                        owner.amount = (owner.amount or Decimal(0)) - net
                        p_line = next((p for p in o["lines"] if p["id"] == owner.line_item_id), None)
                        if p_line is not None:
                            parent = {"kind": owner.kind, "line": p_line, "unit": owner.unit, "amount": owner.amount, "extras": []}
                db.delete(i)
            db.flush()
            if parent is None and target:
                p_line = next((p for p in o["lines"] if p["title"].strip() == target), None)
                if p_line is not None:
                    parent = {"kind": "well", "line": p_line, "unit": 1, "amount": Decimal(0), "extras": []}
            for u in range(1, li["quantity"] + 1):
                x = {"kind": "suqya", "line": li, "unit": u, "amount": _net(li), "extras": [], "parent": parent, "rule": {}}
                done.append(f"{row.name}: " + _create_unit(db, row, o, x, cfg, paid=True))
        if len(done) > before:
            if row.status in {"nothing_to_import", "needs_review"}:
                others = [i for i in db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id))
                          if i.kind == "other"]
                row.status = "needs_review" if others else "imported"
            row.message = "; ".join(filter(None, [row.message if row.status != "imported" else None,
                                                  "Created " + ", ".join(d.split(": ", 1)[1] for d in done[before:])]))
            audit(db, "shopify.suqya_backfill", "shopify_order", row.name, actor_label="Shopify", after={"done": done[before:]})
    return done


def repair_phone_countries(db: Session) -> int:
    """Local customer numbers saved without a country ("needs_country") get the customer's own
    country from their Shopify order (billing address country code), so WhatsApp links work.
    A country chosen by staff is never replaced. Returns how many numbers were completed."""
    from app.services import phones
    fixed = 0
    rows = db.scalars(select(ShopifyOrder).where(ShopifyOrder.raw.is_not(None)))
    for row in rows:
        code = (row.raw or {}).get("country_code")
        if not code:
            continue
        for item in db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id)):
            rec = db.get(Project, item.project_id) if item.project_id else db.get(Sacrifice, item.sacrifice_id) if item.sacrifice_id else None
            if rec is None or rec.customer_phone_status != "needs_country":
                continue
            hint = (row.raw or {}).get("phone")
            phones.apply(rec, hints=[hint], fallback_country=code)
            if rec.customer_phone_status == "valid":
                fixed += 1
                audit(db, "phone.country_from_shopify", "project" if isinstance(rec, Project) else "sacrifice",
                      getattr(rec, "well_id", None) or rec.sacrifice_no, actor_label="Shopify",
                      after={"country": rec.customer_phone_country, "e164": rec.customer_phone_e164})
    return fixed


def _from_raw_order(raw: dict) -> dict:
    o = dict(raw)
    o["lines"] = [{**li, "unit_price": Decimal(str(li["unit_price"])), "discount": Decimal(str(li.get("discount") or 0))}
                  for li in raw.get("lines") or []]
    return o


def _linked(db: Session, row: ShopifyOrder):
    items = list(db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id)))
    ps = [db.get(Project, i.project_id) for i in items if i.project_id]
    ss = [db.get(Sacrifice, i.sacrifice_id) for i in items if i.sacrifice_id]
    return ps, ss


def _linked_suqya(db: Session, row: ShopifyOrder) -> list[Suqya]:
    ids = db.scalars(select(ShopifyOrderItem.suqya_id).where(ShopifyOrderItem.order_id == row.id, ShopifyOrderItem.suqya_id.is_not(None)))
    return [db.get(Suqya, i) for i in ids]


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
    qs = _linked_suqya(db, row)
    for q in qs:
        q.notes = ((q.notes or "") + "\n" + note).strip()
    row.status = "cancelled"
    row.message = note if (ps or ss or qs) else f"Cancelled/refunded in Shopify ({o['financial_status'] or 'cancelled'})"
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
        select coalesce(p.source_group, s.source_group, 'Unknown') src, count(*), coalesce(sum(i.amount), 0)
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


def orders_list(db: Session, *, q: str | None = None, status: str | None = None, page: int = 1, per_page: int = 50) -> dict:
    """«طلبات شوبيفاي» (Hayah, 27 Nov 2026): every order HAYAH has seen, like Shopify's own orders list.
    Only what Hayah keeps: order number, items, customer name, phone, country, selling price and source.
    No address, email or payment details are stored, so none can be shown."""
    stmt = select(ShopifyOrder)
    if status == "cancelled":
        stmt = stmt.where(ShopifyOrder.cancelled.is_(True))
    elif status == "open":
        stmt = stmt.where(ShopifyOrder.cancelled.is_(False))
    elif status == "review":
        stmt = stmt.where(ShopifyOrder.status.in_(["needs_review", "not_in_workbook", "check", "waiting_payment"]))
    if q and q.strip():
        t = q.strip()
        like = f"%{t}%"
        stmt = stmt.where(ShopifyOrder.name.ilike(f"%{t.lstrip('#')}%") | ShopifyOrder.customer_name.ilike(like)
                          | func.cast(ShopifyOrder.raw, Text).ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.order_by(ShopifyOrder.created_at_shop.desc().nulls_last(), ShopifyOrder.id.desc())
                           .offset((page - 1) * per_page).limit(per_page)))
    cfg = config(db)
    ids = [r.id for r in rows]
    links: dict[int, dict] = {i: {"wells": [], "sacrifices": [], "suqya": []} for i in ids}
    if ids:
        for oid, line_id, unit, w, sno, qno in db.execute(
                select(ShopifyOrderItem.order_id, ShopifyOrderItem.line_item_id, ShopifyOrderItem.unit, Project.well_id,
                       Sacrifice.sacrifice_no, Suqya.suqya_no)
                .outerjoin(Project, Project.id == ShopifyOrderItem.project_id)
                .outerjoin(Sacrifice, Sacrifice.id == ShopifyOrderItem.sacrifice_id)
                .outerjoin(Suqya, Suqya.id == ShopifyOrderItem.suqya_id)
                .where(ShopifyOrderItem.order_id.in_(ids))).all():
            for key, v in (("wells", w), ("sacrifices", sno), ("suqya", qno)):
                if v:
                    links[oid][key].append({"no": v, "line": line_id, "unit": unit})
    mapped = {k.lower() for k in cfg["phone_keys"]}
    out = []
    for r in rows:
        raw = r.raw or {}
        lines = raw.get("lines") or []
        phone = raw.get("phone")
        for li in lines:
            phone = phone or _prop(li.get("props") or {}, cfg["phone_keys"])
        try:
            src = sales_source({"attrs": raw.get("attrs") or {}, "referrer": raw.get("referrer")}) if raw else None
        except Exception:  # an old copy without these fields
            src = None
        items = []
        for li in lines:
            kind = classify({"title": li.get("title") or "", "variant_title": li.get("variant_title"),
                             "props": li.get("props") or {}}, cfg)
            items.append({"id": li.get("id"), "title": li.get("title"), "variant": li.get("variant_title"),
                          "quantity": li.get("quantity"), "price": float(Decimal(str(li.get("unit_price") or 0))),
                          "discount": float(Decimal(str(li.get("discount") or 0))), "kind": kind,
                          "props": {k: v for k, v in (li.get("props") or {}).items() if not k.startswith("_") and k.lower() not in mapped}})
        out.append({"id": r.id, "name": r.name, "created_at": r.created_at_shop, "financial_status": r.financial_status,
                    "cancelled": r.cancelled, "total": float(r.total or 0), "currency": r.currency,
                    "customer_name": r.customer_name, "phone": phone, "country_code": raw.get("country_code"),
                    "source": src, "status": r.status, "message": r.message, "note": raw.get("note"),
                    "items": items, "links": links[r.id]})
    return {"orders": out, "total": total, "page": page, "per_page": per_page}


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

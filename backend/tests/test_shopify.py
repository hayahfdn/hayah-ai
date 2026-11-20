"""Shopify orders become wells and sacrifices: once, with the right fields, visible in reports."""
import base64
import hashlib
import hmac
import json

import httpx
import pytest

from tests.conftest import login

SECRET = "test-client-secret-0123456789"


def sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()


def order(oid=5001, name="#2001", lines=None, status="paid", cancelled=None, **kw):
    return {"id": oid, "name": name, "created_at": "2026-11-18T10:08:45+02:00", "financial_status": status,
            "cancelled_at": cancelled, "total_price": "0", "currency": "USD", "note": None,
            "note_attributes": [{"name": "utm_source", "value": "ig"}],
            "customer": {"first_name": "Test", "last_name": "Donor"}, "billing_address": {"name": "Test Donor"},
            "line_items": lines or [], **kw}


def line(lid, title, price, qty=1, props=None, variant=None):
    return {"id": lid, "title": title, "variant_title": variant, "quantity": qty, "price": str(price),
            "discount_allocations": [], "properties": [{"name": k, "value": v} for k, v in (props or {}).items()]}


@pytest.fixture
def shop(client, seeded):
    admin = login(client, "admin@hayah.local")
    r = client.put("/api/shopify/settings", headers=admin, json={
        "store_domain": "https://admin.shopify.com/store/hayah-test", "client_id": "cid123",
        "client_secret": SECRET, "enabled": True, "import_from": "2026-11-01", "well_id_start": 1400, "sacrifice_no_start": 300})
    assert r.status_code == 200, r.text
    assert r.json()["store_domain"] == "hayah-test.myshopify.com"
    assert r.json()["client_secret"]["set"] and SECRET not in r.text
    return admin


def post_webhook(client, payload, topic="orders/create", wid="w1", sig=None):
    body = json.dumps(payload).encode()
    return client.post("/api/shopify/webhook", content=body, headers={
        "X-Shopify-Hmac-Sha256": sig or sign(body), "X-Shopify-Topic": topic, "X-Shopify-Webhook-Id": wid,
        "X-Shopify-Shop-Domain": "hayah-test.myshopify.com", "Content-Type": "application/json"})


def run_jobs():
    from app.db import SessionLocal
    from app.services.jobs import run_due_jobs
    db = SessionLocal()
    try:
        return run_due_jobs(db)
    finally:
        db.close()


WELL_ORDER = order(lines=[
    line(11, "بئر ارتوازي عميق", 899, props={"الإهداء": "صدقة جارية عن والدي", "رقم الهاتف (WhatsApp)": "+971 500000001"}),
    line(12, "خزان مياه إضافي", 89, props={"للمشروع": "بئر ارتوازي عميق"}),
    line(13, "خروف", 99, props={"للمشروع": "بئر ارتوازي عميق"}),
])


def test_webhook_creates_well_with_dedication_price_and_addons(client, shop):
    assert post_webhook(client, WELL_ORDER).status_code == 200
    assert run_jobs()["failed"] == 0
    w = client.get("/api/projects/1400", headers=shop).json()
    assert w["customer_name"] == "Test Donor"
    assert w["dedication"] == "صدقة جارية عن والدي"
    assert w["sale_amount"] == "988.00"  # 899 well + 89 tank; the 99 sheep is its own sacrifice
    assert "خروف" in (w["extras"] or "") and "sacrifice 300" in w["notes"]  # listed as an add-on, priced on the sacrifice
    sac = [s for s in client.get("/api/sacrifices", headers=login(client, "manager@hayah.local")).json() if s["shopify_order"] == "#2001"]
    assert len(sac) == 1 and sac[0]["sacrifice_no"] == 300 and sac[0]["sale_price"] == "99.00"
    assert sac[0]["dedication"] == "صدقة جارية عن والدي" and sac[0]["animal_type"] == "خروف" and sac[0]["intention"] == "صدقة"
    assert sac[0]["donor_name"] == "Test Donor" and sac[0]["customer_phone"] == "+971 500000001"
    assert w["well_type"] == "عميق" and w["shopify_order"] == "#2001"
    assert w["payment_status"] == "paid" and w["sales_source"] == "Shopify (Instagram)" and w["source_group"] == "Instagram"
    assert w["customer_phone"] == "+971 500000001" and w["order_date"] == "2026-11-18"
    assert "خزان مياه إضافي" in w["extras"] and w["cost"] is None
    orders = client.get("/api/shopify/orders", headers=shop).json()
    assert orders[0]["status"] == "imported" and orders[0]["well_ids"] == [1400]


def test_no_duplicates_from_repeated_webhooks_and_sync(client, shop):
    for wid, topic in [("w1", "orders/create"), ("w1", "orders/create"), ("w2", "orders/paid")]:
        assert post_webhook(client, WELL_ORDER, topic, wid).status_code == 200
    run_jobs()
    from app.db import SessionLocal
    from app.services import shopify as svc
    db = SessionLocal()
    svc.import_order(db, svc.normalize_rest(WELL_ORDER), source="sync")
    db.commit()
    db.close()
    items = client.get("/api/projects", headers=shop, params={"q": "Test Donor"}).json()["items"]
    assert len(items) == 1


def test_sacrifices_one_per_unit_with_intention(client, shop):
    o = order(oid=5002, name="#2002", lines=[
        line(21, "خروف", 160, qty=2, props={"الإهداء": "فاعل خير", "الغرض": "عقيقة", "_service_page": "aqiqah"}),
        line(22, "إطعام", 36, qty=2, variant="خروف", props={"للمشروع": "خروف"})])
    post_webhook(client, o, wid="s1")
    run_jobs()
    mgr = login(client, "manager@hayah.local")
    sac = [s for s in client.get("/api/sacrifices", headers=mgr).json() if s["shopify_order"] == "#2002"]
    assert sorted(s["sacrifice_no"] for s in sac) == [300, 301]
    for s in sac:
        assert s["animal_type"] == "خروف" and s["intention"] == "عقيقة" and s["dedication"] == "فاعل خير"
        assert s["sale_price"] == "196.00" and "إطعام" in s["extras"]
        assert "_service_page" not in (s["notes"] or "")


def test_order_already_in_workbook_is_linked_not_recreated(client, shop):
    r = client.post("/api/projects", headers=shop, json={"well_id": 1350, "customer_name": "typed by hand",
                                                          "shopify_order": "2003", "sale_amount": "240.00"})
    assert r.status_code == 201
    post_webhook(client, order(oid=5003, name="#2003", lines=[line(31, "بئر سطحي بمضخة يدوية", 240)]), wid="x3")
    run_jobs()
    o = client.get("/api/shopify/orders", headers=shop).json()[0]
    assert o["status"] == "already_in_workbook" and o["well_ids"] == [1350]
    assert client.get("/api/projects/1400", headers=shop).status_code == 404


def test_unpaid_waits_then_imports_when_paid(client, shop):
    o = order(oid=5004, name="#2004", status="pending", lines=[line(41, "بئر سطحي بمضخة يدوية", 240)])
    post_webhook(client, o, wid="p1")
    run_jobs()
    assert client.get("/api/shopify/orders", headers=shop).json()[0]["status"] == "waiting_payment"
    post_webhook(client, {**o, "financial_status": "paid"}, topic="orders/paid", wid="p2")
    run_jobs()
    w = client.get("/api/projects/1400", headers=shop).json()
    assert w["well_type"] == "يدوي" and w["sale_amount"] == "240.00"


def test_cancel_marks_records_never_deletes(client, shop):
    post_webhook(client, WELL_ORDER, wid="c1")
    run_jobs()
    post_webhook(client, {**WELL_ORDER, "cancelled_at": "2026-11-19T10:00:00+02:00", "financial_status": "refunded"},
                 topic="orders/cancelled", wid="c2")
    run_jobs()
    w = client.get("/api/projects/1400", headers=shop).json()
    assert w["payment_status"] == "refunded" and "cancelled" in w["notes"]


def test_bad_signature_and_disabled(client, shop):
    assert post_webhook(client, WELL_ORDER, sig="nope").status_code == 401
    client.put("/api/shopify/settings", headers=shop, json={"enabled": False})
    assert post_webhook(client, WELL_ORDER).json() == {"ignored": "disabled"}


def test_only_admin_changes_settings_and_contractors_see_no_sales(client, shop):
    mgr, staff, p1 = (login(client, e) for e in ("manager@hayah.local", "staff@hayah.local", "p1@hayah.local"))
    assert client.put("/api/shopify/settings", headers=mgr, json={"enabled": False}).status_code == 403
    assert client.get("/api/shopify/settings", headers=staff).status_code == 403
    assert client.get("/api/shopify/summary", headers=staff).status_code == 200
    assert client.get("/api/shopify/summary", headers=p1).status_code == 403
    assert client.get("/api/shopify/orders", headers=p1).status_code == 403


def test_summary_counts_sales_by_month(client, shop):
    post_webhook(client, WELL_ORDER, wid="r1")
    run_jobs()
    s = client.get("/api/shopify/summary", headers=shop, params={"start": "2026-01-01", "end": "2026-12-31"}).json()
    assert s["orders"] == 1 and s["by_month"][0]["wells"] == 1 and s["by_month"][0]["wells_amount"] == 988.0
    assert s["by_month"][0]["sacrifices"] == 1 and s["by_month"][0]["sacrifices_amount"] == 99.0
    assert s["by_source"][0]["source"] == "Instagram"


def test_sync_uses_client_credentials_and_graphql(client, shop):
    from app.integrations import shopify as api
    calls = []

    def handle(req: httpx.Request):
        calls.append(str(req.url))
        if req.url.path == "/admin/oauth/access_token":
            assert b"grant_type=client_credentials" in req.content
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 86399})
        assert req.headers["X-Shopify-Access-Token"] == "tok-1"
        q = json.loads(req.content)["query"]
        if "shop {" in q:
            return httpx.Response(200, json={"data": {"shop": {"name": "Hayah", "myshopifyDomain": "hayah-test.myshopify.com",
                                                                 "ianaTimezone": "Asia/Dubai", "currencyCode": "USD"}}})
        node = {"id": "gid://shopify/Order/6001", "name": "#2100", "createdAt": "2026-11-18T22:30:00Z",
                "displayFinancialStatus": "PAID", "cancelledAt": None, "note": None, "phone": None, "email": None,
                "customAttributes": [{"key": "referrer", "value": "https://www.google.com/"}],
                "currentTotalPriceSet": {"shopMoney": {"amount": "120.0", "currencyCode": "USD"}},
                "customer": {"firstName": "Sync", "lastName": "Donor", "defaultPhoneNumber": None},
                "billingAddress": None,
                "lineItems": {"nodes": [{"id": "gid://shopify/LineItem/77", "title": "ماعز", "variantTitle": None, "quantity": 1,
                                         "customAttributes": [{"key": "الإهداء", "value": "عن روح جدي"}],
                                         "originalUnitPriceSet": {"shopMoney": {"amount": "120.0"}},
                                         "discountAllocations": []}]}}
        return httpx.Response(200, json={"data": {"orders": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                                             "nodes": [node]}}})

    api.set_transport(httpx.MockTransport(handle))
    try:
        assert client.post("/api/shopify/test", headers=shop).json()["shop"]["name"] == "Hayah"
        r = client.post("/api/shopify/sync", headers=shop).json()
        assert r["created_sacrifices"] == 1, r
        assert client.post("/api/shopify/sync", headers=shop).json()["created_sacrifices"] == 0
    finally:
        api.set_transport(None)
    mgr = login(client, "manager@hayah.local")
    s = [x for x in client.get("/api/sacrifices", headers=mgr).json() if x["shopify_order"] == "#2100"][0]
    assert s["order_date"] == "2026-11-19"  # shop time zone (Dubai), not UTC
    assert s["sales_source"] == "Shopify (Google)" and s["dedication"] == "عن روح جدي"
    assert sum("access_token" in c for c in calls) == 1  # token reused, not fetched every call


def test_domain_rules():
    from app.integrations.shopify import ShopifyError, normalize_domain
    assert normalize_domain("abc-1") == "abc-1.myshopify.com"
    assert normalize_domain("https://abc.myshopify.com/admin") == "abc.myshopify.com"
    with pytest.raises(ShopifyError):
        normalize_domain("checkout.hayahfoundation.com")


def test_enabling_without_a_date_starts_from_today(client, seeded):
    from datetime import date
    admin = login(client, "admin@hayah.local")
    r = client.put("/api/shopify/settings", headers=admin, json={"store_domain": "x-1", "enabled": True}).json()
    assert r["import_from"] == date.today().isoformat()


def test_shopify_errors_are_readable():
    from app.integrations.shopify import explain_oauth_error
    html = '<!DOCTYPE html><html><head><title>400 - Oauth error app_not_installed</title><style>*{}</style>'
    msg = explain_oauth_error(400, html)
    assert "not installed" in msg and "<" not in msg
    assert "<" not in explain_oauth_error(500, "<html><title>Oops</title></html>")


def test_webhook_queues_only_the_fields_hayah_uses(client, shop):
    """Order number, items, name, phone, country (line property) and price; no address, email or payment details."""
    payload = {**WELL_ORDER, "id": 5099, "name": "#2099", "email": "donor@example.com",
               "billing_address": {"name": "Test Donor", "phone": "+971 1", "address1": "Street 1", "city": "Dubai"},
               "shipping_address": {"address1": "Street 1"}, "payment_gateway_names": ["visa"],
               "customer": {"first_name": "Test", "last_name": "Donor", "email": "donor@example.com",
                            "default_address": {"address1": "Street 1"}}}
    assert post_webhook(client, payload, wid="slim").status_code == 200
    from app.db import SessionLocal
    from app.models import Job
    db = SessionLocal()
    job = db.query(Job).filter(Job.kind == "shopify_order").order_by(Job.id.desc()).first()
    text = json.dumps(job.payload, ensure_ascii=False)
    db.close()
    for banned in ("donor@example.com", "Street 1", "Dubai", "visa", "shipping_address"):
        assert banned not in text
    assert "#2099" in text and "Test Donor" in text and "الإهداء" in text
    assert run_jobs()["failed"] == 0

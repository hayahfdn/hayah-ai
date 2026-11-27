"""Shopify orders show in the system the moment they happen: the webhook imports the order straight
away (no waiting for the worker), orders/updated is subscribed, missing webhooks are re-added by the
scheduled sync, and pages can poll a small «live» status that changes when an order arrives."""
import time

from tests.conftest import login
from tests.test_shopify import WELL_ORDER, order, post_webhook, shop  # noqa: F401  (fixture)


def test_webhook_imports_order_instantly_without_worker(client, shop):
    staff = login(client, "staff@hayah.local")
    before = client.get("/api/shopify/live", headers=staff).json()
    assert post_webhook(client, WELL_ORDER, wid="live1").status_code == 200
    # no run_jobs(): the order is already in the list
    rows = client.get("/api/shopify/orders/list", headers=staff).json()["orders"]
    assert [r["name"] for r in rows] == ["#2001"]
    assert rows[0]["links"]["wells"], "the well was made straight away"
    after = client.get("/api/shopify/live", headers=staff).json()
    assert after["orders_version"] != before["orders_version"] and after["last_webhook_at"]


def test_order_updates_follow_shopify(client, shop):
    staff = login(client, "staff@hayah.local")
    o = order(oid=7001, name="#3001", status="pending", lines=[])
    post_webhook(client, o, wid="u1")
    post_webhook(client, {**o, "financial_status": "paid", "note": "edited"}, topic="orders/updated", wid="u2")
    row = client.get("/api/shopify/orders/list", headers=staff).json()["orders"][0]
    assert row["financial_status"] == "paid" and row["note"] == "edited"


def test_live_status_is_for_staff_only(client, shop):
    assert client.get("/api/shopify/live").status_code == 401
    r = client.get("/api/shopify/live", headers=shop).json()
    assert set(r) >= {"orders_version", "suqya_version", "instant", "last_sync_at"} and r["instant"] is False


def test_scheduled_sync_re_adds_missing_webhooks(db, shop, monkeypatch):
    from app.services import shopify as svc
    calls = []

    def fake_gql(_db, query, variables=None):
        if "webhookSubscriptions" in query:
            return {"webhookSubscriptions": {"nodes": [
                {"id": "1", "topic": t, "uri": "https://hayah.example/api/shopify/webhook"}
                for t in ("ORDERS_CREATE", "ORDERS_PAID", "ORDERS_CANCELLED")]}}
        calls.append(variables["topic"])
        return {"webhookSubscriptionCreate": {"webhookSubscription": {"id": "2", "topic": variables["topic"]}, "userErrors": []}}

    monkeypatch.setattr(svc, "gql", fake_gql)
    assert svc.ensure_webhooks(db) is None  # never connected by the admin: nothing to keep up
    svc._state(db, webhooks={"uri": "https://hayah.example/api/shopify/webhook", "active": ["ORDERS_CREATE"]})
    r = svc.ensure_webhooks(db)
    assert calls == ["ORDERS_UPDATED"] and set(r["active"]) == set(svc.TOPICS)
    assert svc.ensure_webhooks(db) is None  # checked again only after a few hours
    svc._state(db, webhooks_checked_at=time.time() - svc.RECHECK_HOOKS_S - 1)
    assert svc.ensure_webhooks(db) is not None
    db.commit()
    assert svc.live_status(db)["instant"] is True

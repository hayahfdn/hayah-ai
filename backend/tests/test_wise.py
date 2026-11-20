"""Wise, read only: no duplicates on re-sync, classification, auto match, unmatched list, record once."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import AuditLog, FinanceAccount, Transaction, TxKind, WiseTransaction
from app.services import wise
from tests.conftest import login

NOW = datetime.now(timezone.utc)


def act(i, title, amount, *, typ="TRANSFER", desc="", days=1, secondary=None, status="COMPLETED"):
    return {"id": f"ACT-{i}", "type": typ, "title": f"<strong>{title}</strong>", "description": desc, "status": status,
            "primaryAmount": amount, "secondaryAmount": secondary, "createdOn": (NOW - timedelta(days=days)).isoformat(),
            "resource": {"type": typ, "id": str(1000 + i)}}


FEED = [
    act(1, "SHOPIFY", "<positive>+ 2,570.38 USD</positive>", desc="Received"),
    act(2, "Ghaidaa sabbah", "248 GBP", desc="Sent", secondary="328.08 USD"),
    act(3, "Hetzner", "25 USD", typ="CARD_PAYMENT"),
    act(4, "Facebk *ads", "40 USD", typ="CARD_PAYMENT"),
    act(5, "USD to GBP", "100 USD", typ="CONVERSION"),
    act(6, "Someone", "10 USD", status="CANCELLED"),
]


@pytest.fixture
def connected(db, monkeypatch):
    from app.services.secrets_store import set_secret
    from app.services.settings_store import set_setting
    set_secret(db, wise.SECRET, "read-only-token", None)
    set_setting(db, wise.SETTING, {"profile_id": 89358383, "profile_name": "Hayah Foundation LLC"})
    db.commit()
    calls = []
    monkeypatch.setattr(wise, "fetch_activities", lambda token, pid, since: calls.append(pid) or FEED)
    return calls


def test_parse_amounts():
    assert wise.parse_amount("<positive>+ 2,570.38 USD</positive>") == ("+", Decimal("2570.38"), "USD")
    assert wise.parse_amount("248 GBP") == (None, Decimal("248"), "GBP")
    assert wise.parse_amount(None) == (None, None, None)


def test_sync_twice_stores_once_and_classifies(client, manager, db, connected):
    r1 = client.post("/api/wise/sync", headers=manager).json()
    r2 = client.post("/api/wise/sync", headers=manager).json()
    assert r1["new"] == 5 and r2["new"] == 0  # cancelled skipped, nothing duplicated
    rows = {w.wise_id: w for w in db.query(WiseTransaction)}
    assert len(rows) == 5
    assert (rows["ACT-1"].direction, rows["ACT-1"].category, rows["ACT-1"].usd_amount) == ("in", "shopify_payout", Decimal("2570.38"))
    assert (rows["ACT-2"].direction, rows["ACT-2"].category, rows["ACT-2"].usd_amount) == ("out", "transfer_out", Decimal("328.08"))
    assert rows["ACT-3"].category == "tools" and rows["ACT-4"].category == "ads"
    assert rows["ACT-5"].match_status == "ignored"  # between own balances


def test_auto_match_and_recipient_mapping(client, manager, db, connected):
    acc = db.query(FinanceAccount).filter(FinanceAccount.code == "WISE").one()
    t = Transaction(date=(NOW - timedelta(days=2)).date(), kind=TxKind.income, direction="in", account_id=acc.id,
                    amount=Decimal("2570.38"), currency="USD", description="Shopify payout")
    db.add(t); db.commit()
    assert client.put("/api/wise/recipients", headers=manager, json={"recipient_contractors": {"Ghaidaa Sabbah": "PAK1"}}).status_code == 200
    client.post("/api/wise/sync", headers=manager)
    db.expire_all()
    payout = db.query(WiseTransaction).filter_by(wise_id="ACT-1").one()
    assert payout.match_status == "matched" and payout.transaction_id == t.id
    gh = db.query(WiseTransaction).filter_by(wise_id="ACT-2").one()
    assert gh.category == "contractor" and gh.contractor.code == "PAK1"
    unmatched = client.get("/api/wise/transactions", headers=manager).json()
    assert "ACT-1" not in [u["counterparty"] for u in unmatched] and len(unmatched) == 3


def test_record_once_and_ignore(client, manager, db, connected):
    client.post("/api/wise/sync", headers=manager)
    w = db.query(WiseTransaction).filter_by(wise_id="ACT-3").one()
    r = client.post(f"/api/wise/transactions/{w.id}/record", headers=manager, json={})
    assert r.status_code == 200
    t = db.get(Transaction, r.json()["transaction_id"])
    assert (t.kind, t.direction, t.amount) == (TxKind.operating_expense, "out", Decimal("25.00"))
    assert client.post(f"/api/wise/transactions/{w.id}/record", headers=manager, json={}).status_code == 409
    other = db.query(WiseTransaction).filter_by(wise_id="ACT-4").one()
    assert client.post(f"/api/wise/transactions/{other.id}/ignore", headers=manager).status_code == 200
    db.expire_all()
    assert db.get(WiseTransaction, other.id).match_status == "ignored"


def test_staff_and_token_rules(client, manager, db, seeded):
    staff = login(client, "staff@hayah.local")
    assert client.get("/api/wise/status", headers=staff).status_code == 403
    assert client.put("/api/wise/token", headers=manager, json={"token": "x"}).status_code == 403  # super admin only
    st = client.get("/api/wise/status", headers=manager).json()
    assert st["token"]["set"] is False and "token" not in str(st["token"].get("last4") or "")
    assert client.post("/api/wise/sync", headers=manager).status_code == 422


def test_no_write_requests_to_wise():
    """The client only ever uses GET."""
    import inspect
    src = inspect.getsource(wise)
    assert "httpx.post" not in src and "httpx.put" not in src and "httpx.delete" not in src and ".request(" not in src

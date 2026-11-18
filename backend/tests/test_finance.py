from datetime import date

from tests.conftest import login


def test_workbook_tabs_have_requested_pages(client, manager):
    wb = client.get("/api/finance/workbook", headers=manager).json()
    codes = {c["code"] for c in wb["contractors"]}
    assert {"PAK1", "PAK2", "PAK3", "PAK4", "PAK5", "NEP1", "NEP2", "NEP3", "BANG1", "TZ1"} <= codes
    assert [a["code"] for a in wb["accounts"]] == ["WISE", "MOHAMMED", "GHAZI", "CLIQ"]
    assert date.today().strftime("%Y-%m") in wb["months"]["wells"]
    assert wb["months"]["sacrifices"]


def test_finance_is_managers_only(client, seeded):
    for email in ("p1@hayah.local", "viewer@hayah.local", "maint@hayah.local"):
        h = login(client, email)
        assert client.get("/api/finance/summary", headers=h).status_code == 403
        assert client.get("/api/sacrifices", headers=h).status_code == 403


def test_contractor_ledger_invoiced_paid_owed(client, manager):
    led = client.get("/api/finance/contractors/PAK1/ledger", headers=manager).json()
    # PAK1 sample wells: 9001 (متوسط 420), 9002 (يدوي 170), 9010 (متوسط 420); one sample payment of 900
    assert {w["well_id"] for w in led["wells"]} == {9001, 9002, 9010}
    assert led["totals"]["invoiced"] == 1010.0
    assert led["totals"]["paid"] == 900.0
    assert led["totals"]["owed"] == 110.0
    tz = client.get("/api/finance/contractors/TZ1/ledger", headers=manager).json()
    assert len(tz["sacrifices"]) == 14 and tz["totals"]["sacrifices"] == 14


def test_partner_and_bank_balances(client, manager):
    mo = client.get("/api/finance/accounts/MOHAMMED/ledger", headers=manager).json()["totals"]
    assert mo["took_from_company"] == 500 and mo["spent_on_company"] == 320 and mo["still_with_partner"] == 180
    wise = client.get("/api/finance/accounts/wise/ledger", headers=manager).json()
    ins = 6200 + 2900
    outs = 900 + 600 + 1200 + 400 + 380 + 220 + 300 + 79 + 600
    assert wise["totals"]["balance"] == ins - outs
    assert wise["transactions"][-1]["balance"] == ins - outs  # running balance column


def test_summary_numbers_add_up(client, manager):
    s = client.get("/api/finance/summary", headers=manager).json()
    h = s["headline"]
    assert h["wells"] == 12 and h["sacrifices"] == 14
    assert round(h["gross_profit"], 2) == round(h["total_sales"] - h["cost"], 2)
    assert h["ad_spend"] == 900 and h["operating_expenses"] == 679
    assert round(sum(m["pure_profit"] for m in s["by_month"]), 2) == round(h["pure_profit"], 2)
    assert {"Facebook", "Google", "Neutrons"} == {r["channel"] for r in s["ads_by_channel"]}
    assert s["has_samples"] is True
    real = client.get("/api/finance/summary", params={"include_samples": False}, headers=manager).json()
    assert real["headline"]["total_sales"] == 0


def test_transaction_void_not_delete_and_audited(client, manager, db):
    from app.models import AuditLog
    acc = client.get("/api/finance/accounts", headers=manager).json()
    wise = next(a for a in acc if a["code"] == "WISE")
    r = client.post("/api/finance/transactions", headers=manager, json={
        "date": "2026-11-10", "kind": "ad_spend", "account_id": wise["id"], "channel": "Instagram", "amount": "55.50"})
    assert r.status_code == 201 and r.json()["direction"] == "out"
    tid = r.json()["id"]
    r = client.patch(f"/api/finance/transactions/{tid}", headers=manager, json={"amount": "60", "expected_version": 1})
    assert r.status_code == 200 and r.json()["amount"] == "60.00"
    assert client.patch(f"/api/finance/transactions/{tid}", headers=manager, json={"amount": "61", "expected_version": 1}).status_code == 409
    assert client.post(f"/api/finance/transactions/{tid}/void", headers=manager, json={"reason": "typo"}).json()["voided"]
    assert client.patch(f"/api/finance/transactions/{tid}", headers=manager, json={"amount": "1"}).status_code == 409
    assert db.query(AuditLog).filter(AuditLog.entity_type == "transaction", AuditLog.entity_id == str(tid)).count() == 3
    bad = client.post("/api/finance/transactions", headers=manager, json={"date": "2026-11-10", "kind": "contractor_payment", "amount": "10"})
    assert bad.status_code == 422


def test_sacrifices_by_month_and_edit(client, manager):
    month = date.today().strftime("%Y-%m")
    rows = client.get("/api/sacrifices", params={"month": month}, headers=manager).json()
    assert rows and all(r["order_date"].startswith(month) for r in rows)
    r = client.post("/api/sacrifices", headers=manager, json={"sacrifice_no": 3088, "order_date": f"{month}-02",
                                                               "animal_type": "خروف", "cost": "120", "sale_price": "199"})
    assert r.status_code == 201
    assert client.post("/api/sacrifices", headers=manager, json={"sacrifice_no": 3088}).status_code == 409
    r = client.patch("/api/sacrifices/3088", headers=manager, json={"donor_name": "أم علي", "expected_version": 1})
    assert r.status_code == 200 and r.json()["version"] == 2
    assert client.get("/api/sacrifices/next-number", headers=manager).json()["suggested_next"] == 3089


def test_wells_month_filter_and_new_fields(client, manager):
    month = date.today().strftime("%Y-%m")
    items = client.get("/api/projects", params={"month": month, "page_size": 500}, headers=manager).json()["items"]
    assert all(p["order_date"].startswith(month) for p in items)
    p = client.get("/api/projects/9004", headers=manager).json()
    r = client.patch("/api/projects/9004", headers=manager, json={"cost": "175.00", "extras": "خزان",
                                                                  "expected_version": p["version"]})
    assert r.status_code == 200 and r.json()["cost"] == "175.00" and r.json()["extras"] == "خزان"


def test_direct_delivery_by_manager_only(client, manager, seeded):
    h = login(client, "p1@hayah.local")
    assert client.post("/api/finance/deliver/9002", headers=h, json={"delivery_date": "2026-11-12"}).status_code == 403
    r = client.post("/api/finance/deliver/9002", headers=manager, json={"delivery_date": "2026-11-12"})
    assert r.status_code == 200 and r.json()["delivery_status"] == "delivered" and r.json()["delivery_date"] == "2026-11-12"
    hist = client.get("/api/projects/9002/history", headers=manager).json()
    kinds = [e["event_type"] for e in (hist["events"] if isinstance(hist, dict) else hist)]
    assert "delivery_confirmed" in kinds

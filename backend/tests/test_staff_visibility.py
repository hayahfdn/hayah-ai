"""Team members (and every non-manager) never see well costs; they can add wells with a selling price."""
from tests.conftest import login


def test_staff_sees_sale_price_but_not_cost(client, seeded):
    mgr, staff = login(client, "manager@hayah.local"), login(client, "staff@hayah.local")
    assert client.patch("/api/projects/9001", headers=mgr, json={"cost": "123.00"}).status_code == 200
    for who in ("staff@hayah.local", "viewer@hayah.local", "maint@hayah.local"):
        h = login(client, who)
        one = client.get("/api/projects/9001", headers=h).json()
        assert one["cost"] is None
        assert all(p["cost"] is None for p in client.get("/api/projects", headers=h, params={"page_size": 100}).json()["items"])
        hist = client.get("/api/projects/9001/history", headers=h).json()["events"]
        assert "cost" not in str(hist)
    assert client.get("/api/projects/9001", headers=mgr).json()["cost"] == "123.00"


def test_staff_can_add_well_with_price_but_not_cost(client, seeded):
    staff = login(client, "staff@hayah.local")
    r = client.post("/api/projects", headers=staff, json={"well_id": 8001, "customer_name": "x", "sale_amount": "150.00"})
    assert r.status_code == 201, r.text
    assert r.json()["sale_amount"] == "150.00" and r.json()["cost"] is None
    assert client.patch("/api/projects/8001", headers=staff, json={"sale_amount": "160.00"}).status_code == 200
    assert client.patch("/api/projects/8001", headers=staff, json={"cost": "40.00"}).status_code == 403
    assert client.post("/api/projects", headers=staff, json={"well_id": 8002, "cost": "40.00"}).status_code == 403


def test_staff_blocked_from_finance(client, seeded):
    staff = login(client, "staff@hayah.local")
    for url in ("/api/finance/summary", "/api/projects/export.csv", "/api/audit"):
        assert client.get(url, headers=staff).status_code == 403, url
    rep = client.get("/api/reports/summary", headers=staff).json()
    assert all(r["cost"] is None for r in rep["maintenance_by_problem"])


def test_staff_sees_sacrifices_without_cost(client, seeded):
    """Employees (موظف) see and add sacrifices with every detail and the selling price, never cost or profit."""
    mgr, staff = login(client, "manager@hayah.local"), login(client, "staff@hayah.local")
    sac = client.get("/api/sacrifices", headers=mgr).json()
    assert sac and any(s["cost"] is not None for s in sac)
    no = next(s["sacrifice_no"] for s in sac if s["cost"] is not None)
    rows = client.get("/api/sacrifices", headers=staff).json()
    assert len(rows) == len(sac) and all(s["cost"] is None for s in rows)
    one = next(s for s in rows if s["sacrifice_no"] == no)
    assert one["donor_name"] is not None or one["dedication"] is not None or one["sale_price"] is not None
    assert client.get("/api/nav", headers=staff).json()["sacrifices"]
    assert client.get("/api/sacrifices/next-number", headers=staff).status_code == 200
    # edit operational details and selling price
    r = client.patch(f"/api/sacrifices/{no}", headers=staff, json={"donor_name": "أبو أحمد", "sale_price": "150.00", "shopify_order": "#1300"})
    assert r.status_code == 200, r.text
    assert r.json()["cost"] is None and r.json()["sale_price"] == "150.00"
    assert client.get("/api/sacrifices/orders/1300", headers=staff).status_code == 200
    # cost and delivery confirmation stay with managers
    assert client.patch(f"/api/sacrifices/{no}", headers=staff, json={"cost": "10.00"}).status_code == 403
    assert client.patch(f"/api/sacrifices/{no}", headers=staff, json={"delivery_date": "2026-11-01"}).status_code == 403
    assert client.post("/api/sacrifices", headers=staff, json={"donor_name": "x", "cost": "5.00"}).status_code == 403
    made = client.post("/api/sacrifices", headers=staff, json={"donor_name": "x", "sale_price": "99.00"})
    assert made.status_code == 201, made.text
    assert made.json()["cost"] is None
    bulk = client.post("/api/sacrifices/bulk", headers=staff, json={"donor_name": "y", "quantity": 2})
    assert bulk.status_code == 201 and all(s["cost"] is None for s in bulk.json())
    # renumbering and the finance workbook stay managers only
    assert client.patch(f"/api/sacrifices/{no}/number", headers=staff, json={"new_number": 999999}).status_code == 403
    assert client.post("/api/sacrifices/renumber/preview", headers=staff, json={}).status_code == 403
    assert client.get("/api/finance/workbook", headers=staff).status_code == 403
    assert next(s for s in client.get("/api/sacrifices", headers=mgr).json() if s["sacrifice_no"] == no)["cost"] is not None
    # contractors and viewers still see nothing
    for who in ("p1@hayah.local", "viewer@hayah.local"):
        assert client.get("/api/sacrifices", headers=login(client, who)).status_code == 403
        assert client.get("/api/nav", headers=login(client, who)).json()["sacrifices"] == []

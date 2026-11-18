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

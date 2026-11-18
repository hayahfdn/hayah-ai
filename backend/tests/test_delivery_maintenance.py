from datetime import date


def test_delivery_requires_manager_approval(client, manager, seeded):
    from tests.conftest import login
    p1 = login(client, "p1@hayah.local")
    r = client.post("/api/delivery", json={"well_id": 9010, "delivery_date": str(date.today())}, headers=p1)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert client.get("/api/projects/9010", headers=manager).json()["delivery_status"] == "pending"
    # contractor cannot approve
    assert client.post(f"/api/delivery/{r.json()['id']}/decision", json={"approve": True}, headers=p1).status_code == 403
    d = client.post(f"/api/delivery/{r.json()['id']}/decision", json={"approve": True, "note": "evidence ok"}, headers=manager)
    assert d.status_code == 200
    p = client.get("/api/projects/9010", headers=manager).json()
    assert p["delivery_status"] == "delivered" and p["delivery_date"] == str(date.today())
    # cannot decide twice
    assert client.post(f"/api/delivery/{r.json()['id']}/decision", json={"approve": True}, headers=manager).status_code == 409


def test_rejected_delivery_changes_nothing(client, manager):
    r = client.post("/api/delivery", json={"well_id": 9003, "delivery_date": "2026-11-01"}, headers=manager).json()
    client.post(f"/api/delivery/{r['id']}/decision", json={"approve": False, "note": "wrong photos"}, headers=manager)
    assert client.get("/api/projects/9003", headers=manager).json()["delivery_status"] == "not_ready"


def test_maintenance_ids_and_history_preserved(client, seeded):
    from tests.conftest import login
    h = login(client, "maint@hayah.local")
    a = client.post("/api/maintenance", json={"well_id": 9007, "date": "2026-11-10", "problem_type": "leak",
                                              "description": "تسرب في الأنبوب"}, headers=h).json()
    b = client.post("/api/maintenance", json={"well_id": 9007, "date": "2026-11-15", "problem_type": "pump_failure"},
                    headers=h).json()
    assert a["maintenance_code"] != b["maintenance_code"] and a["maintenance_code"].startswith("MNT-")
    u = client.patch(f"/api/maintenance/{a['maintenance_code']}", json={"status": "resolved", "repair_cost": "40.00"},
                     headers=h)
    assert u.status_code == 200
    # original report fields are immutable
    assert client.patch(f"/api/maintenance/{a['maintenance_code']}", json={"problem_type": "x"}, headers=h).status_code == 422
    recs = client.get("/api/maintenance", params={"well_id": 9007}, headers=h).json()
    assert len(recs) == 3  # seeded one + two new
    p = client.get("/api/projects/9007", headers=h).json()
    assert p["maintenance_status"] == "open" and p["last_maintenance_date"] == "2026-11-15"
    audit = client.get("/api/audit", params={"entity_type": "maintenance", "entity_id": a["maintenance_code"]},
                       headers=login(client, "admin@hayah.local")).json()
    assert {x["action"] for x in audit} == {"maintenance.create", "maintenance.update"}

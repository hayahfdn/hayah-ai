from app.models import AuditLog, ProjectEvent


def test_create_project_and_duplicate_well_id(client, manager, db):
    body = {"well_id": 1339, "country": "Pakistan", "well_type": "medium_artesian", "customer_name": "عائلة اختبار"}
    r = client.post("/api/projects", json=body, headers=manager)
    assert r.status_code == 201, r.text
    assert r.json()["delivery_status"] == "not_ready"
    assert client.post("/api/projects", json=body, headers=manager).status_code == 409
    assert db.query(AuditLog).filter_by(action="project.create", entity_id="1339").count() == 1


def test_invalid_input_rejected(client, manager):
    assert client.post("/api/projects", json={"well_id": -4}, headers=manager).status_code == 422
    assert client.post("/api/projects", json={"well_id": 77, "final_video_link": "javascript:alert(1)"},
                       headers=manager).status_code == 422
    assert client.patch("/api/projects/9003", json={"unknown_field": 1}, headers=manager).status_code == 422
    assert client.patch("/api/projects/9003", json={"final_video_link": "not-a-link"}, headers=manager).status_code == 422


def test_search_and_filters(client, manager):
    r = client.get("/api/projects", params={"country": "Pakistan"}, headers=manager).json()
    assert r["total"] == 6
    assert client.get("/api/projects", params={"q": "9007"}, headers=manager).json()["items"][0]["well_id"] == 9007
    assert client.get("/api/projects", params={"q": "النور"}, headers=manager).json()["total"] == 1


def test_construction_completion_does_not_mark_delivered(client, manager):
    r = client.patch("/api/projects/9003", json={"construction_status": "completed"}, headers=manager).json()
    assert r["construction_status"] == "completed"
    assert r["completion_date"] is not None
    assert r["delivery_status"] == "pending"  # waits for an approved confirmation


def test_delivery_fields_cannot_be_edited_directly(client, manager):
    r = client.patch("/api/projects/9003", json={"delivery_status": "delivered"}, headers=manager)
    assert r.status_code == 422


def test_final_video_does_not_mark_delivered(client, manager):
    r = client.patch("/api/projects/9003", json={"video_status": "completed",
                                                 "final_video_link": "https://drive.google.com/x"}, headers=manager).json()
    assert r["delivery_status"] != "delivered"


def test_optimistic_locking(client, manager):
    p = client.get("/api/projects/9004", headers=manager).json()
    assert client.patch("/api/projects/9004", json={"notes": "a", "expected_version": p["version"]}, headers=manager).status_code == 200
    r = client.patch("/api/projects/9004", json={"notes": "b", "expected_version": p["version"]}, headers=manager)
    assert r.status_code == 409


def test_history_contains_events_media_maintenance(client, manager):
    h = client.get("/api/projects/9001/history", headers=manager).json()
    types = {e["event_type"] for e in h["events"]}
    assert {"project_created", "construction_update", "delivery_confirmed", "maintenance_reported"} <= types
    assert len(h["media"]) == 1 and len(h["maintenance"]) == 1 and h["deliveries"][0]["status"] == "approved"


def test_merge_requires_approval_and_keeps_history(client, manager, db):
    r = client.post("/api/projects/merge-requests", headers=manager,
                    json={"source_well_id": 9012, "target_well_id": 9006, "reason": "duplicate entry"})
    assert r.status_code == 201
    assert client.get("/api/projects/9012", headers=manager).json()["merged_into_id"] is None
    r = client.post(f"/api/review/{r.json()['id']}/decision", json={"approve": True}, headers=manager)
    assert r.status_code == 200
    src = client.get("/api/projects/9012", headers=manager).json()
    assert src["merged_into_id"] is not None
    events = client.get("/api/projects/9006/history", headers=manager).json()["events"]
    assert any(e["event_type"] == "project_merged" for e in events)
    assert db.query(ProjectEvent).count() > 0  # nothing deleted


def test_well_id_check(client, manager):
    r = client.get("/api/projects/well-id-check/9001", headers=manager).json()
    assert r["exists"] and r["highest_existing"] == 9012 and r["suggested_next"] == 9013


def test_csv_export_utf8(client, manager):
    r = client.get("/api/projects/export.csv", headers=manager)
    assert r.status_code == 200 and "عائلة أحمد" in r.text and r.text.count("\n") == 13

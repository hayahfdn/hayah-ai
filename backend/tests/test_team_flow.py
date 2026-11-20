"""Team tasks (Hayah, 21 Nov 2026): Ghazi (intake) -> Shatha (customer & plaque) -> Ghaida (review & delivery)."""
from tests.conftest import login
from tests.test_final_video import _mp4, _up
from tests.test_plaque_flow import _save

MONEY = ("cost", "profit", "sale_amount", "price")


def _card(client, h, no):
    r = client.get(f"/api/team/order/{no}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _tick(client, h, no, step, done=True, note=None):
    return client.post(f"/api/team/order/{no}/steps/{step}", headers=h, json={"done": done, "note": note})


def test_order_moves_through_the_three_people(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    mgr = login(client, "manager@hayah.local")
    r = client.post("/api/projects", headers=staff, json={"well_id": 7301, "well_type": "يدوي", "customer_name": "أم محمد",
                                                          "dedication": "المرحوم محمد علي", "customer_phone": "+962791234567"})
    assert r.status_code == 201, r.text

    # 1. Ghazi: receive -> country -> contractor
    c = _card(client, staff, 7301)
    assert c["stage"] == "intake" and c["next_step"] == "received"
    assert any(x["well_id"] == 7301 for x in client.get("/api/team/tasks?stage=intake", headers=staff).json()["items"])
    assert _tick(client, staff, 7301, "received").json()["next_step"] == "country"
    con = client.get("/api/contractors", headers=staff).json()[0]
    assert client.patch("/api/projects/7301", headers=staff, json={"contractor_id": con["id"], "country": "Pakistan"}).status_code == 200
    c = _card(client, staff, 7301)
    assert c["stage"] == "customer" and c["next_step"] == "contacted"

    # 2. Shatha: contact -> design -> send -> approval (only after it was sent)
    assert _tick(client, staff, 7301, "contacted", note="اتصال هاتفي").json()["next_step"] == "designed"
    assert _save(client, staff, 7301, {"name": "المرحوم محمد علي"}).status_code == 201
    c = _card(client, staff, 7301)
    assert c["next_step"] == "sent"
    pid = c["plaque_id"]
    early = client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "customer_approved"})
    if c["plaque_status"] == "ready_for_review":
        assert early.status_code == 409 and "لم تُرسَل" in early.json()["detail"]
    assert client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "awaiting_customer"}).status_code == 200
    assert _card(client, staff, 7301)["next_step"] == "approved"
    assert client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "customer_approved", "note": "وافق على واتساب"}).status_code == 200
    c = _card(client, staff, 7301)
    assert c["stage"] == "delivery" and c["next_step"] == "checked"

    # 3. Ghaida: check order no + phone -> final video -> ready -> sent
    assert _tick(client, staff, 7301, "checked").json()["next_step"] == "video"
    assert _up(client, staff, "well", 7301, _mp4(71)).status_code == 201
    assert _card(client, staff, 7301)["next_step"] == "ready"
    assert client.post("/api/videos/order/well/7301/status", headers=staff, json={"to": "ready_for_delivery"}).status_code == 200
    assert _card(client, staff, 7301)["next_step"] == "delivered"
    assert client.post("/api/videos/order/well/7301/status", headers=staff, json={"to": "sent_to_customer"}).status_code == 200
    c = _card(client, staff, 7301)
    assert c["stage"] is None and all(s["done"] for s in c["steps"].values())
    assert all(x["well_id"] != 7301 for x in client.get("/api/team/tasks", headers=mgr).json()["items"])
    events = [e["event_type"] for e in client.get("/api/projects/7301/history", headers=mgr).json()["events"]]
    assert events.count("team_step") == 3


def test_phone_must_be_valid_before_check_and_steps_can_be_undone(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    assert client.post("/api/projects", headers=staff, json={"well_id": 7302, "well_type": "يدوي", "country": "Nepal",
                                                             "customer_phone": "0791234567"}).status_code == 201
    r = _tick(client, staff, 7302, "checked")
    assert r.status_code == 409 and "رقم هاتف" in r.json()["detail"]
    assert _tick(client, staff, 7302, "received").json()["steps"]["received"]["by"] == "Demo Team Member"
    assert _tick(client, staff, 7302, "received", done=False).json()["steps"]["received"]["done"] is False
    assert _tick(client, staff, 7302, "video").status_code == 422  # done from the video page, not by hand


def test_roles_money_and_assignment(client, seeded, mocks):
    admin = login(client, "admin@hayah.local")
    staff = login(client, "staff@hayah.local")
    assert client.post("/api/projects", headers=staff, json={"well_id": 7303, "well_type": "يدوي", "sale_amount": 300}).status_code == 201
    for who in ("p1@hayah.local", "viewer@hayah.local", "maint@hayah.local"):
        assert client.get("/api/team/tasks", headers=login(client, who)).status_code == 403
    body = client.get("/api/team/tasks", headers=staff).text
    assert not any(f'"{k}"' in body for k in MONEY)
    # Admin gives the employee a part of the workflow; the employee then sees their own count.
    me = client.get("/api/auth/me", headers=staff).json()
    assert client.patch(f"/api/users/{me['id']}", headers=admin, json={"team_stage": "intake"}).json()["team_stage"] == "intake"
    staff = login(client, "staff@hayah.local")
    c = client.get("/api/team/counts", headers=staff).json()
    assert c["my_stage"] == "intake" and c["mine"] == c["intake"] >= 1
    t = client.get("/api/team/tasks", headers=staff).json()
    assert t["members"]["intake"][0]["name"] == "Demo Team Member"
    assert client.patch(f"/api/users/{me['id']}", headers=admin, json={"team_stage": "boss"}).status_code == 422
    # Start date: orders before it are left out; only managers change it.
    assert client.put("/api/team/settings", headers=staff, json={"start_date": "2030-01-01"}).status_code == 403
    assert client.put("/api/team/settings", headers=admin, json={"start_date": "2030-01-01"}).status_code == 200
    assert client.get("/api/team/counts", headers=staff).json()["intake"] == 0

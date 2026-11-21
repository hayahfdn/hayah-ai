"""Team workflow v2 (Hayah, 21 Nov 2026): eight stages, one responsible person each, manager board."""
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


def _staff(client, admin, email, name):
    r = client.post("/api/users", headers=admin, json={"email": email, "full_name": name, "role": "staff", "password": "Demo-Pass-2026"})
    assert r.status_code == 201, r.text
    return r.json()["id"], login(client, email)


def _team(client):
    admin = login(client, "admin@hayah.local")
    gz, g = _staff(client, admin, "ghazi@hayah.local", "غازي")
    sh, s = _staff(client, admin, "shatha@hayah.local", "شذى")
    gd, d = _staff(client, admin, "ghaida@hayah.local", "غيداء")
    owners = {"intake": gz, "design": sh, "approval": sh, "contractor": gz, "review": gd, "delivery": sh}
    r = client.put("/api/team/settings", headers=admin, json={"owners": owners})
    assert r.status_code == 200, r.text
    return admin, g, s, d


def test_order_moves_through_all_eight_stages(client, seeded, mocks):
    admin, g, s, d = _team(client)
    assert client.post("/api/projects", headers=g, json={"well_id": 7301, "well_type": "يدوي", "customer_name": "أم محمد",
                                                         "dedication": "المرحوم محمد علي", "customer_phone": "+962791234567"}).status_code == 201
    # 1 Ghazi: intake
    c = _card(client, g, 7301)
    assert c["stage"] == "intake" and c["owner"]["name"] == "غازي" and c["next_step"] == "received"
    assert _tick(client, s, 7301, "received").status_code == 403  # not Shatha's task
    assert _tick(client, g, 7301, "received").json()["next_step"] == "country"
    con = client.get("/api/contractors", headers=g).json()[0]
    assert client.patch("/api/projects/7301", headers=g, json={"contractor_id": con["id"], "country": "Pakistan"}).status_code == 200
    # 2 Shatha: contact, design, send
    c = _card(client, s, 7301)
    assert c["stage"] == "design" and c["owner"]["name"] == "شذى"
    assert any(x["well_id"] == 7301 for x in client.get("/api/team/tasks?view=mine", headers=s).json()["items"])
    assert not any(x["well_id"] == 7301 for x in client.get("/api/team/tasks?view=mine", headers=g).json()["items"])
    _tick(client, s, 7301, "contacted", note="واتساب")
    assert _save(client, s, 7301, {"name": "المرحوم محمد علي"}).status_code == 201
    pid = _card(client, s, 7301)["plaque_id"]
    early = client.post(f"/api/plaques/{pid}/status", headers=s, json={"to": "customer_approved"})
    assert early.status_code == 409
    assert client.post(f"/api/plaques/{pid}/status", headers=s, json={"to": "awaiting_customer"}).status_code == 200
    # 3 Shatha: approval (waiting for the customer)
    c = _card(client, s, 7301)
    assert c["stage"] == "approval" and c["waiting_customer"]
    assert client.post(f"/api/plaques/{pid}/status", headers=s, json={"to": "customer_approved", "note": "واتساب"}).status_code == 200
    # 4 Ghazi: send plaque, requirements (with a note), video received
    c = _card(client, g, 7301)
    assert c["stage"] == "contractor" and c["next_step"] == "plaque_sent" and c["owner"]["name"] == "غازي"
    assert client.post("/api/team/order/7301/send-to-contractor", headers=s, json={}).status_code == 403
    assert client.post("/api/team/order/7301/send-to-contractor", headers=g, json={"note": "واتساب المقاول"}).json()["next_step"] == "requirements"
    assert _tick(client, g, 7301, "requirements").status_code == 422  # needs a note
    assert _tick(client, g, 7301, "requirements", note="أُرسلت قائمة المتطلبات").json()["next_step"] == "video_received"
    assert _tick(client, g, 7301, "video_received", note="وصل على واتساب").json()["stage"] == "review"
    # 5 Ghaida: check, video, ready -> 6 certificate prepared by the system
    assert _tick(client, d, 7301, "checked").json()["next_step"] == "video"
    assert _up(client, d, "well", 7301, _mp4(71)).status_code == 201
    assert client.post("/api/videos/order/well/7301/status", headers=d, json={"to": "ready_for_delivery"}).status_code == 200
    c = _card(client, s, 7301)
    assert c["steps"]["certificate"]["done"] and c["stage"] == "delivery" and c["owner"]["name"] == "شذى"
    cert = client.get("/api/certificates/well/7301", headers=s).json()
    assert cert["saved_at"] and cert["design"] == {}
    # 7 Shatha: send video + certificate, confirm delivery
    assert client.post("/api/videos/order/well/7301/status", headers=s, json={"to": "sent_to_customer"}).status_code == 200
    assert _tick(client, s, 7301, "confirmed", note="العميل أكد الاستلام").json()["stage"] == "close"
    # 8 Manager closes
    assert client.post("/api/team/order/7301/close", headers=s, json={}).status_code == 403
    r = client.post("/api/team/order/7301/close", headers=admin, json={"on": "2026-11-21"})
    assert r.status_code == 200 and r.json()["stage"] is None
    p = client.get("/api/projects/7301", headers=admin).json()
    assert p["delivery_status"] == "delivered" and p["delivery_date"] == "2026-11-21"
    assert all(x["well_id"] != 7301 for x in client.get("/api/team/tasks?view=all", headers=admin).json()["items"])


def test_manager_moves_a_task_and_board_shows_owner(client, seeded, mocks):
    admin, g, s, d = _team(client)
    assert client.post("/api/projects", headers=g, json={"well_id": 7302, "well_type": "يدوي", "customer_phone": "0791234567"}).status_code == 201
    me_s = client.get("/api/auth/me", headers=s).json()["id"]
    assert client.post("/api/team/order/7302/assign", headers=g, json={"stage": "intake", "user_id": me_s}).status_code == 403
    r = client.post("/api/team/order/7302/assign", headers=admin, json={"stage": "intake", "user_id": me_s, "note": "غازي في إجازة"})
    assert r.status_code == 200 and r.json()["owner"]["name"] == "شذى" and r.json()["reassigned"]
    assert _tick(client, g, 7302, "received").status_code == 403
    assert _tick(client, s, 7302, "received").status_code == 200
    assert client.post("/api/team/order/7302/assign", headers=admin, json={"stage": "intake", "user_id": None}).json()["owner"]["name"] == "غازي"
    board = client.get("/api/team/tasks?view=all", headers=admin).json()
    row = next(x for x in board["items"] if x["well_id"] == 7302)
    assert row["stage_label"] and "days" in row and row["owner"]["name"] == "غازي"
    events = [e["event_type"] for e in client.get("/api/projects/7302/history", headers=admin).json()["events"]]
    assert events.count("team_reassigned") == 2


def test_phone_check_roles_money_and_start_date(client, seeded, mocks):
    admin, g, s, d = _team(client)
    assert client.post("/api/projects", headers=g, json={"well_id": 7303, "well_type": "يدوي", "sale_amount": 300,
                                                         "customer_phone": "0791234567"}).status_code == 201
    for who in ("p1@hayah.local", "viewer@hayah.local", "maint@hayah.local"):
        assert client.get("/api/team/tasks", headers=login(client, who)).status_code == 403
    body = client.get("/api/team/tasks?view=all", headers=g).text
    assert not any(f'"{k}"' in body for k in MONEY)
    assert client.get("/api/team/counts", headers=g).json()["mine"] >= 1
    assert client.put("/api/team/settings", headers=g, json={"start_date": "2030-01-01"}).status_code == 403
    assert client.put("/api/team/settings", headers=admin, json={"owners": {"intake": 999999}}).status_code == 422
    # phone check: the manager steps in on Ghaida's stage, a local number is refused
    r = client.post(f"/api/team/order/7303/steps/checked", headers=admin, json={"done": True})
    assert r.status_code == 409 and "رقم هاتف" in r.json()["detail"]
    assert client.put("/api/team/settings", headers=admin, json={"start_date": "2030-01-01"}).status_code == 200
    assert client.get("/api/team/counts", headers=g).json()["intake"] == 0


def test_helper_shares_a_stage_and_tasks_are_newest_first(client, seeded, mocks):
    admin, g, s, d = _team(client)
    hy, h = _staff(client, admin, "haya@hayah.local", "هيا")
    r = client.put("/api/team/settings", headers=admin, json={"helpers": {"intake": [hy], "contractor": [hy]}})
    assert r.status_code == 200, r.text
    assert [x["name"] for x in next(st for st in r.json()["stages"] if st["key"] == "intake")["helpers"]] == ["هيا"]
    assert client.put("/api/team/settings", headers=g, json={"helpers": {"intake": []}}).status_code == 403
    for no in (7401, 7402):
        assert client.post("/api/projects", headers=g, json={"well_id": no, "customer_name": "عميل"}).status_code == 201
    mine = client.get("/api/team/tasks?view=mine", headers=h).json()
    assert set(mine["my_stages"]) == {"intake", "contractor"}
    nos = [x["well_id"] for x in mine["items"]]
    assert nos.index(7402) < nos.index(7401)  # newest on top
    c = _card(client, h, 7401)
    assert c["owner"]["name"] == "غازي" and [x["name"] for x in c["helpers"]] == ["هيا"]
    assert _tick(client, h, 7401, "received").status_code == 200   # Haya does Ghazi's step
    assert _tick(client, d, 7402, "received").status_code == 403   # Ghaida still cannot
    # a manager moving one order to Ghazi alone takes it out of Haya's hands
    ghazi_id = _card(client, admin, 7402)["owner"]["id"]
    assert client.post("/api/team/order/7402/assign", headers=admin, json={"stage": "intake", "user_id": ghazi_id}).status_code == 200
    assert _tick(client, h, 7402, "received").status_code == 403


def test_contractor_kind_wells_or_sacrifices(client, seeded, mocks):
    admin = login(client, "admin@hayah.local")
    r = client.post("/api/contractors", headers=admin, json={"code": "SAC9", "name": "Sac nine", "kind": "sacrifices"})
    assert r.status_code == 201 and r.json()["kind"] == "sacrifices"
    assert client.post("/api/projects", headers=admin, json={"well_id": 7501, "contractor_id": r.json()["id"]}).status_code == 422
    assert client.patch(f"/api/contractors/{r.json()['id']}", headers=admin, json={"kind": "both"}).json()["kind"] == "both"
    assert client.post("/api/projects", headers=admin, json={"well_id": 7501, "contractor_id": r.json()["id"]}).status_code == 201
    nav = client.get("/api/nav", headers=admin)
    if nav.status_code == 200:
        assert all("kind" in c for c in nav.json()["contractors"])

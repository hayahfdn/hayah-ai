"""Hayah's 20 Nov 2026 request: edit a project's number, one number per sacrifice in order of
registration, every sacrifice linked to its order, and the one-off correction of sacrifices 3091-3098."""
from tests.conftest import login

HAYAH_RENAMES = [{"from": 3098, "to": 3091}, {"from": 3099, "to": 3092}, {"from": 3100, "to": 3096}]
HAYAH_ORDERS = [{"order": "1231", "numbers": [3097, 3098]}, {"order": "1229", "numbers": [3096]},
                {"order": "1228", "numbers": [3094, 3095]}, {"order": "1227", "numbers": [3093]},
                {"order": "1225", "numbers": [3091, 3092]}]


def _sac(client, h, no, order, name, **kw):
    r = client.post("/api/sacrifices", headers=h, json={"sacrifice_no": no, "shopify_order": order, "donor_name": name,
                                                        "order_date": "2026-11-15", "animal_type": "خروف", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _all(client, h):
    return {s["sacrifice_no"]: s for s in client.get("/api/sacrifices", headers=h).json() if not s["is_sample"]}


def test_new_sacrifice_gets_next_number_automatically_and_never_repeats(client, seeded):
    mgr = login(client, "manager@hayah.local")
    a = _sac(client, mgr, 4000, "#1300", "أ")
    r = client.post("/api/sacrifices", headers=mgr, json={"donor_name": "ب"})  # no number typed
    assert r.status_code == 201 and r.json()["sacrifice_no"] == a["sacrifice_no"] + 1
    r = client.post("/api/sacrifices/bulk", headers=mgr, json={"quantity": 3, "shopify_order": "1301", "donor_name": "ج"})
    assert r.status_code == 201
    nos = [s["sacrifice_no"] for s in r.json()]
    assert nos == [4002, 4003, 4004] and {s["shopify_order"] for s in r.json()} == {"#1301"}
    assert client.post("/api/sacrifices", headers=mgr, json={"sacrifice_no": 4003}).status_code == 409
    v = client.get("/api/sacrifices/orders/%231301", headers=mgr).json()
    assert [s["sacrifice_no"] for s in v["sacrifices"]] == nos and v["order"] == "#1301"


def test_change_one_sacrifice_number(client, seeded):
    mgr = login(client, "manager@hayah.local")
    _sac(client, mgr, 5001, "#1400", "أ")
    _sac(client, mgr, 5002, "#1400", "ب")
    assert client.patch("/api/sacrifices/5001/number", headers=mgr, json={"new_number": 5002}).status_code == 409
    r = client.patch("/api/sacrifices/5001/number", headers=mgr, json={"new_number": 5010})
    assert r.status_code == 200 and r.json()["sacrifice"]["sacrifice_no"] == 5010
    # history follows the number: an edit made before the change can still be undone
    assert client.patch("/api/sacrifices/5010", headers=mgr, json={"notes": "x"}).status_code == 200
    staff = login(client, "staff@hayah.local")
    assert client.patch("/api/sacrifices/5002/number", headers=staff, json={"new_number": 5020}).status_code == 403


def test_hayah_correction_preview_apply_undo(client, seeded, db):
    mgr = login(client, "manager@hayah.local")
    w = client.post("/api/projects", headers=mgr, json={"well_id": 7225, "well_type": "يدوي", "shopify_order": "#1225",
                                                       "notes": "خروف add-on: sacrifice 3098\nخروف add-on: sacrifice 3099"}).json()
    # what the live site plausibly holds: the order's sacrifices exist, but with the wrong numbers
    _sac(client, mgr, 3093, "#1227", "1227")
    _sac(client, mgr, 3094, "#1228", "1228-a")
    _sac(client, mgr, 3095, "#1228", "1228-b")
    _sac(client, mgr, 3096, "#1231", "1231-a")
    _sac(client, mgr, 3097, "#1231", "1231-b")
    _sac(client, mgr, 3098, "#1225", "1225-a")
    _sac(client, mgr, 3099, "#1225", "1225-b")
    _sac(client, mgr, 3100, "#1229", "1229")
    from app.models import Sacrifice
    for no in (3098, 3099):
        s = db.query(Sacrifice).filter_by(sacrifice_no=no).one()
        s.parent_project_id = w["id"]
    db.commit()
    body = {"renames": HAYAH_RENAMES, "orders": HAYAH_ORDERS}
    p = client.post("/api/sacrifices/renumber/preview", headers=mgr, json=body).json()
    assert p["ok"], p["errors"]
    after = {r["after_no"]: (r["before_no"], r["after_order"]) for r in p["rows"]}
    assert after == {3091: (3098, "#1225"), 3092: (3099, "#1225"), 3093: (3093, "#1227"), 3094: (3094, "#1228"),
                     3095: (3095, "#1228"), 3096: (3100, "#1229"), 3097: (3097, "#1231"), 3098: (3096, "#1231")}
    assert _all(client, mgr)[3098]["donor_name"] == "1225-a"  # preview changed nothing
    assert client.post("/api/sacrifices/renumber/apply", headers=mgr, json={**body, "token": "wrong"}).status_code == 409
    before_csv = client.get("/api/sacrifices/backup.csv", headers=mgr)
    assert before_csv.status_code == 200 and "1225-a" in before_csv.text and "3098" in before_csv.text
    pre = client.post("/api/sacrifices/renumber/verify", headers=mgr, json=body).json()
    assert not pre["ok"]  # before the change the orders do not match the table
    r = client.post("/api/sacrifices/renumber/apply", headers=mgr, json={**body, "token": p["token"]})
    assert r.status_code == 200, r.text
    assert r.json()["backup_rows"] >= 8 and r.json()["verify"]["ok"], r.json()["verify"]
    assert {o["order"]: o["actual"] for o in r.json()["verify"]["orders"]} == {
        "#1231": [3097, 3098], "#1229": [3096], "#1228": [3094, 3095], "#1227": [3093], "#1225": [3091, 3092]}
    assert client.post("/api/sacrifices/renumber/verify", headers=mgr, json=body).json()["ok"]
    staff = login(client, "staff@hayah.local")
    assert client.get("/api/sacrifices/backup.csv", headers=staff).status_code == 403
    bid0 = r.json()["batch_id"]
    kept = client.get(f"/api/sacrifices/renumber/{bid0}/backup.csv", headers=mgr).text
    # the automatic copy holds the numbers as they were before: 3098 was still 1225-a's
    assert any(line.split(",")[1:4] == ["3098", "#1225", "1225-a"] for line in kept.splitlines())
    now = _all(client, mgr)
    assert {n: (s["donor_name"], s["shopify_order"]) for n, s in now.items()} == {
        3091: ("1225-a", "#1225"), 3092: ("1225-b", "#1225"), 3093: ("1227", "#1227"), 3094: ("1228-a", "#1228"),
        3095: ("1228-b", "#1228"), 3096: ("1229", "#1229"), 3097: ("1231-b", "#1231"), 3098: ("1231-a", "#1231")}
    assert now[3091]["parent_well_id"] == 7225  # links follow
    well = client.get("/api/projects/7225", headers=mgr).json()
    assert "sacrifice 3091" in well["notes"] and "sacrifice 3092" in well["notes"]
    assert [s["sacrifice_no"] for s in well["addon_sacrifices"]] == [3091, 3092]
    v = client.get("/api/sacrifices/orders/1225", headers=mgr).json()
    assert [s["sacrifice_no"] for s in v["sacrifices"]] == [3091, 3092] and [x["well_id"] for x in v["wells"]] == [7225]
    # the old creation records now point at the new numbers
    from app.models import AuditLog
    db.expire_all()
    created = {a.entity_id for a in db.query(AuditLog).filter_by(action="sacrifice.create")}
    assert {"3091", "3096", "3098"} <= created and "3100" not in created
    # the next sacrifice continues after the highest number; while it holds 3099, undo is refused
    extra = client.post("/api/sacrifices", headers=mgr, json={"donor_name": "new"}).json()
    assert extra["sacrifice_no"] == 3099
    bid = client.get("/api/sacrifices/renumber/history", headers=mgr).json()[0]["id"]
    r = client.post(f"/api/sacrifices/renumber/undo/{bid}", headers=mgr)
    assert r.status_code == 409 and "3099" in r.text
    assert client.patch("/api/sacrifices/3099/number", headers=mgr, json={"new_number": 3200}).status_code == 200
    # undo puts everything back
    assert client.post(f"/api/sacrifices/renumber/undo/{bid}", headers=mgr).status_code == 200
    back = _all(client, mgr)
    assert back[3098]["donor_name"] == "1225-a" and back[3100]["donor_name"] == "1229" and back[3096]["donor_name"] == "1231-a"
    assert client.post(f"/api/sacrifices/renumber/undo/{bid}", headers=mgr).status_code == 409


def test_plan_reports_a_number_held_by_someone_else(client, seeded):
    mgr = login(client, "manager@hayah.local")
    _sac(client, mgr, 3091, "#1111", "other order")
    _sac(client, mgr, 3098, "#1225", "1225-a")
    p = client.post("/api/sacrifices/renumber/preview", headers=mgr,
                    json={"renames": [{"from": 3098, "to": 3091}], "orders": []}).json()
    assert not p["ok"] and any("3091" in e for e in p["errors"])


def test_change_project_number_everywhere(client, seeded, db):
    mgr = login(client, "manager@hayah.local")
    client.post("/api/projects", headers=mgr, json={"well_id": 8801, "well_type": "يدوي", "extras": "خروف"})
    client.post("/api/projects", headers=mgr, json={"well_id": 8802, "well_type": "يدوي"})
    assert client.patch("/api/projects/8801/number", headers=mgr, json={"new_number": 8802}).status_code == 409
    staff = login(client, "staff@hayah.local")
    assert client.patch("/api/projects/8801/number", headers=staff, json={"new_number": 8899}).status_code == 403
    r = client.patch("/api/projects/8801/number", headers=mgr, json={"new_number": 8899})
    assert r.status_code == 200 and r.json()["changed"]
    assert client.get("/api/projects/8801", headers=mgr).status_code == 404
    p = client.get("/api/projects/8899", headers=mgr).json()
    assert p["addon_sacrifices"]
    sac = [s for s in client.get("/api/sacrifices", headers=mgr).json() if s["parent_well_id"] == 8899]
    assert sac and "8899" in sac[0]["notes"] and "8801" not in sac[0]["notes"]
    hist = client.get("/api/projects/8899/history", headers=mgr)
    assert hist.status_code == 200
    from app.models import AuditLog
    assert db.query(AuditLog).filter_by(action="project.create", entity_id="8899").count() == 1

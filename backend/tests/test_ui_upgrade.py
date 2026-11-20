"""Side menu, contractor colours, the four well types, and plaques approved from an order."""
import io
import json

from sqlalchemy import text

from app.cli import _tiny_png
from tests.conftest import login


def _save(client, h, n, well_id=9006, **form):
    d = {"template": "hayah_square", "size": "digital", "name": "فاعل خير", "well_id": str(well_id)}
    data = {"design": json.dumps(d, ensure_ascii=False), **{k: "true" if v else "false" for k, v in form.items()}}
    return client.post(f"/api/projects/{well_id}/plaques", headers=h, data=data,
                       files={"file": ("plaque.png", io.BytesIO(_tiny_png(400 + n)), "image/png")})


# ---------------- plaques from an order ----------------
def test_approve_links_plaque_to_order_and_keeps_versions(client, manager, mocks):
    assert client.get("/api/projects/9006", headers=manager).json()["plaque_status"] is None
    draft = _save(client, manager, 1)
    assert draft.status_code == 201 and draft.json()["version"] == 1 and not draft.json()["approved"]
    p = client.get("/api/projects/9006", headers=manager).json()
    assert p["plaque_status"] == "draft" and p["plaque_media_id"] is None

    ok = _save(client, manager, 2, approve=True)
    assert ok.status_code == 201, ok.text
    row = ok.json()
    assert row["approved"] and row["version"] == 2
    p = client.get("/api/projects/9006", headers=manager).json()
    assert p["plaque_status"] == "approved" and p["plaque_media_id"] == row["media_id"] and p["plaque_approved_by"]

    # The approved image can be opened later.
    f = client.get(f"/api/projects/9006/plaques/file/{row['media_id']}", headers=manager)
    assert f.status_code == 200 and f.headers["content-type"] == "image/png" and f.content == _tiny_png(402)

    # A second approval needs the person's confirmation; nothing is replaced without it.
    again = _save(client, manager, 3, approve=True)
    assert again.status_code == 409
    assert client.get("/api/projects/9006", headers=manager).json()["plaque_media_id"] == row["media_id"]
    replaced = _save(client, manager, 4, approve=True, replace=True)
    assert replaced.status_code == 201 and replaced.json()["approved"]

    versions = client.get("/api/projects/9006/plaques", headers=manager).json()
    assert sorted(v["version"] for v in versions) == [1, 2, 3]  # the refused save stored nothing
    assert sum(v["approved"] for v in versions) == 1
    # Earlier versions stay available, and an older one can be approved again.
    old = [v for v in versions if v["media_id"] == row["media_id"]][0]
    assert client.post(f"/api/projects/9006/plaques/{old['id']}/approve", headers=manager).status_code == 409
    back = client.post(f"/api/projects/9006/plaques/{old['id']}/approve?replace=true", headers=manager)
    assert back.status_code == 200 and back.json()["approved"]
    events = client.get("/api/projects/9006/history", headers=manager).json()["events"]
    assert sum(e["event_type"] == "plaque_approved" for e in events) == 3


def test_staff_can_approve_contractor_cannot_and_file_is_scoped(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    r = _save(client, staff, 10, approve=True)
    assert r.status_code == 201
    contractor = login(client, "p1@hayah.local")
    assert _save(client, contractor, 11, approve=True).status_code == 403
    # A contractor cannot open another contractor's plaque; a wrong media id is 404.
    pc = client.get("/api/projects/9006", headers=staff).json()["contractor"]
    if not pc or pc["code"] != "P1":
        assert client.get(f"/api/projects/9006/plaques/file/{r.json()['media_id']}", headers=contractor).status_code == 404
    assert client.get("/api/projects/9006/plaques/file/999999", headers=staff).status_code == 404


# ---------------- side menu ----------------
def test_nav_lists_months_contractors_by_country_and_partners_for_managers(client, manager):
    n = client.get("/api/nav", headers=manager).json()
    assert n["current"] in n["wells"] and n["current"] in n["sacrifices"]
    assert n["contractors"] and all({"code", "name", "country", "color"} <= set(c) for c in n["contractors"])
    assert {p["code"] for p in n["partners"]} >= {"MOHAMMED", "GHAZI", "CLIQ"}


def test_nav_hides_finance_pages_from_staff_and_contractors(client, seeded):
    staff = client.get("/api/nav", headers=login(client, "staff@hayah.local")).json()
    # Employees get sacrifice months (no cost/profit on those pages); partners and banks stay hidden.
    assert staff["wells"] and staff["sacrifices"] and staff["partners"] == [] and staff["banks"] == [] and staff["contractors"]
    con = client.get("/api/nav", headers=login(client, "p1@hayah.local")).json()
    assert con["contractors"] == [] and con["partners"] == [] and con["sacrifices"] == []


# ---------------- contractor colours ----------------
def test_new_contractor_gets_its_own_colour_and_manager_can_change_it(client, manager):
    used = {c["color"] for c in client.get("/api/contractors", headers=manager).json()}
    r = client.post("/api/contractors", headers=manager, json={"code": "KEN1", "name": "Kenya 1", "country": "Kenya"})
    assert r.status_code == 201 and r.json()["color"] and r.json()["color"] not in used
    cid = r.json()["id"]
    assert client.patch(f"/api/contractors/{cid}", headers=manager, json={"color": "#abcdef"}).json()["color"] == "#ABCDEF"
    assert client.patch(f"/api/contractors/{cid}", headers=manager, json={"color": "red"}).status_code == 422
    staff = login(client, "staff@hayah.local")
    assert client.patch(f"/api/contractors/{cid}", headers=staff, json={"color": "#000000"}).status_code == 403


def test_country_follows_contractor(client, manager):
    cons = client.get("/api/contractors", headers=manager).json()
    a = next(c for c in cons if c["country"])
    b = next(c for c in cons if c["country"] and c["country"] != a["country"])
    r = client.post("/api/projects", headers=manager, json={"well_id": 77001, "contractor_id": a["id"]})
    assert r.json()["country"] == a["country"]
    r = client.patch("/api/projects/77001", headers=manager, json={"contractor_id": b["id"], "expected_version": r.json()["version"]})
    assert r.json()["country"] == b["country"]


# ---------------- the four well types ----------------
def test_api_stores_one_name_per_type(client, manager):
    for i, (given, stored) in enumerate([("بئر سطحي يدوي", "يدوي"), ("يدوي مع سيراميك", "يدوي"), ("بئر ارتوازي متوسط", "متوسط"),
                                         ("بئر ارتوازي عميق", "عميق"), ("بئر ارتوازي متوضأ", "عميق"), ("شمسي", "شمسي")]):
        r = client.post("/api/projects", headers=manager, json={"well_id": 78000 + i, "well_type": given})
        assert r.status_code == 201 and r.json()["well_type"] == stored, (given, r.text)
    assert client.post("/api/projects", headers=manager, json={"well_id": 78100, "well_type": "قصر"}).status_code == 422
    lists = client.get("/api/settings/lists", headers=manager).json()
    assert lists["well_types"] == ["يدوي", "متوسط", "عميق", "شمسي"]


def test_unify_old_rows_is_logged_and_can_be_undone(client, admin, db):
    rows = {"بئر سطحي يدوي": 1, "بئر يدوي مع سيراميك": 2, "بئر ارتوازي متوضأ": 3, "بئر متوضأ عميق": 4,
            "بئر سطحي كهربائي": 5, "متوسط": 6, "شيء آخر": 7}
    for old, i in rows.items():  # old names written straight to the table, as older imports did
        db.execute(text("insert into projects (well_id, well_type, currency, payment_status, construction_status, delivery_status, "
                        "video_status, maintenance_status, is_sample, version, created_at, updated_at) values "
                        "(:w, :t, 'USD', 'unpaid', 'new_order', 'not_ready', 'none', 'none', false, 1, now(), now())"),
                   {"w": 79000 + i, "t": old})
    db.commit()
    st = client.get("/api/admin/well-types", headers=admin).json()
    assert {p["from"] for p in st["pending"]} >= {"بئر سطحي يدوي", "بئر ارتوازي متوضأ", "بئر سطحي كهربائي"}
    assert st["unknown"] == [{"value": "شيء آخر", "count": 1}]
    run = client.post("/api/admin/well-types/normalize", headers=admin).json()
    assert run["changed"] == 5 and run["audit_id"]
    got = dict(db.execute(text("select well_id, well_type from projects where well_id between 79000 and 79010")).all())
    assert got == {79001: "يدوي", 79002: "يدوي", 79003: "عميق", 79004: "عميق", 79005: "كهربائي", 79006: "متوسط", 79007: "شيء آخر"}
    assert db.execute(text("select extras from projects where well_id = 79002")).scalar() == "سيراميك"
    assert client.get("/api/admin/well-types", headers=admin).json()["pending"] == []

    undo = client.post(f"/api/admin/well-types/undo/{run['audit_id']}", headers=admin).json()
    assert undo["restored"] == 5
    db.expire_all()
    assert db.execute(text("select well_type from projects where well_id = 79003")).scalar() == "بئر ارتوازي متوضأ"
    assert db.execute(text("select extras from projects where well_id = 79002")).scalar() is None
    assert client.post(f"/api/admin/well-types/undo/{run['audit_id']}", headers=admin).status_code == 409
    staff = login(client, "staff@hayah.local")
    assert client.post("/api/admin/well-types/normalize", headers=staff).status_code == 403

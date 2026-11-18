"""Unified well types, contractor row colours and approved plaques (migration 0005)."""
import io
import json

import pytest

from app.cli import _tiny_png
from app.services.well_types import normalize


@pytest.mark.parametrize("old,new", [
    ("بئر سطحي يدوي", "يدوي"), ("يدوي مع سيراميك", "يدوي"), ("يدوي", "يدوي"),
    ("بئر ارتوازي متوسط", "متوسط"), ("متوسط", "متوسط"),
    ("بئر ارتوازي عميق", "عميق"), ("متوضأ", "عميق"), ("بئر ارتوازي متوضأ", "عميق"), ("عميق", "عميق"),
    ("شمسي", "شمسي"), ("سطحي كهربائي", "كهربائي"), ("  يدوي  ", "يدوي"),
    (None, None), ("", None),
])
def test_normalize_table_from_hayah(old, new):
    assert normalize(old) == new


def test_unknown_type_is_kept_not_lost():
    assert normalize("بئر سطحي مع خزان") == "بئر سطحي مع خزان"


def test_every_write_path_stores_the_unified_name(db, seeded):
    from app.models import Project
    p = Project(well_id=55501, well_type="بئر ارتوازي متوضأ")
    db.add(p)
    db.commit()
    assert db.get(Project, p.id).well_type == "عميق"


def test_api_rejects_unknown_type_and_only_lists_four(client, manager):
    r = client.post("/api/projects", json={"well_id": 55502, "well_type": "نوع جديد"}, headers=manager)
    assert r.status_code == 422
    r = client.post("/api/projects", json={"well_id": 55503, "well_type": "بئر سطحي يدوي"}, headers=manager)
    assert r.status_code == 201 and r.json()["well_type"] == "يدوي"
    assert client.get("/api/settings/lists", headers=manager).json()["well_types"] == ["يدوي", "متوسط", "عميق", "شمسي"]


def test_well_type_list_cannot_get_duplicates(client, seeded):
    from tests.conftest import login
    admin = login(client, "admin@hayah.local")
    r = client.put("/api/settings/lists/well_types", json=["يدوي", "بئر سطحي يدوي"], headers=admin)
    assert r.status_code == 422


def test_legacy_electric_type_is_kept_on_its_project(client, manager, db):
    from app.models import Project
    db.add(Project(well_id=55504, well_type="سطحي كهربائي"))
    db.commit()
    r = client.get("/api/projects/55504", headers=manager).json()
    assert r["well_type"] == "كهربائي"
    # editing something else on that project keeps the old type
    r = client.patch("/api/projects/55504", json={"notes": "x", "well_type": "كهربائي", "expected_version": r["version"]}, headers=manager)
    assert r.status_code == 200 and r.json()["well_type"] == "كهربائي"


def test_country_follows_the_contractor(client, manager):
    cons = {c["code"]: c for c in client.get("/api/contractors", headers=manager).json()}
    r = client.post("/api/projects", json={"well_id": 55505, "contractor_id": cons["NEP1"]["id"]}, headers=manager)
    assert r.status_code == 201 and r.json()["country"] == "Nepal"
    r = client.patch("/api/projects/55505", json={"contractor_id": cons["PAK1"]["id"], "expected_version": r.json()["version"]},
                     headers=manager)
    assert r.json()["country"] == "Pakistan"


def test_contractors_get_distinct_colours_automatically(client, manager):
    cons = client.get("/api/contractors", headers=manager).json()
    colours = [c["color"] for c in cons]
    assert all(colours) and len(set(colours)) == len(colours)
    r = client.post("/api/contractors", json={"code": "KEN1", "name": "Kenya 1", "country": "Kenya"}, headers=manager)
    assert r.status_code == 201 and r.json()["color"] and r.json()["color"] not in colours
    r = client.patch(f"/api/contractors/{r.json()['id']}", json={"color": "#123456"}, headers=manager)
    assert r.json()["color"] == "#123456"
    assert client.patch(f"/api/contractors/{r.json()['id']}", json={"color": "red"}, headers=manager).status_code == 422


def test_palette_never_runs_out():
    from app.services.contractor_colors import next_color
    used: set[str] = set()
    for _ in range(40):
        c = next_color(used)
        assert c not in used
        used.add(c)


def _save(client, h, n, approve=False, replace=False, well_id=9006):
    d = {"template": "hayah_square", "size": "digital", "name": f"اسم {n}", "well_id": str(well_id)}
    return client.post(f"/api/projects/{well_id}/plaques", headers=h,
                       data={"design": json.dumps(d, ensure_ascii=False), "approve": str(approve).lower(),
                             "replace_approved": str(replace).lower()},
                       files={"file": ("plaque.png", io.BytesIO(_tiny_png(400 + n)), "image/png")})


def test_approve_plaque_links_it_to_the_order(client, manager, mocks):
    r = _save(client, manager, 1, approve=True)
    assert r.status_code == 201, r.text
    assert r.json()["approved"] is True
    p = client.get("/api/projects/9006", headers=manager).json()
    assert p["plaque_media_id"] == r.json()["media_id"] and p["plaque_approved_at"]
    # the approved image can be opened from the order
    img = client.get(f"/api/media/{p['plaque_media_id']}/content", headers=manager)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG"
    events = [e["event_type"] for e in client.get("/api/projects/9006/history", headers=manager).json()["events"]]
    assert "plaque_approved" in events


def test_new_version_never_replaces_the_approved_one_without_consent(client, manager, mocks):
    first = _save(client, manager, 2, approve=True).json()
    r = _save(client, manager, 3, approve=True)
    assert r.status_code == 409
    p = client.get("/api/projects/9006", headers=manager).json()
    assert p["plaque_media_id"] == first["media_id"]
    # nothing was stored by the refused request
    assert len(client.get("/api/projects/9006/plaques", headers=manager).json()) == 1
    r = _save(client, manager, 3, approve=True, replace=True)
    assert r.status_code == 201
    listed = client.get("/api/projects/9006/plaques", headers=manager).json()
    assert len(listed) == 2  # the earlier version is still there
    assert [x["approved"] for x in listed] == [True, False]


def test_approve_an_earlier_saved_version(client, manager, mocks):
    draft = _save(client, manager, 4).json()
    assert draft["approved"] is False
    assert client.get("/api/projects/9006", headers=manager).json()["plaque_media_id"] is None
    r = client.post("/api/projects/9006/plaques/approve", json={"media_id": draft["media_id"]}, headers=manager)
    assert r.status_code == 200 and r.json()["plaque_media_id"] == draft["media_id"]
    other = _save(client, manager, 5).json()
    assert client.post("/api/projects/9006/plaques/approve", json={"media_id": other["media_id"]}, headers=manager).status_code == 409
    assert client.post("/api/projects/9006/plaques/approve", json={"media_id": other["media_id"], "replace_approved": True},
                       headers=manager).json()["plaque_media_id"] == other["media_id"]
    # a plaque of another well cannot be approved here
    assert client.post("/api/projects/9001/plaques/approve", json={"media_id": other["media_id"]}, headers=manager).status_code == 404


def test_contractor_cannot_open_other_contractors_files(client, manager, mocks, seeded):
    from tests.conftest import login
    saved = _save(client, manager, 6, well_id=9006).json()  # 9006 belongs to NEP1
    p1 = login(client, "p1@hayah.local")
    assert client.get(f"/api/media/{saved['media_id']}/content", headers=p1).status_code == 404

import io
import json

from app.cli import _tiny_png


def save(client, h, design=None, content=None, well_id=9006, mime="image/png"):
    d = design if design is not None else {"template": "hayah_square", "size": "digital", "name": "فاعل خير", "well_id": str(well_id)}
    return client.post(f"/api/projects/{well_id}/plaques", headers=h,
                       data={"design": json.dumps(d, ensure_ascii=False)},
                       files={"file": ("plaque.png", io.BytesIO(content or _tiny_png(301)), mime)})


def test_save_plaque_goes_to_plaques_folder_and_history(client, manager, mocks):
    r = save(client, manager)
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["filename"].startswith("9006_") and "_PLAQUE_" in row["filename"]
    f = [x for x in mocks["drive"]._idx()["files"].values() if x["name"] == row["filename"]][0]
    assert f["path"].startswith("HAYAH PROJECTS/Plaques/9006/")
    listed = client.get("/api/projects/9006/plaques", headers=manager).json()
    assert len(listed) == 1 and listed[0]["design"]["name"] == "فاعل خير"
    h = client.get("/api/projects/9006/history", headers=manager).json()
    assert any(e["event_type"] == "plaque_saved" for e in h["events"])
    assert any(m["category"] == "PLAQUE" for m in h["media"])


def test_staff_can_save_but_contractor_cannot(client, seeded):
    from tests.conftest import login
    staff = login(client, "staff@hayah.local")
    assert save(client, staff, content=_tiny_png(302)).status_code == 201
    contractor = login(client, "p1@hayah.local")
    assert save(client, contractor, content=_tiny_png(303)).status_code == 403


def test_rejects_bad_design_and_file_type(client, manager):
    assert save(client, manager, design={"name": "x"}).status_code == 422
    r = client.post("/api/projects/9006/plaques", headers=manager, data={"design": "not json"},
                    files={"file": ("p.png", io.BytesIO(_tiny_png(304)), "image/png")})
    assert r.status_code == 422
    assert save(client, manager, content=b"\xff\xd8\xff" + b"0" * 20, mime="image/jpeg").status_code == 415


def test_unknown_well(client, manager):
    assert save(client, manager, well_id=987654).status_code == 404


def _sacrifice(db, no=4321):
    from app.models import Sacrifice
    db.add(Sacrifice(sacrifice_no=no, donor_name="آمال الحوراني", animal_type="خروف", intention="صدقة", cost=50, sale_price=120))
    db.commit()


def test_sacrifice_plaque_data_has_no_money_and_saves(client, db, mocks, seeded):
    from tests.conftest import login
    _sacrifice(db)
    staff = login(client, "staff@hayah.local")
    r = client.get("/api/plaques/sacrifices/4321", headers=staff)
    assert r.status_code == 200, r.text
    s = r.json()["sacrifice"]
    assert s["donor_name"] == "آمال الحوراني" and "cost" not in s and "sale_price" not in s
    d = {"template": "sacrifice_portrait", "name": "آمال الحوراني", "sacrifice_no": "4321"}
    r = client.post("/api/plaques/sacrifices/4321", headers=staff, data={"design": json.dumps(d, ensure_ascii=False)},
                    files={"file": ("p.png", io.BytesIO(_tiny_png(401)), "image/png")})
    assert r.status_code == 201, r.text
    assert r.json()["filename"].startswith("S4321_") and "_PLAQUE_001" in r.json()["filename"]
    f = [x for x in mocks["drive"]._idx()["files"].values() if x["name"] == r.json()["filename"]][0]
    assert f["path"].startswith("HAYAH PROJECTS/Plaques/Sacrifices/4321/")
    saved = client.get("/api/plaques/sacrifices/4321", headers=staff).json()["saved"]
    assert len(saved) == 1 and saved[0]["design"]["name"] == "آمال الحوراني"


def test_sacrifice_plaque_blocked_for_contractor_and_unknown(client, db, seeded):
    from tests.conftest import login
    _sacrifice(db)
    assert client.get("/api/plaques/sacrifices/4321", headers=login(client, "p1@hayah.local")).status_code == 403
    assert client.get("/api/plaques/sacrifices/99999999", headers=login(client, "staff@hayah.local")).status_code == 404

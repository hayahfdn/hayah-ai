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

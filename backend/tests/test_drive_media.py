import io

from app.cli import _tiny_png


def upload(client, h, content, name="photo.png", mime="image/png", well_id=9006, category="CONSTRUCTION"):
    data = {"category": category}
    if well_id:
        data["well_id"] = str(well_id)
    return client.post("/api/media/upload", headers=h, data=data, files={"file": (name, io.BytesIO(content), mime)})


def test_upload_goes_to_well_folder_with_standard_name(client, manager, mocks):
    r = upload(client, manager, _tiny_png(77))
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["filename"].startswith("9006_") and m["filename"].endswith("_CONSTRUCTION_001.png")
    idx = mocks["drive"]._idx()
    f = idx["files"][m["drive_file_id"]]
    assert f["path"].startswith("HAYAH PROJECTS/Raw Footages/9006/")
    p = client.get("/api/projects/9006", headers=manager).json()
    assert p["raw_media_folder_id"] == m["drive_folder_id"]


def test_duplicate_upload_rejected(client, manager, mocks):
    assert upload(client, manager, _tiny_png(78)).status_code == 201
    r = upload(client, manager, _tiny_png(78), name="same-file-renamed.png")
    assert r.status_code == 409
    assert len(mocks["drive"]._idx()["files"]) == 4 + 1  # 4 seeded + 1


def test_sequence_numbers_increment(client, manager):
    a = upload(client, manager, _tiny_png(80)).json()["filename"]
    b = upload(client, manager, _tiny_png(81)).json()["filename"]
    assert a.endswith("_001.png") and b.endswith("_002.png")


def test_unassigned_media_goes_to_review(client, manager, mocks):
    r = upload(client, manager, _tiny_png(90), well_id=None)
    assert r.status_code == 201 and r.json()["filename"].startswith("UNASSIGNED_")
    path = mocks["drive"]._idx()["files"][r.json()["drive_file_id"]]["path"]
    assert path.startswith("HAYAH PROJECTS/Unassigned Media/")
    cases = client.get("/api/review", headers=manager).json()
    case = next(c for c in cases if c["kind"] == "unassigned_media")
    client.post(f"/api/review/{case['id']}/decision", json={"approve": True, "well_id": 9005}, headers=manager)
    media = client.get("/api/media", params={"well_id": 9005}, headers=manager).json()
    assert len(media) == 1
    # the original Drive file still exists untouched
    assert (mocks["drive"].root / path).exists()


def test_file_type_validation(client, manager):
    assert upload(client, manager, b"MZ\x90\x00 fake exe", name="x.exe", mime="application/x-msdownload").status_code == 415
    assert upload(client, manager, b"MZ\x90\x00 not a png", name="x.png", mime="image/png").status_code == 415


def test_drive_client_has_no_delete():
    from app.integrations.drive.google import GoogleDriveClient
    from app.integrations.drive.mock import MockDriveClient
    for cls in (GoogleDriveClient, MockDriveClient):
        assert not any("delete" in n or "trash" in n for n in dir(cls))


def test_drive_outage_leaves_no_partial_record(client, manager, mocks):
    mocks["drive"].fail_next = 1
    assert upload(client, manager, _tiny_png(99)).status_code == 502
    from app.db import SessionLocal
    from app.models import MediaAsset
    with SessionLocal() as s:
        assert s.query(MediaAsset).filter(MediaAsset.original_filename == "photo.png").count() == 0
    assert upload(client, manager, _tiny_png(99)).status_code == 201

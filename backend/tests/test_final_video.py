"""Final delivery video: upload MP4/MOV, play with seeking, replace, states, no mixing between
orders, timeline, signed links and role checks; dashboard counts."""
import io

from tests.conftest import login


def _mp4(seed: int, size: int = 4096) -> bytes:
    # a minimal ISO-BMFF header ("ftyp") followed by distinct bytes, enough for type sniffing
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + bytes((seed + i) % 251 for i in range(size))


def _new_well(client, h, well_id, **kw):
    r = client.post("/api/projects", headers=h, json={"well_id": well_id, "well_type": "يدوي", "country": "Pakistan", **kw})
    assert r.status_code == 201, r.text


def _up(client, h, kind, no, data, name="final.mp4", mime="video/mp4"):
    return client.post(f"/api/videos/order/{kind}/{no}", headers=h, files={"file": (name, io.BytesIO(data), mime)})


def test_upload_play_replace_and_states(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    _new_well(client, staff, 7201, customer_name="أم أحمد")
    v = client.get("/api/videos/order/well/7201", headers=staff).json()
    assert v["status"] == "not_uploaded" and v["versions"] == []
    # cannot mark ready before a video exists
    assert client.post("/api/videos/order/well/7201/status", headers=staff, json={"to": "ready_for_delivery"}).status_code == 409
    # only MP4 / MOV
    assert _up(client, staff, "well", 7201, b"%PDF-1.4 xx", "x.pdf", "application/pdf").status_code == 415
    r = _up(client, staff, "well", 7201, _mp4(1))
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "uploaded" and v["uploaded_by"] and v["uploaded_at"] and len(v["versions"]) == 1
    mid = v["current_media_id"]
    # play: signed link, Range requests work (seeking in the player)
    link = client.get(f"/api/videos/file/{mid}/link", headers=staff).json()
    full = client.get(link["url"])
    assert full.status_code == 200 and full.content.startswith(b"\x00\x00\x00\x18ftyp")
    part = client.get(link["url"], headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert "attachment" in client.get(link["download_url"]).headers["content-disposition"]
    assert client.get(f"/api/videos/file/{mid}?t=bad").status_code == 401
    # states
    assert client.post("/api/videos/order/well/7201/status", headers=staff, json={"to": "sent_to_customer"}).status_code == 409
    assert client.post("/api/videos/order/well/7201/status", headers=staff, json={"to": "ready_for_delivery"}).json()["status"] == "ready_for_delivery"
    s = client.post("/api/videos/order/well/7201/status", headers=staff, json={"to": "sent_to_customer", "note": "واتساب"}).json()
    assert s["status"] == "sent_to_customer" and s["sent_by"] and s["sent_note"] == "واتساب"
    # a newer version replaces it, keeps the old one, and goes back to "uploaded"
    v = _up(client, staff, "well", 7201, _mp4(2), "final-v2.mov", "video/quicktime").json()
    assert v["status"] == "uploaded" and len(v["versions"]) == 2 and v["versions"][0]["current"] and not v["versions"][1]["current"]
    assert v["versions"][0]["mime_type"] == "video/quicktime"
    # uploading the current file again is refused
    assert _up(client, staff, "well", 7201, _mp4(2), "again.mov", "video/quicktime").status_code == 409
    events = [e["event_type"] for e in client.get("/api/projects/7201/history", headers=staff).json()["events"]]
    assert events.count("final_video_uploaded") == 2 and events.count("final_video_status") == 2
    assert client.get("/api/projects/7201", headers=staff).json()["video_status"] == "completed"


def test_videos_never_mix_between_orders(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    _new_well(client, staff, 7202)
    _new_well(client, staff, 7203)
    assert _up(client, staff, "well", 7202, _mp4(9)).status_code == 201
    r = _up(client, staff, "well", 7203, _mp4(9))
    assert r.status_code == 409 and "another order" in r.json()["detail"]
    assert client.get("/api/videos/order/well/7203", headers=staff).json()["status"] == "not_uploaded"
    # a link for one file cannot open another
    a = client.get("/api/videos/order/well/7202", headers=staff).json()["current_media_id"]
    link = client.get(f"/api/videos/file/{a}/link", headers=staff).json()["url"]
    assert client.get(link.replace(f"/file/{a}?", f"/file/{a + 999}?")).status_code == 403


def test_sacrifice_video_and_counts(client, seeded, mocks):
    mgr, staff = login(client, "manager@hayah.local"), login(client, "staff@hayah.local")
    assert client.post("/api/sacrifices", headers=mgr, json={"sacrifice_no": 6101, "donor_name": "فاعل خير", "animal_type": "خروف"}).status_code == 201
    before = client.get("/api/ops/counts", headers=staff).json()
    assert {"plaques", "videos", "orders"} <= set(before)
    assert _up(client, staff, "sacrifice", 6101, _mp4(33)).status_code == 201
    client.post("/api/videos/order/sacrifice/6101/status", headers=staff, json={"to": "ready_for_delivery"})
    after = client.get("/api/ops/counts", headers=staff).json()["videos"]
    assert after["ready_for_delivery"] == before["videos"]["ready_for_delivery"] + 1
    ready = client.get("/api/videos?status=ready_for_delivery", headers=staff).json()
    assert any(x["kind"] == "sacrifice" and x["number"] == 6101 for x in ready)


def test_contractors_and_viewers_blocked(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    _new_well(client, staff, 7204)
    mid = _up(client, staff, "well", 7204, _mp4(44)).json()["current_media_id"]
    for who in ("p1@hayah.local", "viewer@hayah.local"):
        h = login(client, who)
        assert client.get("/api/videos/order/well/7204", headers=h).status_code == 403
        assert client.get(f"/api/videos/file/{mid}/link", headers=h).status_code == 403
        assert _up(client, h, "well", 7204, _mp4(45)).status_code == 403
        assert client.get("/api/ops/counts", headers=h).json() == {}


def test_waiting_for_video_follows_the_plaque(client, seeded, mocks):
    from tests.test_plaque_flow import _save
    staff = login(client, "staff@hayah.local")
    _new_well(client, staff, 7205, dedication="المرحوم أحمد محمد")
    w0 = client.get("/api/ops/counts", headers=staff).json()["videos"]["waiting_upload"]
    assert _save(client, staff, 7205, {"name": "المرحوم أحمد محمد"}).status_code == 201
    pid = client.get("/api/plaques/order/well/7205", headers=staff).json()["id"]
    assert client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "awaiting_customer"}).status_code == 200
    assert _save(client, staff, 7205, {"name": "المرحوم أحمد محمد"}, approve=True).status_code == 201
    con = client.get("/api/contractors", headers=staff).json()[0]["id"]
    assert client.post(f"/api/plaques/{pid}/send-to-contractor", headers=staff, json={"contractor_id": con, "country": "Pakistan"}).status_code == 403
    mgr = login(client, "manager@hayah.local")
    assert client.post(f"/api/plaques/{pid}/send-to-contractor", headers=mgr, json={"contractor_id": con, "country": "Pakistan"}).status_code == 200
    assert client.get("/api/ops/counts", headers=staff).json()["videos"]["waiting_upload"] == w0 + 1
    assert any(x["number"] == 7205 for x in client.get("/api/videos?status=waiting", headers=staff).json())
    _up(client, staff, "well", 7205, _mp4(55))
    assert client.get("/api/ops/counts", headers=staff).json()["videos"]["waiting_upload"] == w0

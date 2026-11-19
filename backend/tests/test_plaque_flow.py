"""Plaque workflow: automatic draft, missing information, customer approval, approved section,
sending to the contractor, versions, prayers rules and employee access."""
import io
import json
import zipfile

import pytest

from app.services.prayers import classify
from tests.conftest import login
from tests.test_ui_upgrade import _tiny_png


@pytest.mark.parametrize("text,kind,sure", [
    ("محمد أحمد", "neutral", False),                     # a bare name: gender not guessed
    ("أم أحمد", "living_f", True),
    ("المرحوم أحمد محمد", "dead_m", True),
    ("المرحومة فاطمة أحمد", "dead_f", True),
    ("فاعل خير", "anon_m", True),
    ("عن أرواح موتانا وموتى المسلمين", "dead_group", True),
    ("عن روح والدتي", "dead_f", True),
    ("عن روح سامي", "dead_neutral", False),
    ("عائلة الحوراني", "living_group", True),
    ("أبو خالد", "living_m", True),
    ("", "neutral", False),
])
def test_prayer_rules(text, kind, sure):
    c = classify(text)
    assert (c["kind"], c["sure"]) == (kind, sure)


def _new_well(client, h, well_id, **kw):
    r = client.post("/api/projects", headers=h, json={"well_id": well_id, "well_type": "يدوي", "country": "Pakistan", **kw})
    assert r.status_code == 201, r.text
    return client.get(f"/api/plaques/order/well/{well_id}", headers=h).json()


def _save(client, h, well_id, design_extra=None, approve=False):
    d = {"template": "hayah_square", "size": "digital", "well_id": str(well_id), **(design_extra or {})}
    return client.post(f"/api/projects/{well_id}/plaques", headers=h,
                       data={"design": json.dumps(d, ensure_ascii=False), "approve": "true" if approve else "false"},
                       files={"file": ("p.png", io.BytesIO(_tiny_png(500 + well_id % 97)), "image/png")})


def test_new_order_gets_draft_and_missing_is_listed(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    pl = _new_well(client, staff, 7001, customer_name="محمد أحمد")
    assert pl["status"] == "draft" and pl["missing"] == ["gender_state"]
    assert pl["versions"][0]["version"] == 1 and pl["versions"][0]["source"] == "auto" and not pl["versions"][0]["has_file"]
    assert pl["design"]["auto"] and pl["design"]["dua_sure"] is False
    # nothing complete -> cannot go to the customer
    r = client.post(f"/api/plaques/{pl['id']}/status", headers=staff, json={"to": "awaiting_customer"})
    assert r.status_code == 409
    # the employee confirms "living, male" in the designer and saves -> ready for review
    assert _save(client, staff, 7001, {"name": "محمد أحمد", "dua_kind": "living_m", "dua_sure": True}).status_code == 201
    pl = client.get(f"/api/plaques/{pl['id']}", headers=staff).json()
    assert pl["status"] == "ready_for_review" and pl["missing"] == [] and pl["honoree_gender"] == "male"
    assert [v["version"] for v in pl["versions"]] == [2, 1]
    # version 1 (the automatic draft) is kept unchanged
    assert pl["versions"][1]["design"]["auto"] is True


def test_full_path_to_contractor(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    pl = _new_well(client, staff, 7002, dedication="المرحومة فاطمة أحمد")
    assert pl["status"] == "ready_for_review" and pl["honoree_state"] == "deceased"
    assert _save(client, staff, 7002, {"name": "المرحومة فاطمة أحمد"}).status_code == 201
    pid = pl["id"]
    c = client.get("/api/plaques/counts", headers=staff).json()
    assert c["needs_confirmation"] == 1 and c["ready_for_contractor"] == 0
    assert client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "awaiting_customer"}).json()["status"] == "awaiting_customer"
    r = client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "needs_changes", "note": "تكبير الاسم"}).json()
    assert r["status"] == "needs_changes" and r["customer_note"] == "تكبير الاسم"
    assert _save(client, staff, 7002, {"name": "المرحومة فاطمة أحمد", "name_size": 120}).status_code == 201
    client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "awaiting_customer"})
    r = client.post(f"/api/plaques/{pid}/status", headers=staff, json={"to": "customer_approved"}).json()
    # customer approval moves it straight to the approved section
    assert r["status"] == "approved_for_contractor" and r["file_version_id"]
    mgr = login(client, "manager@hayah.local")
    c = client.get("/api/plaques/counts", headers=staff).json()
    assert c["needs_confirmation"] == 0 and c["ready_for_contractor"] == 0  # the manager's step: not counted for employees
    assert client.get("/api/plaques/counts", headers=mgr).json()["ready_for_contractor"] == 1
    assert client.get("/api/plaques?group=approved", headers=staff).status_code == 403
    assert [x["id"] for x in client.get("/api/plaques?group=approved", headers=mgr).json()] == [pid]
    # employees: out of their lists and search, but still open by number; managers see it everywhere
    assert 7002 not in [p["well_id"] for p in client.get("/api/projects", headers=staff, params={"page_size": 500}).json()["items"]]
    assert 7002 not in [p["well_id"] for p in client.get("/api/projects", headers=staff, params={"q": "7002"}).json()["items"]]
    assert 7002 in [p["well_id"] for p in client.get("/api/projects", headers=mgr, params={"page_size": 500}).json()["items"]]
    p = client.get("/api/projects/7002", headers=staff).json()
    assert p["plaque_status"] == "approved" and p["plaque_media_id"]
    # download one and several
    f = client.get(f"/api/plaques/{pid}/file?download=true", headers=staff)
    assert f.status_code == 200 and f.content.startswith(b"\x89PNG") and "attachment" in f.headers["content-disposition"]
    z = client.post("/api/plaques/zip", headers=staff, json={"ids": [pid]})
    assert len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 1
    # stays in the list until sending is recorded; needs a contractor and country
    cons = client.get("/api/contractors", headers=staff).json()
    assert client.post(f"/api/plaques/{pid}/send-to-contractor", headers=staff, json={"contractor_id": cons[0]["id"]}).status_code == 403
    assert client.post(f"/api/plaques/{pid}/send-to-contractor", headers=mgr, json={"contractor_id": 999999}).status_code == 422
    r = client.post(f"/api/plaques/{pid}/send-to-contractor", headers=mgr,
                    json={"contractor_id": cons[0]["id"], "country": "Pakistan", "sent_on": "2026-11-19"}).json()
    assert r["status"] == "sent_to_contractor" and r["contractor"]["id"] == cons[0]["id"] and r["sent_to_contractor_on"] == "2026-11-19"
    assert client.get("/api/plaques/counts", headers=staff).json()["ready_for_contractor"] == 0
    assert client.get("/api/projects/7002", headers=staff).json()["contractor_id"] == cons[0]["id"]
    # once sent and assigned, the employee sees it again (lists and the contractor's page)
    assert 7002 in [p["well_id"] for p in client.get("/api/projects", headers=staff, params={"contractor_id": cons[0]["id"]}).json()["items"]]
    assert 7002 in [p["well_id"] for p in client.get("/api/projects", headers=staff, params={"page_size": 500}).json()["items"]]
    # every step is on the order's timeline
    events = [e["event_type"] for e in client.get("/api/projects/7002/history", headers=staff).json()["events"]]
    assert "plaque_draft_created" in events and "plaque_sent_to_contractor" in events and events.count("plaque_status") >= 5


def test_sacrifice_plaque_flow_and_sample_or_import_get_no_draft(client, seeded, mocks):
    mgr, staff = login(client, "manager@hayah.local"), login(client, "staff@hayah.local")
    r = client.post("/api/sacrifices", headers=mgr, json={"sacrifice_no": 6001, "donor_name": "فاعل خير", "animal_type": "خروف",
                                                         "customer_phone": "+962 0791234567"})
    assert r.status_code == 201 and r.json()["customer_phone_e164"] == "+962791234567"
    pl = client.get("/api/plaques/order/sacrifice/6001", headers=staff).json()
    assert pl["kind"] == "sacrifice" and pl["anonymous"] and pl["missing"] == ["country"]
    d = {"template": "sacrifice_portrait", "size": "digital", "name": "فاعل خير", "sacrifice_no": "6001"}
    r = client.post("/api/plaques/sacrifices/6001", headers=staff, data={"design": json.dumps(d, ensure_ascii=False), "approve": "true"},
                    files={"file": ("p.png", io.BytesIO(_tiny_png(77)), "image/png")})
    assert r.status_code == 409  # country still missing: no approval with incomplete information
    # seeded sample orders never get automatic drafts
    assert client.get("/api/plaques/order/well/9001", headers=staff).json() is None
    assert client.post("/api/plaques/order/well/9001", headers=staff).status_code == 201


def test_plaque_api_never_returns_money_and_contractors_are_blocked(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    _new_well(client, staff, 7003, customer_name="أم أحمد", sale_amount="240.00")
    txt = json.dumps(client.get("/api/plaques?group=confirm", headers=staff).json())
    assert "240" not in txt and "cost" not in txt and "sale" not in txt
    for who in ("p1@hayah.local", "viewer@hayah.local"):
        h = login(client, who)
        assert client.get("/api/plaques/counts", headers=h).status_code == 403
        assert client.get("/api/plaques?group=approved", headers=h).status_code == 403

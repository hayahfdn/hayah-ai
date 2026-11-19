"""The WhatsApp icon on a prepared plaque: the message text with the delivery time per order type,
nothing sent automatically, and tapping it logged and moving the plaque to the customer."""
from app.services.plaque_whatsapp import TEXT
from tests.conftest import login
from tests.test_plaque_flow import _new_well, _save


def test_text_per_well_type(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    for n, typ, time in [(7401, "يدوي", "١٠ أيام"), (7402, "متوسط", "١٠ أيام"), (7403, "عميق", "١٥ يوم"), (7404, "شمسي", "٢٠ يوم")]:
        r = client.post("/api/projects", headers=staff, json={"well_id": n, "well_type": typ, "country": "Pakistan",
                                                               "dedication": "المرحوم أحمد", "customer_phone": "+962 79 123 4567"})
        assert r.status_code == 201, r.text
        w = client.get(f"/api/plaques/order/well/{n}", headers=staff).json()["whatsapp"]
        assert w["time"] == time and w["text"] == TEXT.format(time=time) and w["phone"] == "+962791234567"
        assert w["text"].startswith("السلام عليكم\nتم استلام طلبك وإعداد اللوحة سيتم التنفيذ ان شاء الله خلال ")
        assert w["problems"] == ["no_file"]  # the plaque is not saved yet


def test_sacrifice_is_48_hours(client, seeded, mocks):
    mgr = login(client, "manager@hayah.local")
    r = client.post("/api/sacrifices", headers=mgr, json={"sacrifice_no": 6401, "donor_name": "فاعل خير", "animal_type": "خروف",
                                                          "customer_phone": "+447700900123"})
    assert r.status_code in (200, 201), r.text
    w = client.get("/api/plaques/order/sacrifice/6401", headers=mgr).json()["whatsapp"]
    assert w["time"] == "٤٨ ساعة" and w["text"].endswith("خلال ٤٨ ساعة")


def test_tap_logs_and_moves_to_customer(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    pl = _new_well(client, staff, 7405, dedication="المرحومة فاطمة أحمد")
    # no phone and no saved file: the icon is not ready and the server refuses
    assert set(pl["whatsapp"]["problems"]) == {"no_file", "no_phone"}
    assert client.post(f"/api/plaques/{pl['id']}/whatsapp-opened", headers=staff).status_code == 409
    client.patch(f"/api/projects/7405", headers=staff, json={"customer_phone": "+962 79 123 4567"})
    assert _save(client, staff, 7405, {"name": "المرحومة فاطمة أحمد"}).status_code == 201
    pl = client.get(f"/api/plaques/{pl['id']}", headers=staff).json()
    assert pl["whatsapp"]["problems"] == [] and pl["status"] == "ready_for_review"
    r = client.post(f"/api/plaques/{pl['id']}/whatsapp-opened", headers=staff)
    assert r.status_code == 200 and r.json()["status"] == "awaiting_customer" and r.json()["sent_to_customer_at"]
    # tapping again keeps the state and is noted again
    assert client.post(f"/api/plaques/{pl['id']}/whatsapp-opened", headers=staff).json()["status"] == "awaiting_customer"
    ev = client.get("/api/projects/7405/history", headers=staff).json()["events"]
    assert any("WhatsApp" in (e.get("summary") or "") for e in ev)

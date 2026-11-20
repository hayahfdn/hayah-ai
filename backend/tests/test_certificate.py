"""«شهادة وقفية»: defaults from the order, saved design, sent log, roles, and no finance figures."""
import io

from tests.conftest import login


def test_defaults_save_and_sent(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    r = client.post("/api/projects", headers=staff, json={
        "well_id": 1335, "well_type": "يدوي", "country": "Pakistan", "customer_name": "أبو محمد",
        "dedication": "محمد بشير بنور مروان\nجودية علي ميلاد حنيش", "customer_phone": "+962 79 123 4567",
        "completion_date": "2026-10-05"})
    assert r.status_code == 201, r.text
    c = client.get("/api/certificates/well/1335", headers=staff)
    assert c.status_code == 200, c.text
    c = c.json()
    d = c["defaults"]
    assert d["names"] == "محمد بشير بنور مروان\nجودية علي ميلاد حنيش"
    assert d["project_type"] == "حفر بئر مياه" and d["month"] == "أكتوبر" and d["year"] == "2026"
    assert d["number"] == "1335" and d["country"] == "Pakistan" and d["date_guessed"] is False
    assert c["design"] is None and c["customer_phone_e164"] == "+962791234567"
    assert c["video"]["status"] == "not_uploaded" and c["video"]["media_id"] is None
    assert "cost" not in str(c) and "sale_amount" not in str(c)

    # save an edited design: unknown keys are dropped
    s = client.put("/api/certificates/well/1335", headers=staff,
                   json={"design": {"names": "فاعل خير", "country": "باكستان", "evil": "x"}})
    assert s.status_code == 200, s.text
    assert s.json()["design"] == {"names": "فاعل خير", "country": "باكستان"} and s.json()["saved_by"]

    # the final video is offered with the certificate once uploaded
    mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + bytes(range(200))
    up = client.post("/api/videos/order/well/1335", headers=staff, files={"file": ("f.mp4", io.BytesIO(mp4), "video/mp4")})
    assert up.status_code == 201, up.text
    c = client.get("/api/certificates/well/1335", headers=staff).json()
    assert c["video"]["media_id"] and c["video"]["mime_type"] == "video/mp4"

    sent = client.post("/api/certificates/well/1335/sent", headers=staff, json={"with_video": True, "method": "share"})
    assert sent.status_code == 200 and sent.json()["sent_at"]
    events = client.get("/api/projects/1335/history", headers=staff).json()["events"]
    kinds = [e["event_type"] for e in events]
    assert "certificate_saved" in kinds and "certificate_sent" in kinds


def test_solar_type_and_guessed_date(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    client.post("/api/projects", headers=staff, json={"well_id": 1336, "well_type": "شمسي", "country": "Nepal", "customer_name": "سارة"})
    d = client.get("/api/certificates/well/1336", headers=staff).json()["defaults"]
    assert d["project_type"] == "حفر بئر مياه بالطاقة الشمسية" and d["names"] == "سارة" and d["date_guessed"] is True
    assert client.get("/api/certificates/well/999999", headers=staff).status_code == 404


def test_roles(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    client.post("/api/projects", headers=staff, json={"well_id": 1337, "well_type": "يدوي", "country": "Pakistan"})
    assert client.get("/api/certificates/well/1337").status_code == 401
    for who in ("p1@hayah.local", "maint@hayah.local", "viewer@hayah.local"):
        try:
            h = login(client, who)
        except AssertionError:
            continue
        assert client.get("/api/certificates/well/1337", headers=h).status_code == 403


def test_names_only_one_per_line():
    """Hayah's rule: names only, each on its own line; no title, kinship, 'late' or prayer."""
    from app.services.certificate import clean_names as c
    assert c("صدقة جارية عن روح والدي المرحوم محمد أحمد ووالدتي فاطمة") == "محمد أحمد\nفاطمة"
    assert c("المرحومة الحاجة أم أحمد رحمها الله") == "أم أحمد"
    assert c("السيد خالد بن الوليد، والسيدة هند بنت عتبة") == "خالد بن الوليد\nهند بنت عتبة"
    assert c("الدكتور عبد الله") == "عبد الله"
    assert c("أخي وليد و أختي وفاء") == "وليد\nوفاء"
    assert c("ابن خالي سامي") == "سامي"
    assert c("المرحوم محمد أسكنه الله فسيح جناته") == "محمد"
    assert c("محمد بشير بنور مروان\nجودية علي ميلاد حنيش") == "محمد بشير بنور مروان\nجودية علي ميلاد حنيش"
    assert c("عن روح جدتي") == ""


def test_default_names_are_cleaned(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    client.post("/api/projects", headers=staff, json={"well_id": 1338, "well_type": "يدوي", "country": "Pakistan",
                                                      "customer_name": "أبو سامي", "dedication": "عن روح والدتي المرحومة الحاجة فاطمة علي رحمها الله"})
    assert client.get("/api/certificates/well/1338", headers=staff).json()["defaults"]["names"] == "فاطمة علي"
    client.post("/api/projects", headers=staff, json={"well_id": 1339, "well_type": "يدوي", "country": "Pakistan",
                                                      "customer_name": "السيد سامي", "dedication": "عن روح جدتي"})
    assert client.get("/api/certificates/well/1339", headers=staff).json()["defaults"]["names"] == "سامي"

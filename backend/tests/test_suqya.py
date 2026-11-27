"""«سقيا الماء في الحرم»: numbering, order fields, plaque design, sent log, backgrounds and roles."""
from tests.conftest import login


def test_numbers_design_and_sent(client, seeded):
    staff = login(client, "staff@hayah.local")
    r = client.get("/api/suqya", headers=staff)
    assert r.status_code == 200 and r.json() == {"items": [], "next_no": 1}

    # the first number can be typed (Hayah is at 104); the next ones follow it
    a = client.post("/api/suqya", headers=staff, json={"suqya_no": 104, "quantity": 100, "donor_name": "خيرة الزهراني",
                                                       "dua": "حفظها الله", "customer_phone": "+962 79 123 4567",
                                                       "order_date": "2026-11-20", "sale_price": 50})
    assert a.status_code == 201, a.text
    a = a.json()
    assert a["suqya_no"] == 104 and a["month_text"] == "نوفمبر 2026" and a["customer_phone_e164"] == "+962791234567"
    assert a["sale_price"] == 50 and "cost" not in a
    b = client.post("/api/suqya", headers=staff, json={"donor_name": "فاعل خير"}).json()
    assert b["suqya_no"] == 105 and b["quantity"] == 100
    assert client.post("/api/suqya", headers=staff, json={"suqya_no": 104}).status_code == 409
    assert client.get("/api/suqya", headers=staff).json()["next_no"] == 106
    assert [i["suqya_no"] for i in client.get("/api/suqya?q=الزهراني", headers=staff).json()["items"]] == [104]

    p = client.patch("/api/suqya/105", headers=staff, json={"quantity": 250, "dua": "رحمه الله"})
    assert p.status_code == 200 and p.json()["quantity"] == 250 and p.json()["donor_name"] == "فاعل خير"

    d = client.put("/api/suqya/104/design", headers=staff, json={"design": {"name": "خيرة", "bg": "haram", "evil": "x"}})
    assert d.status_code == 200 and d.json()["design"] == {"name": "خيرة", "bg": "haram"} and d.json()["plaque_saved_by"]
    s = client.post("/api/suqya/104/sent", headers=staff, json={"method": "share"})
    assert s.status_code == 200 and s.json()["sent_at"]

    # backgrounds: built-in Haram plus uploads
    bg = client.post("/api/suqya/backgrounds", headers=staff, json={"name": "my bg", "data_url": "data:image/png;base64,iVBORw0KGgo="})
    assert bg.status_code == 201
    assert [i["id"] for i in client.get("/api/suqya/backgrounds", headers=staff).json()][0] == "haram"
    assert client.post("/api/suqya/backgrounds", headers=staff, json={"name": "x", "data_url": "data:text/html;base64,AAAA"}).status_code == 415

    # only managers delete
    assert client.delete("/api/suqya/105", headers=staff).status_code == 403
    assert client.delete("/api/suqya/105", headers=login(client, "admin@hayah.local")).status_code == 204
    assert client.get("/api/suqya/105", headers=staff).status_code == 404


def test_contractors_cannot_see(client, seeded):
    staff = login(client, "staff@hayah.local")
    client.post("/api/suqya", headers=staff, json={"donor_name": "x"})
    from app.db import SessionLocal
    from app.models import Role, User
    with SessionLocal() as db:
        c = db.query(User).filter(User.role == Role.contractor).first()
    if c:
        h = login(client, c.email)
        assert client.get("/api/suqya", headers=h).status_code == 403

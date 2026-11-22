"""«صيغة عقد»: facts from the order, invoice number given once, Hayah's phone from Settings, roles,
and no cost or profit anywhere in it."""
from tests.conftest import login


def test_well_contract_invoice_and_settings(client, seeded, mocks, db):
    staff = login(client, "staff@hayah.local")
    mgr = login(client, "admin@hayah.local")
    r = client.post("/api/projects", headers=mgr, json={
        "well_id": 1401, "well_type": "عميق", "country": "Pakistan", "customer_name": "أبو محمد",
        "extras": "خزان, سيراميك", "sale_amount": "850", "cost": "400", "order_date": "2026-11-01"})
    assert r.status_code == 201, r.text
    c = client.get("/api/contracts/well/1401", headers=staff)
    assert c.status_code == 200, c.text
    c = c.json()
    f = c["facts"]
    assert f["number"] == 1401 and f["owner"] == "أبو محمد" and f["well_type"] == "عميق" and f["extras"] == "خزان, سيراميك"
    assert f["amount"] == "850.00" and f["currency"] == "USD"
    assert "expected_delivery" not in f  # typed by hand on each contract (Hayah's rule)
    assert c["invoice_no"] is None and c["hayah_phone"] == "+447350295849"
    assert "400" not in str(c) and "cost" not in str(c) and "profit" not in str(c)

    s1 = client.put("/api/contracts/well/1401", headers=staff, json={"design": {"owner": "محمد", "evil": "x"}})
    assert s1.status_code == 200, s1.text
    inv = s1.json()["invoice_no"]
    assert inv and inv.startswith("HF-") and inv.endswith("-0001") and s1.json()["design"] == {"owner": "محمد"}
    s2 = client.put("/api/contracts/well/1401", headers=staff, json={"design": {"owner": "محمد علي"}})
    assert s2.json()["invoice_no"] == inv and s2.json()["design"]["owner"] == "محمد علي"

    # only managers set the phone and period; everyone who prepares contracts reads them
    assert client.put("/api/contracts/settings", headers=staff, json={"hayah_phone": "+1"}).status_code == 403
    ok = client.put("/api/contracts/settings", headers=mgr, json={"hayah_phone": "+962 7 9000 0000", "invoice_prefix": "HF"})
    assert ok.status_code == 200, ok.text
    c = client.get("/api/contracts/well/1401", headers=staff).json()
    assert c["hayah_phone"] == "+962 7 9000 0000"

    # a second well gets the next number
    client.post("/api/projects", headers=staff, json={"well_id": 1402, "well_type": "يدوي"})
    from datetime import date
    from app.models import Project
    p = db.query(Project).filter(Project.well_id == 1402).one()
    p.delivery_date = date(2026, 12, 10)
    db.commit()
    c2 = client.get("/api/contracts/well/1402", headers=staff).json()
    assert client.put("/api/contracts/well/1402", headers=staff, json={"design": {}}).json()["invoice_no"].endswith("-0002")


def test_sacrifice_contract_and_roles(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    r = client.post("/api/sacrifices", headers=login(client, "admin@hayah.local"), json={"sacrifice_no": 5501, "donor_name": "سارة", "animal_type": "خروف",
                                                           "sale_price": "120", "cost": "70", "order_date": "2026-11-10"})
    assert r.status_code in (200, 201), r.text
    c = client.get("/api/contracts/sacrifice/5501", headers=staff).json()
    assert c["facts"]["animal_type"] == "خروف" and c["facts"]["amount"] == "120.00" and "70.00" not in str(c)
    assert client.get("/api/contracts/sacrifice/999999", headers=staff).status_code == 404
    assert client.get("/api/contracts/other/1", headers=staff).status_code == 404
    assert client.get("/api/contracts/sacrifice/5501").status_code == 401
    for who in ("p1@hayah.local", "viewer@hayah.local"):
        try:
            h = login(client, who)
        except AssertionError:
            continue
        assert client.get("/api/contracts/sacrifice/5501", headers=h).status_code == 403

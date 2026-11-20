"""Hayah's 20 Nov 2026 request: add-ons on wells and sacrifices, the sheep add-on as a linked
sacrifice at 99 USD (counted once), projects newest-created first with a re-sort button, the
WhatsApp button's real cause (country) fixed, phone numbers to international form, per-user zoom."""
from decimal import Decimal

from app.services import addons, phones
from tests.conftest import login
from tests.test_plaque_flow import _save


def _sacs_of(client, mgr, well_id):
    return [s for s in client.get("/api/sacrifices", headers=mgr).json() if s["parent_well_id"] == well_id]


def test_addon_text_helpers():
    assert addons.split("خزان، سيراميك + خروف") == ["خزان", "سيراميك", "خروف"]
    assert addons.normalize("خزان، سيراميك") == "خزان, سيراميك"
    assert addons.sheep_count("خزان, خروف") == 1 and addons.sheep_count("خروف ×2") == 2
    assert addons.sheep_count("Sheep (3), tank") == 3 and addons.sheep_count("سيراميك") == 0 and addons.sheep_count(None) == 0


def test_project_without_and_with_several_addons(client, seeded):
    staff = login(client, "staff@hayah.local")
    mgr = login(client, "manager@hayah.local")
    r = client.post("/api/projects", headers=staff, json={"well_id": 8201, "well_type": "يدوي"})
    assert r.status_code == 201 and r.json()["extras"] is None and r.json()["addon_sacrifices"] == []
    r = client.post("/api/projects", headers=staff, json={"well_id": 8202, "well_type": "عميق", "extras": "خزان، سيراميك"})
    p = r.json()
    assert p["extras"] == "خزان, سيراميك" and p["well_type"] == "عميق"  # separate fields, never merged
    assert _sacs_of(client, mgr, 8202) == []
    lists = client.get("/api/settings/lists", headers=staff).json()
    assert lists["well_addons"] == ["خزان", "سيراميك", "خروف"] and lists["sacrifice_addons"] == ["إطعام"]


def test_sheep_addon_becomes_linked_sacrifice_once_at_99(client, seeded):
    staff = login(client, "staff@hayah.local")
    mgr = login(client, "manager@hayah.local")
    r = client.post("/api/projects", headers=staff, json={
        "well_id": 8203, "well_type": "يدوي", "extras": "خزان, خروف", "sale_amount": "329.00", "customer_name": "أم محمد",
        "dedication": "صدقة عن والدي", "customer_phone": "+962791234567", "order_date": "2026-11-20"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert len(p["addon_sacrifices"]) == 1 and p["addon_sacrifices"][0]["sale_price"] == "99.00"
    assert "cost" not in p["addon_sacrifices"][0]  # employees only ever see the selling price
    sac = _sacs_of(client, mgr, 8203)
    assert len(sac) == 1
    s = sac[0]
    assert s["sale_price"] == "99.00" and s["animal_type"] == "خروف" and s["dedication"] == "صدقة عن والدي"
    assert s["customer_phone_e164"] == "+962791234567" and s["order_date"] == "2026-11-20" and s["intention"] == "صدقة"
    # saving the well again (any change) does not create a second sacrifice
    client.patch("/api/projects/8203", headers=staff, json={"notes": "x", "extras": "خروف, خزان"})
    assert len(_sacs_of(client, mgr, 8203)) == 1
    # the sacrifice is a normal one: editable on the sacrifices page
    r = client.patch(f"/api/sacrifices/{s['sacrifice_no']}", headers=mgr, json={"delivery_date": "2026-11-22", "extras": "إطعام"})
    assert r.status_code == 200 and r.json()["extras"] == "إطعام" and r.json()["parent_well_id"] == 8203
    # money counted once: well 329 (well + tank), sheep 99 on the sacrifice
    summ = client.get("/api/finance/summary", headers=mgr).json()
    assert summ is not None
    from app.db import SessionLocal
    from app.models import Project, Sacrifice
    db = SessionLocal()
    w = db.query(Project).filter_by(well_id=8203).one()
    total = (w.sale_amount or 0) + sum(x.sale_price for x in db.query(Sacrifice).filter_by(parent_project_id=w.id))
    assert total == Decimal("428.00")
    db.close()
    # a second sheep added later creates exactly one more; removing sheep never deletes a sacrifice
    client.patch("/api/projects/8203", headers=staff, json={"extras": "خزان, خروف ×2"})
    assert len(_sacs_of(client, mgr, 8203)) == 2
    client.patch("/api/projects/8203", headers=staff, json={"extras": "خزان"})
    assert len(_sacs_of(client, mgr, 8203)) == 2
    ev = client.get("/api/projects/8203/history", headers=staff).json()["events"]
    assert any(e["event_type"] == "addon_sacrifice_created" for e in ev)


def test_sacrifice_with_feeding_addon(client, seeded):
    mgr = login(client, "manager@hayah.local")
    r = client.post("/api/sacrifices", headers=mgr, json={"sacrifice_no": 6501, "animal_type": "خروف", "extras": "إطعام"})
    assert r.status_code == 201 and r.json()["extras"] == "إطعام"
    r = client.patch("/api/sacrifices/6501", headers=mgr, json={"extras": ""})
    assert r.status_code == 200


def test_projects_newest_created_first_and_stable_and_resort(client, seeded):
    mgr = login(client, "manager@hayah.local")
    staff = login(client, "staff@hayah.local")
    for wid, day in [(8301, "2026-11-19"), (8302, "2026-01-01"), (8303, "2026-11-01")]:
        assert client.post("/api/projects", headers=staff, json={"well_id": wid, "order_date": day}).status_code == 201

    def order():
        return [p["well_id"] for p in client.get("/api/projects", headers=mgr, params={"page_size": 500}).json()["items"] if 8300 < p["well_id"] < 8400]
    assert order() == [8303, 8302, 8301]  # the last one added is on top
    # editing, changing status or the order date never moves a project
    client.patch("/api/projects/8301", headers=staff, json={"construction_status": "in_progress", "order_date": "2026-12-01"})
    assert order() == [8303, 8302, 8301]
    assert client.post("/api/projects", headers=staff, json={"well_id": 8304}).status_code == 201
    assert order()[0] == 8304
    r = client.post("/api/projects/resort", headers=staff)
    assert r.status_code == 200 and order() == [8304, 8303, 8302, 8301]
    assert client.post("/api/projects/resort", headers=login(client, "p1@hayah.local")).status_code == 403


def test_plaque_flag_counts_as_country_and_missing_is_refreshed(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    # a new order has no contractor yet, so no country: the old code kept the button blocked (ناقص: الدولة)
    r = client.post("/api/projects", headers=staff, json={"well_id": 8401, "well_type": "شمسي", "dedication": "المرحوم أحمد",
                                                           "customer_phone": "07911123456", "customer_phone_country": "GB"})
    assert r.status_code == 201
    pl = client.get("/api/plaques/order/well/8401", headers=staff).json()
    assert "country" in pl["missing"]
    assert _save(client, staff, 8401, {"name": "المرحوم أحمد", "flag": "PK", "dua_kind": "deceased_m"}).status_code == 201
    pl = client.get(f"/api/plaques/{pl['id']}", headers=staff).json()
    assert "country" not in pl["missing"] and pl["whatsapp"]["problems"] == []
    assert pl["whatsapp"]["phone"] == "+447911123456"
    r = client.post(f"/api/plaques/{pl['id']}/whatsapp-opened", headers=staff)
    assert r.status_code == 200 and r.json()["status"] == "awaiting_customer"


def test_whatsapp_problem_names_what_is_wrong_with_the_phone(client, seeded, mocks):
    staff = login(client, "staff@hayah.local")
    client.post("/api/projects", headers=staff, json={"well_id": 8402, "well_type": "يدوي", "dedication": "المرحوم علي",
                                                      "customer_phone": "0791234567"})
    pl = client.get("/api/plaques/order/well/8402", headers=staff).json()
    assert "phone_country" in pl["whatsapp"]["problems"]
    client.patch("/api/projects/8402", headers=staff, json={"customer_phone_country": "JO"})
    pl = client.get("/api/plaques/order/well/8402", headers=staff).json()
    assert "phone_country" not in pl["whatsapp"]["problems"] and pl["whatsapp"]["phone"] == "+962791234567"


def test_phone_numbers_from_different_countries():
    cases = [
        ("+44 7911 123456", None, "+447911123456"), ("00962791234567", None, "+962791234567"),
        ("447911123456", None, "+447911123456"),       # country code without +
        ("966501234567", None, "+966501234567"), ("971501234567", None, "+971501234567"),
        ("0501234567", "SA", "+966501234567"), ("07911 123456", "GB", "+447911123456"),
        ("٠٧٩١٢٣٤٥٦٧", "JO", "+962791234567"),          # Arabic digits
        ("+1 415 555 2671", None, "+14155552671"), ("+92 300 1234567", None, "+923001234567"),
        ("+20 100 123 4567", None, "+201001234567"), ("+974 3312 3456", None, "+97433123456"),
    ]
    for raw, country, want in cases:
        r = phones.normalize(raw, country)
        assert r["e164"] == want and r["status"] == "valid", (raw, r)
    assert phones.normalize("0791234567")["status"] == "needs_country"
    # the customer's own country from the order completes a local number
    assert phones.normalize("0791234567", fallback_country="JO")["e164"] == "+962791234567"


def test_shopify_billing_country_completes_local_number():
    from app.services import shopify as svc
    o = svc.normalize_graphql({"id": "gid://shopify/Order/1", "name": "#1300", "billingAddress": {"name": "x", "phone": None, "countryCodeV2": "GB"},
                               "lineItems": {"nodes": []}})
    assert o["country_code"] == "GB"
    o = svc.normalize_rest({"id": 1, "name": "#1300", "billing_address": {"country_code": "JO"}, "line_items": []})
    assert o["country_code"] == "JO"


def test_zoom_is_saved_per_user(client, seeded):
    staff = login(client, "staff@hayah.local")
    mgr = login(client, "manager@hayah.local")
    assert client.patch("/api/auth/me/preferences", headers=staff, json={"ui_zoom": 125}).json()["ui_zoom"] == 125
    assert client.get("/api/auth/me", headers=staff).json()["ui_zoom"] == 125
    assert client.get("/api/auth/me", headers=mgr).json()["ui_zoom"] is None
    assert client.patch("/api/auth/me/preferences", headers=staff, json={"ui_zoom": 130}).status_code == 422
    assert client.patch("/api/auth/me/preferences", headers=staff, json={"ui_zoom": 100}).json()["ui_zoom"] is None


def test_plaque_image_library(client, seeded):
    staff = login(client, "staff@hayah.local")
    lib = client.get("/api/plaque-images", headers=staff).json()
    assert lib[0]["id"] == "solar-well" and lib[0]["src"] == "/plaque-images/solar-well.png"
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    r = client.post("/api/plaque-images", headers=staff, json={"name": "بئر شمسي 2", "data_url": png})
    assert r.status_code == 201
    assert any(i["id"] == r.json()["id"] for i in client.get("/api/plaque-images", headers=staff).json())
    assert client.post("/api/plaque-images", headers=staff, json={"name": "x", "data_url": "data:text/html;base64,AAAA"}).status_code == 415
    assert client.get("/api/plaque-images", headers=login(client, "p1@hayah.local")).status_code == 403

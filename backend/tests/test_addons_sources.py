"""Sheep add-on becomes its own sacrifice (from order #1225), and sales sources are unified."""
from decimal import Decimal

from tests.conftest import login
from tests.test_shopify import line, order, post_webhook, run_jobs, shop  # noqa: F401  (fixture)

SHEEP_PID = 15429437489372


def _sacs(client, name):
    mgr = login(client, "manager@hayah.local")
    return [s for s in client.get("/api/sacrifices", headers=mgr).json() if s["shopify_order"] == name]


def test_two_sheep_with_one_well_make_two_sacrifices_and_resync_adds_none(client, shop):
    o = order(oid=7001, name="#1225", lines=[
        {**line(71, "خروف", 99, qty=2, props={"للمشروع": "بئر سطحي بمضخة يدوية"}), "product_id": SHEEP_PID},
        line(72, "خزان مياه إضافي", 89, props={"للمشروع": "بئر سطحي بمضخة يدوية"}),
        line(73, "بئر سطحي بمضخة يدوية", 240, props={"الإهداء": "صدقة جارية عن شيماء", "رقم الهاتف (WhatsApp)": "+972549203262"})])
    assert post_webhook(client, o).status_code == 200
    run_jobs()
    w = client.get("/api/projects/1400", headers=shop).json()
    assert w["sale_amount"] == "329.00"  # 240 + 89 tank; each sheep is its own sacrifice
    sac = _sacs(client, "#1225")
    assert sorted(s["sacrifice_no"] for s in sac) == [300, 301]
    assert all(s["sale_price"] == "99.00" and s["dedication"] == "صدقة جارية عن شيماء" for s in sac)
    # the same order again (webhook retry + sync) creates nothing new
    assert post_webhook(client, o, "orders/paid", "w9").status_code == 200
    run_jobs()
    from app.db import SessionLocal
    from app.services import shopify as svc
    db = SessionLocal()
    svc.import_order(db, svc.normalize_rest(o), source="sync")
    assert svc.split_imported_addons(db) == []
    db.commit()
    db.close()
    assert len(_sacs(client, "#1225")) == 2
    assert client.get("/api/projects/1401", headers=shop).status_code == 404


def test_orders_before_1225_keep_the_sheep_in_the_well(client, shop):
    o = order(oid=7002, name="#1216", lines=[
        line(81, "خروف", 99, props={"للمشروع": "بئر ارتوازي عميق"}),
        line(82, "بئر ارتوازي عميق", 899, props={"الإهداء": "آمال"})])
    post_webhook(client, o)
    run_jobs()
    assert client.get("/api/projects/1400", headers=shop).json()["sale_amount"] == "998.00"
    assert _sacs(client, "#1216") == []


def test_already_imported_order_is_split_once(client, shop):
    """#1225 arrived before this change: the sheep was folded into the well. The sync splits it."""
    from app.db import SessionLocal
    from app.services import shopify as svc
    o = order(oid=7003, name="#1230", lines=[
        line(91, "خروف", 99, props={"للمشروع": "بئر سطحي بمضخة يدوية"}),
        line(92, "بئر سطحي بمضخة يدوية", 240, props={"الإهداء": "محمد"})])
    db = SessionLocal()
    cfg_before = svc.config(db)
    svc.save_config(db, {"standalone_from_order": 99999}, None)  # behave like the old code
    svc.import_order(db, svc.normalize_rest(o), source="webhook")
    db.commit()
    w = db.scalar(svc.select(svc.Project).where(svc.Project.shopify_order == "#1230"))
    assert w.sale_amount == Decimal("339.00") and "خروف" in w.extras
    svc.save_config(db, {"standalone_from_order": cfg_before["standalone_from_order"]}, None)
    done = svc.split_imported_addons(db)
    db.commit()
    assert len(done) == 1
    db.refresh(w)
    assert w.sale_amount == Decimal("240.00") and "خروف" not in (w.extras or "")
    assert svc.split_imported_addons(db) == []
    db.close()
    sac = _sacs(client, "#1230")
    assert len(sac) == 1 and sac[0]["dedication"] == "محمد"


def test_feeding_and_tiles_stay_add_ons(client, shop):
    o = order(oid=7004, name="#1240", lines=[
        line(101, "إطعام", 48, variant="خروف", props={"للمشروع": "خروف"}),
        line(102, "خروف", 160, props={"الإهداء": "فاعل خير"}),
        line(103, "إضافة سيراميك للبئر", 72, variant="بئر سطحي بمضخة يدوية", props={"للمشروع": "بئر سطحي بمضخة يدوية"}),
        line(104, "بئر سطحي بمضخة يدوية", 240, props={"الإهداء": "x"})])
    post_webhook(client, o)
    run_jobs()
    sac = _sacs(client, "#1240")
    assert len(sac) == 1 and sac[0]["sale_price"] == "208.00"
    assert client.get("/api/projects/1400", headers=shop).json()["sale_amount"] == "312.00"


def test_unify_sources():
    from app.services.sales_sources import unify
    cases = {"insta ads": "Insta Ads", "Insta ads": "Insta Ads", "ads/ig": "Insta Ads", "Custom referal": "Referral",
             "customer ref": "Referral", "frind": "Referral", "reffral": "Referral", "Shopify (Instagram)": "Instagram",
             "instagram": "Instagram", "Shopify (Google)": "Google", "google": "Google", "lina": "Lina",
             "facebook": "Facebook", "Shopify (Facebook)": "Facebook", "ChatGPT": "ChatGPT", "chatgpt": "ChatGPT",
             "Shopify (ChatGPT)": "ChatGPT", "Influencer": "Influencer", "tiktok": "TikTok", "repeated": "Referral",
             "Youtube": "Other", "": "Unknown", None: "Unknown", "Shopify": "Unknown",
             "Shopify (Insta Ads · Gulf - Reels)": "Insta Ads"}
    for raw, want in cases.items():
        assert unify(raw) == want, raw


def test_shopify_ad_vs_bio_link():
    from app.services.shopify import sales_source
    ad = {"attrs": {"utm_source": "ig", "utm_medium": "Mark MD - GULF", "utm_campaign": "Gulf - Reels"}, "referrer": "https://instagram.com/"}
    tmpl = {"attrs": {"utm_source": "{{site_source_name}}"}, "referrer": "https://instagram.com/"}
    bio = {"attrs": {"utm_source": "ig", "utm_medium": "social", "utm_content": "link_in_bio"}, "referrer": "https://l.instagram.com/"}
    assert sales_source(ad) == "Shopify (Insta Ads · Gulf - Reels)"
    assert sales_source(tmpl) == "Shopify (Insta Ads)"
    assert sales_source(bio) == "Shopify (Instagram)"


def test_manager_edits_groups_and_records_follow_original_kept(client, seeded):
    mgr, staff = login(client, "manager@hayah.local"), login(client, "staff@hayah.local")
    assert client.patch("/api/projects/9001", headers=mgr, json={"sales_source": "snapchat"}).status_code == 200
    p = client.get("/api/projects/9001", headers=mgr).json()
    assert p["source_group"] == "Other" and p["sales_source"] == "snapchat"
    assert client.get("/api/admin/sales-sources", headers=staff).status_code == 403
    groups = [g for g in client.get("/api/admin/sales-sources", headers=mgr).json()["groups"] if not g["fixed"]]
    body = [{"name": g["name"], "values": g["values"]} for g in groups] + [{"name": "Snapchat", "values": ["snapchat", "snap"]}]
    r = client.put("/api/admin/sales-sources", headers=mgr, json=body)
    assert r.status_code == 200 and r.json()["records_changed"] >= 1
    p = client.get("/api/projects/9001", headers=mgr).json()
    assert p["source_group"] == "Snapchat" and p["sales_source"] == "snapchat"
    assert "Snapchat" in client.get("/api/settings/lists", headers=staff).json()["sales_sources"]
    rep = client.get("/api/reports/summary", headers=mgr).json()
    assert any(r["source"] == "Snapchat" for r in rep["by_sales_source"])


def test_lists_are_newest_first(client, seeded):
    mgr = login(client, "manager@hayah.local")
    for wid, day in [(8101, "2026-11-01"), (8102, "2026-11-15"), (8103, None), (8104, "2026-11-15")]:
        assert client.post("/api/projects", headers=mgr, json={"well_id": wid, "order_date": day}).status_code == 201
    ids = [p["well_id"] for p in client.get("/api/projects", headers=mgr, params={"page_size": 500}).json()["items"] if 8100 < p["well_id"] < 8200]
    assert ids == [8104, 8102, 8101, 8103]
    for no, day in [(5101, "2026-10-01"), (5102, "2026-11-02")]:
        client.post("/api/sacrifices", headers=mgr, json={"sacrifice_no": no, "order_date": day})
    nos = [s["sacrifice_no"] for s in client.get("/api/sacrifices", headers=mgr).json() if s["sacrifice_no"] in (5101, 5102)]
    assert nos == [5102, 5101]

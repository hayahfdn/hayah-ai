"""سقيا from Shopify: own project per unit (also as an add-on), cancelled never added, backfill, orders list."""
from tests.conftest import login
from tests.test_shopify import line, order, post_webhook, run_jobs, shop  # noqa: F401


def test_water_becomes_suqya_and_addon_price_moves(client, shop):  # noqa: F811
    staff = login(client, "staff@hayah.local")
    o = order(oid=7001, name="#1282", lines=[
        line(21, "بقرة حجم متوسط", 499, props={"الإهداء": "فاعل خير", "رقم الهاتف (WhatsApp)": "+971 507667989"}),
        line(22, "500 عبوة مياه تُوزَّع على ضيوف الرحمن", 99, props={"للمشروع": "بقرة حجم متوسط"}),
    ])
    post_webhook(client, o, wid="s1"); run_jobs()
    sq = client.get("/api/suqya", headers=staff).json()["items"]
    assert len(sq) == 1 and sq[0]["quantity"] == 500 and sq[0]["sale_price"] == 99
    assert sq[0]["donor_name"] == "فاعل خير" and sq[0]["customer_phone_e164"] == "+971507667989"
    assert sq[0]["shopify_order"] == "#1282" and sq[0]["sales_source"].startswith("Shopify")
    sac = client.get("/api/sacrifices?q=1282", headers=staff)
    # the cow keeps only its own price
    from app.db import SessionLocal
    from app.models import Sacrifice
    with SessionLocal() as db:
        s = db.query(Sacrifice).filter(Sacrifice.shopify_order == "#1282").one()
        assert float(s.sale_price) == 499
    assert sac.status_code in (200, 404, 405)

    o2 = order(oid=7002, name="#1276", lines=[line(31, "خدمة سقيا الماء لضيوف الرحمن في مكة", 29, qty=2, variant="100 عبوة")])
    post_webhook(client, o2, wid="s2"); run_jobs()
    sq = client.get("/api/suqya", headers=staff).json()["items"]
    assert [x["suqya_no"] for x in sq] == [3, 2, 1] and sq[0]["quantity"] == 100 and sq[0]["customer_name"] == "Test Donor"

    # cancelled orders are never added
    o3 = order(oid=7003, name="#1290", cancelled="2026-11-19T10:00:00+02:00", status="refunded",
               lines=[line(41, "خدمة سقيا الماء لضيوف الرحمن في مكة", 29, variant="100 عبوة")])
    post_webhook(client, o3, wid="s3"); run_jobs()
    assert len(client.get("/api/suqya", headers=staff).json()["items"]) == 3

    # the orders list: staff see it, with what was made for each order
    lst = client.get("/api/shopify/orders/list", headers=staff).json()
    names = {x["name"]: x for x in lst["orders"]}
    assert set(names) == {"#1282", "#1276", "#1290"} and names["#1290"]["cancelled"]
    assert [x["no"] for x in names["#1276"]["links"]["suqya"]] == [2, 3]
    assert names["#1282"]["phone"] == "+971 507667989" and "cost" not in str(lst)
    assert client.get("/api/shopify/orders/list?q=1276", headers=staff).json()["total"] == 1


def test_backfill_orders_seen_before(client, shop):  # noqa: F811
    """An order imported before سقيا existed: the water was an 'other' line, or folded into a well as an add-on."""
    from app.db import SessionLocal
    from app.services import shopify as svc
    o = order(oid=7101, name="#1247", lines=[
        line(51, "بئر ارتوازي عميق", 899, props={"الإهداء": "والدي", "رقم الهاتف (WhatsApp)": "+966556677452"}),
        line(52, "خدمة سقيا الماء لضيوف الرحمن في مكة", 29, variant="100 عبوة"),
        line(53, "500 عبوة مياه تُوزَّع على ضيوف الرحمن", 99, props={"للمشروع": "بئر ارتوازي عميق"}),
    ])
    real = svc.is_suqya
    svc.is_suqya = lambda line, cfg: False  # import the old way
    try:
        post_webhook(client, o, wid="b1"); run_jobs()
    finally:
        svc.is_suqya = real
    w = client.get("/api/projects/1400", headers=shop).json()
    assert float(w["sale_amount"]) == 998
    with SessionLocal() as db:
        done = svc.import_missing_suqya(db); db.commit()
        assert len(done) == 2
        assert svc.import_missing_suqya(db) == []  # once only
    w = client.get("/api/projects/1400", headers=shop).json()
    assert float(w["sale_amount"]) == 899 and "500 عبوة" not in (w["extras"] or "")
    sq = sorted(client.get("/api/suqya", headers=shop).json()["items"], key=lambda x: x["suqya_no"])
    assert [(x["quantity"], x["sale_price"]) for x in sq] == [(100, 29), (500, 99)]
    assert sq[1]["donor_name"] == "والدي"

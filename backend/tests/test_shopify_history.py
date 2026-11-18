"""Past Shopify orders are matched to the workbook rows they already are, never created twice."""
import httpx

from tests.conftest import login
from tests.test_shopify import line, order, post_webhook, run_jobs, shop  # noqa: F401  (fixture)


def _db():
    from app.db import SessionLocal
    return SessionLocal()


def _seed_workbook():
    """Rows as the workbook import makes them: no Shopify order number, workbook prices."""
    from datetime import date
    from app.services import finance as fin
    from app.services import projects as psvc
    db = _db()
    for wid, d, name, wtype, extras in [
        (901, date(2026, 10, 2), "رهف الجابر", "يدوي", None),
        (902, date(2026, 10, 2), "سالم", "عميق", "سيراميك"),
        (903, date(2026, 10, 3), "أحمد", "يدوي", None),
        (904, date(2026, 10, 3), "خالد", "يدوي", None),
    ]:
        psvc.create_project(db, {"well_id": wid, "order_date": d, "customer_name": name, "well_type": wtype,
                                 "extras": extras, "sale_amount": 140}, actor=None, source="workbook")
    fin.create_sacrifice(db, {"sacrifice_no": 77, "order_date": date(2026, 10, 5), "donor_name": "فاعل خير",
                              "animal_type": "خروف", "sale_price": 90}, actor=None, source="workbook")
    db.commit()
    db.close()


def at(day, hour="12:00:00"):
    return f"2026-{day}T{hour}+00:00"


def past_orders():
    return [
        order(9001, "#1001", created_at=at("10-02"), lines=[
            line(1, "بئر سطحي بمضخة يدوية", 240, props={"الإهداء": "صدقة جارية عن رهف الجابر حفظها الله",
                                                       "رقم الهاتف (WhatsApp)": "+971 500000009"})]),
        order(9002, "#1002", created_at=at("10-02"), lines=[
            line(2, "إضافة سيراميك للبئر", 150, variant="بئر ارتوازي عميق"),  # old order: no للمشروع property
            line(3, "بئر ارتوازي عميق", 899)]),
        order(9003, "#1003", created_at=at("10-03"), lines=[line(4, "بئر سطحي بمضخة يدوية", 240)]),
        order(9004, "#1004", created_at=at("10-03"), lines=[line(5, "بئر سطحي بمضخة يدوية", 240)]),
        order(9005, "#1005", created_at=at("10-05"), lines=[line(6, "خروف", 160, props={"الإهداء": "فاعل خير"})]),
        order(9006, "#1006", created_at=at("10-20"), lines=[
            line(7, "بئر سطحي بمضخة يدوية", 240, props={"الإهداء": "عن روح جدتي"})]),
        order(9007, "#1007", created_at=at("11-05"), lines=[line(8, "بئر سطحي بمضخة يدوية", 240)]),  # live import's
        order(9008, "#1008", created_at=at("10-04"), cancelled="2026-10-05T00:00:00Z",
              lines=[line(9, "بئر سطحي بمضخة يدوية", 240)]),
    ]


def _run(user=None):
    from app.services import shopify as sh
    from app.services import shopify_history as hist
    db = _db()
    try:
        r = hist.run(db, orders=[sh.normalize_rest(o) for o in past_orders()], user=user)
        db.commit()
        return r
    finally:
        db.close()


def test_classify_old_addons_without_property():
    from app.services import shopify as sh
    cfg = sh.DEFAULTS
    assert sh.classify({"title": "إضافة سيراميك للبئر", "variant_title": "بئر سطحي بمضخة يدوية", "props": {}}, cfg) == "addon"
    assert sh.classify({"title": "خزان مياه إضافي", "props": {}}, cfg) == "addon"
    assert sh.classify({"title": "بئر بالطاقة الشمسية", "props": {}}, cfg) == "well"
    assert sh.classify({"title": "خروف", "props": {}}, cfg) == "sacrifice"


def test_past_orders_link_to_workbook_and_never_duplicate(client, shop):
    _seed_workbook()
    r = _run()
    assert r["orders"] == 7 and r["cancelled"] == 1  # #1007 is after the start date: left to the live import
    assert (r["sure"], r["likely"], r["guess"], r["none"]) == (1, 2, 2, 1), r

    w1 = client.get("/api/projects/901", headers=shop).json()  # name match: filled
    assert w1["shopify_order"] == "#1001" and "رهف الجابر" in w1["dedication"] and w1["customer_phone"] == "+971 500000009"
    assert w1["sale_amount"] == "140.00"  # workbook price is kept
    w2 = client.get("/api/projects/902", headers=shop).json()  # only deep well that day, ceramic on both
    assert w2["shopify_order"] == "#1002"
    for wid in (903, 904):  # two identical hand wells: linked as guesses, nothing written on them
        assert client.get(f"/api/projects/{wid}", headers=shop).json()["shopify_order"] is None
    mgr = login(client, "manager@hayah.local")
    s = [x for x in client.get("/api/sacrifices", headers=mgr).json() if x["sacrifice_no"] == 77][0]
    assert s["shopify_order"] == "#1005"

    wells_before = len(client.get("/api/projects", headers=shop, params={"limit": 500}).json())
    again = _run()
    assert again["none"] == 1 and (again["sure"], again["likely"], again["guess"]) == (1, 2, 2)
    assert len(client.get("/api/projects", headers=shop, params={"limit": 500}).json()) == wells_before

    h = client.get("/api/shopify/history", headers=mgr).json()
    review = {o["name"]: o for o in h["review"]}
    assert set(review) == {"#1003", "#1004", "#1006"}
    assert review["#1006"]["status"] == "not_in_workbook" and review["#1006"]["items"][0]["dedication"] == "عن روح جدتي"

    # A later Shopify notification for a past order changes nothing.
    assert post_webhook(client, order(9006, "#1006", created_at=at("10-20"),
                                      lines=[line(7, "بئر سطحي بمضخة يدوية", 240)]), "orders/paid", "wh-old").status_code == 200
    assert run_jobs()["failed"] == 0
    assert len(client.get("/api/projects", headers=shop, params={"limit": 500}).json()) == wells_before

    # The manager adds the one that is not in the workbook; it gets the next Well ID.
    r = client.post("/api/shopify/history/add", headers=mgr, json={"order": "1006"})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == ["well 1400"]
    w = client.get("/api/projects/1400", headers=shop).json()
    assert w["shopify_order"] == "#1006" and w["dedication"] == "عن روح جدتي" and w["order_date"] == "2026-10-20"
    assert client.post("/api/shopify/history/add", headers=mgr, json={"order": "1006"}).status_code == 404
    assert _run()["none"] == 0  # stays linked on the next run

    # The manager says #1003 is really well 904: #1004's guess moves off it.
    item = review["#1003"]["items"][0]
    r = client.post("/api/shopify/history/link", headers=mgr, json={"item_id": item["id"], "number": 904})
    assert r.status_code == 200, r.text
    assert client.get("/api/projects/904", headers=shop).json()["shopify_order"] == "#1003"
    h = {o["name"]: o for o in client.get("/api/shopify/history", headers=mgr).json()["review"]}
    assert "#1003" not in h and h["#1004"]["items"][0]["match"] == "none"
    # A record linked for sure can't be taken by another order.
    r = client.post("/api/shopify/history/link", headers=mgr, json={"item_id": h["#1004"]["items"][0]["id"], "number": 904})
    assert r.status_code == 409


def test_history_roles_and_scope_check(client, shop):
    staff = login(client, "staff@hayah.local")
    assert client.get("/api/shopify/history", headers=staff).status_code == 403
    assert client.post("/api/shopify/history/add", headers=staff, json={}).status_code == 403
    mgr = login(client, "manager@hayah.local")
    assert client.post("/api/shopify/history", headers=mgr, json={}).status_code == 403  # admin only

    from app.integrations import shopify as api
    seen = []

    def handle(req: httpx.Request):
        if req.url.path == "/admin/oauth/access_token":
            seen.append("token")
            return httpx.Response(200, json={"access_token": f"tok-{len(seen)}", "expires_in": 86399})
        import json
        q = json.loads(req.content)
        if "currentAppInstallation" in q["query"]:
            scopes = ["read_orders"] + (["read_all_orders"] if req.headers["X-Shopify-Access-Token"] == "tok-2" else [])
            return httpx.Response(200, json={"data": {"currentAppInstallation": {"accessScopes": [{"handle": s} for s in scopes]}}})
        seen.append(q["variables"]["q"])
        return httpx.Response(200, json={"data": {"orders": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}})

    api.set_transport(httpx.MockTransport(handle))
    try:
        r = client.post("/api/shopify/history", headers=shop, json={})
    finally:
        api.set_transport(None)
    assert r.status_code == 200, r.text
    assert r.json()["all_orders_scope"] is True  # old cached token lacked the new scope: fetched a fresh one
    assert seen.count("token") == 2
    assert seen[-1] == "created_at:<'2026-11-01'"  # everything before the live start date

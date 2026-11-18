"""Import past Shopify orders without making a second copy of anything.

The workbook already holds most past orders, but its rows carry no Shopify order
number. So for orders created before the live start date ("Only orders from this
date") this module MATCHES each well/sacrifice unit to an existing workbook row
instead of creating one:

  sure    the workbook row has this order number, or the donor/dedication name matches
  likely  same kind and type within a day, and it is the only candidate both ways
  guess   same kind and type within a day, but several rows fit equally
  none    nothing fits: probably not in the workbook

Sure and likely matches fill only EMPTY fields on the row (order number,
dedication, phone). Guesses change nothing on the row; they only stop the order
from being created again, and are listed for a manager. Units with no match are
never created automatically: a manager presses "Add to HAYAH" (one order or all)
or links the unit to the right Well ID / sacrifice number.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models import Project, Sacrifice, ShopifyOrder, ShopifyOrderItem, User, utcnow
from app.services import finance as fin
from app.services import projects as psvc
from app.services import secrets_store
from app.services import shopify as sh
from app.services.audit import audit
from app.services.settings_store import get_setting, set_setting

HISTORY_QUERY = sh.ORDERS_QUERY.replace("sortKey: UPDATED_AT", "sortKey: CREATED_AT")
DAY_WINDOW = 1      # workbook date vs Shopify order day, for type/date matches
NAME_WINDOW = 7     # for name matches
STOP = {"صدقة", "صدقه", "جارية", "جاريه", "عن", "روح", "الى", "إلى", "من", "اهداء", "إهداء", "الاهداء",
        "الإهداء", "حفظه", "حفظها", "حفظهم", "حفظهما", "الله", "رحمه", "رحمها", "رحمهم", "رحمهما", "المرحوم", "المرحومة",
        "المرحومه", "والدي", "والدتي", "والدى", "امي", "أمي", "ابي", "أبي", "ابوي", "اختي", "أختي", "اخي", "أخي", "زوجي",
        "زوجتي", "فاعل", "خير", "بن", "بنت", "ابن", "ال", "اذكروها", "اذكروه", "بدعوة", "الحاج", "الحاجة", "عائلة",
        "وعيالها", "عيالها", "اولاد", "أولاد", "ابنتكم", "الأخت", "الاخت", "الأخ", "الاخ", "شكرا", "لله", "فريق"}
EXTRA_WORDS = {"ceramic": ["سيراميك", "ceramic"], "tank": ["خزان", "tank"], "bucket": ["دلو", "bucket"],
               "feeding": ["إطعام", "اطعام", "feeding"], "sheep": ["خروف", "sheep"]}


# ---------------- name matching ----------------
def _norm(t: str) -> str:
    t = re.sub(r"[ً-ْـ]", "", t or "")  # harakat, tatweel
    t = t.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"}))
    return re.sub(r"[^\w\s]", " ", t.lower())


STOP_N = {_norm(w).strip() for w in STOP}


def _variants(w: str) -> set[str]:
    out = {w}
    if w.startswith("و") and len(w) > 3:
        out.add(w[1:])  # "ودانا" -> "دانا" (and "وهبي" keeps "وهبي" too)
    for v in list(out):
        if v.startswith("ال") and len(v) > 4:
            out.add(v[2:])  # "الجابر" -> "جابر"
    return out


def tokens(t: str | None) -> set[str]:
    out = set()
    for w in _norm(t or "").split():
        if len(w) < 2 or w.isdigit() or _variants(w) & STOP_N:
            continue
        out.add(w)
    return out


def name_score(record_name: str | None, unit_text: str) -> float:
    """Share of the workbook name's words found in the order's dedication/donor/customer text."""
    a, b = tokens(record_name), tokens(unit_text)
    if not a or not b:
        return 0.0
    bv = set().union(*(_variants(w) for w in b))
    shared = [w for w in a if _variants(w) & bv]
    if len(a) == 1:
        # one-word names ("محمد") are too common, unless the dedication is just that name
        return 1.0 if shared and len(shared[0]) >= 4 and len(b) <= 2 else 0.0
    if len(shared) < 2:
        return 0.0
    return len(shared) / len(a)


def _extras_of(text_: str | None) -> set[str]:
    t = (text_ or "").lower()
    return {k for k, words in EXTRA_WORDS.items() if any(w in t for w in words)}


# ---------------- scope ----------------
def granted_scopes(db: Session) -> set[str]:
    r = sh.gql(db, "{ currentAppInstallation { accessScopes { handle } } }")
    return {s["handle"] for s in r["currentAppInstallation"]["accessScopes"]}


def ensure_all_orders_scope(db: Session) -> bool:
    """True if the app can read orders older than 60 days. Refreshes a cached token once (new scopes need a new token)."""
    if "read_all_orders" in granted_scopes(db):
        return True
    if secrets_store.get_secret(db, sh.SECRET_CC):
        secrets_store.set_secret(db, sh.SECRET_CC, None, None)
        return "read_all_orders" in granted_scopes(db)
    return False


# ---------------- the import ----------------
def _cut_day(cfg: dict) -> date:
    """Orders on/after this day belong to the live import."""
    return date.fromisoformat(cfg["import_from"]) if cfg.get("import_from") else date.today()


def fetch_orders(db: Session, start: date | None, before: date, max_pages: int = 60) -> list[dict]:
    parts = [f"created_at:<'{(before + timedelta(days=1)).isoformat()}'"]
    if start:
        parts.append(f"created_at:>='{(start - timedelta(days=1)).isoformat()}'")
    after, out = None, []
    for _ in range(max_pages):
        page = sh.gql(db, HISTORY_QUERY, {"first": 50, "after": after, "q": " AND ".join(parts)})["orders"]
        out += [sh.normalize_graphql(n) for n in page["nodes"]]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return out


def run(db: Session, *, start: date | None = None, user: User | None = None, orders: list[dict] | None = None) -> dict:
    """Match every past order (before the live start date) to the workbook. Safe to run again."""
    db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": sh.LOCK_ID})
    cfg = sh.config(db)
    cut = _cut_day(cfg)
    result = {"orders": 0, "units": 0, "sure": 0, "likely": 0, "guess": 0, "none": 0, "skipped_live": 0,
              "cancelled": 0, "not_paid": 0, "all_orders_scope": True, "first_order": None, "last_order": None}
    if orders is None:
        result["all_orders_scope"] = ensure_all_orders_scope(db)
        orders = fetch_orders(db, start, cut - timedelta(days=1))
    pending: list[tuple[ShopifyOrder, dict, dict]] = []  # (row, order, unit)
    days = []
    for o in sorted(orders, key=lambda x: x.get("created_at") or ""):
        day = sh.order_day(o, cfg["timezone"])
        if not day or day >= cut or (start and day < start):
            continue
        row = db.scalar(select(ShopifyOrder).where(ShopifyOrder.shopify_id == o["id"]))
        if row is not None and row.source != "history":
            result["skipped_live"] += 1  # already handled by the live import
            continue
        result["orders"] += 1
        days.append(day)
        result["first_order"] = result["first_order"] or o["name"]
        result["last_order"] = o["name"]
        if row is None:
            row = ShopifyOrder(shopify_id=o["id"], name=o["name"], source="history", status="new")
            db.add(row)
        row.created_at_shop = datetime.fromisoformat(str(o["created_at"]).replace("Z", "+00:00"))
        row.financial_status, row.total, row.currency = o["financial_status"], o["total"], o["currency"]
        row.customer_name = (o.get("customer_name") or "")[:200] or None
        row.raw, row.updated_at = sh._jsonable_order(o), utcnow()
        db.flush()
        if o["cancelled"] or o["financial_status"] in {"refunded", "voided"}:
            row.cancelled, row.status = True, "cancelled"
            row.message = f"Cancelled/refunded in Shopify ({o['financial_status'] or 'cancelled'}); not matched"
            result["cancelled"] += 1
            continue
        if o["financial_status"] not in {"paid", "partially_paid", "partially_refunded"}:
            row.status, row.message = "waiting_payment", f"Not paid ({o['financial_status'] or 'pending'})"
            result["not_paid"] += 1
            continue
        units, problems = sh._plan(db, row, o, cfg)
        row.message = "; ".join(problems) or None
        existing = {(i.line_item_id, i.unit): i for i in db.scalars(
            select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id))}
        if not units:
            row.status = "nothing_to_import"
        for x in units:
            it = existing.get((x["line"]["id"], x["unit"]))
            if it and (it.project_id or it.sacrifice_id):
                result[it.match or "sure"] = result.get(it.match or "sure", 0) + 1
                continue  # matched or created on an earlier run
            if it is None:
                it = ShopifyOrderItem(order_id=row.id, line_item_id=x["line"]["id"], unit=x["unit"])
                db.add(it)
            it.title, it.kind, it.amount, it.match = x["line"]["title"][:300], x["kind"], x["amount"], "none"
            x["item"] = it
            pending.append((row, o, x))
    db.flush()
    result["units"] = len(pending) + sum(result[k] for k in ("sure", "likely", "guess"))
    if pending:
        lo, hi = min(days) - timedelta(days=NAME_WINDOW), max(days) + timedelta(days=NAME_WINDOW)
        _match(db, cfg, pending, lo, hi, result)
    touched = {r.id: r for r, _, _ in pending}
    for row in touched.values():
        _set_status(db, row)
    st = get_setting(db, sh.STATE)
    st["history"] = {**{k: v for k, v in result.items()}, "at": utcnow().isoformat(), "start": start.isoformat() if start else None}
    set_setting(db, sh.STATE, st)
    audit(db, "shopify.history_import", "settings", "shopify", actor=user, actor_label=None if user else "Shopify",
          after=result)
    return result


def _candidates(db: Session, lo: date, hi: date, names: set[str]):
    taken_p = select(ShopifyOrderItem.project_id).where(ShopifyOrderItem.project_id.is_not(None))
    taken_s = select(ShopifyOrderItem.sacrifice_id).where(ShopifyOrderItem.sacrifice_id.is_not(None))
    empty_p = or_(Project.shopify_order.is_(None), Project.shopify_order == "")
    empty_s = or_(Sacrifice.shopify_order.is_(None), Sacrifice.shopify_order == "")
    norm_p = func.replace(func.trim(Project.shopify_order), "#", "")
    norm_s = func.replace(func.trim(Sacrifice.shopify_order), "#", "")
    wells = list(db.scalars(select(Project).where(
        Project.is_sample.is_(False), Project.merged_into_id.is_(None), Project.id.not_in(taken_p),
        or_(empty_p & Project.order_date.between(lo, hi), norm_p.in_(names)))).unique())
    sacs = list(db.scalars(select(Sacrifice).where(
        Sacrifice.is_sample.is_(False), Sacrifice.id.not_in(taken_s),
        or_(empty_s & Sacrifice.order_date.between(lo, hi), norm_s.in_(names)))).unique())
    return wells, sacs


def _match(db: Session, cfg: dict, pending: list, lo: date, hi: date, result: dict) -> None:
    names = {sh._order_no(o["name"]) for _, o, _ in pending}
    wells, sacs = _candidates(db, lo, hi, names)
    cands = [("well", w) for w in wells] + [("sacrifice", s) for s in sacs]
    used: set[tuple[str, int]] = set()
    done: set[int] = set()  # index in pending

    def info(i):
        row, o, x = pending[i]
        f = sh._unit_fields(db, o, x, cfg)
        return {"day": sh.order_day(o, cfg["timezone"]), "no": sh._order_no(o["name"]),
                "text": " ".join(filter(None, [f["dedication"], f["donor"], o.get("customer_name")])),
                "type": sh.well_type(f["title"]) if x["kind"] == "well" else sh.animal_type(f["title"]),
                "extras": _extras_of(" ".join(x["extras"])), "amount": x["amount"], "fields": f}
    infos = [info(i) for i in range(len(pending))]

    def rec(kind, r):
        if kind == "well":
            return {"day": r.order_date, "no": (r.shopify_order or "").strip().lstrip("#").strip(), "name": r.customer_name,
                    "type": r.well_type, "extras": _extras_of(r.extras), "amount": r.sale_amount}
        return {"day": r.order_date, "no": (r.shopify_order or "").strip().lstrip("#").strip(), "name": r.donor_name,
                "type": r.animal_type, "extras": _extras_of(r.extras), "amount": r.sale_price}
    recs = [rec(k, r) for k, r in cands]

    def same_type(a, b):
        return not a or not b or a == b

    def assign(i, j, level):
        done.add(i)
        used.add((cands[j][0], cands[j][1].id))
        _link(db, pending[i], cands[j], level, infos[i]["fields"])
        result[level] += 1

    # 1. the workbook row already has this order number
    for i, (row, o, x) in enumerate(pending):
        for j, (kind, r) in enumerate(cands):
            if (kind, r.id) not in used and kind == x["kind"] and recs[j]["no"] and recs[j]["no"] == infos[i]["no"]:
                assign(i, j, "sure")
                break

    # 2. the name matches (dedication / donor / customer)
    pairs = []
    for i, (_, _, x) in enumerate(pending):
        if i in done or not infos[i]["day"]:
            continue
        for j, (kind, r) in enumerate(cands):
            if kind != x["kind"] or (kind, r.id) in used or not recs[j]["day"] or recs[j]["no"]:
                continue
            dd = abs((recs[j]["day"] - infos[i]["day"]).days)
            if dd > NAME_WINDOW:
                continue
            sc = name_score(recs[j]["name"], infos[i]["text"])
            if sc >= 0.5:
                pairs.append((-sc, dd, 0 if same_type(recs[j]["type"], infos[i]["type"]) else 1, i, j))
    for _, _, _, i, j in sorted(pairs):
        if i not in done and (cands[j][0], cands[j][1].id) not in used:
            assign(i, j, "sure")

    # 3. same kind + type within a day; extras and price break ties
    def fits(i, j):
        kind, r = cands[j]
        x = pending[i][2]
        if i in done or kind != x["kind"] or (kind, r.id) in used or recs[j]["no"] or not recs[j]["day"] or not infos[i]["day"]:
            return None
        dd = abs((recs[j]["day"] - infos[i]["day"]).days)
        if dd > DAY_WINDOW or not same_type(recs[j]["type"], infos[i]["type"]):
            return None
        ex = len(infos[i]["extras"] ^ recs[j]["extras"])
        price = 0 if recs[j]["amount"] is not None and Decimal(recs[j]["amount"]) == infos[i]["amount"] else 1
        return (dd + ex, price, 0 if recs[j]["type"] else 1, getattr(r, "well_id", None) or getattr(r, "sacrifice_no", 0))
    options = {i: [(f, j) for j in range(len(cands)) if (f := fits(i, j)) is not None] for i in range(len(pending)) if i not in done}
    fans = {}
    for i, opts in options.items():
        for _, j in opts:
            fans[j] = fans.get(j, 0) + 1
    order = sorted(options, key=lambda i: (len(options[i]) or 999, min(options[i])[0] if options[i] else (99,)))
    for i in order:
        best = sorted(o for o in options[i] if (cands[o[1]][0], cands[o[1]][1].id) not in used)
        if not best:
            continue
        f, j = best[0]
        unique = len(options[i]) == 1 and fans.get(j) == 1 and f[0] == 0
        assign(i, j, "likely" if unique else "guess")
    result["none"] = sum(1 for i in range(len(pending)) if i not in done)


def _fill(obj, field: str, value) -> dict:
    return {field: value} if value and not getattr(obj, field) else {}


def _link(db: Session, p: tuple, cand: tuple, level: str, f: dict) -> None:
    """Link one order unit to a workbook row. Sure/likely fill only empty fields; a guess changes nothing on the row."""
    row, o, x = p
    kind, r = cand
    it: ShopifyOrderItem = x["item"]
    it.match = level
    if kind == "well":
        it.project_id = r.id
    else:
        it.sacrifice_id = r.id
    if level in {"sure", "likely"}:
        _fill_record(db, kind, r, o["name"], f)
    db.flush()


def _fill_record(db: Session, kind: str, r, order_name: str, f: dict) -> None:
    ch = {**_fill(r, "shopify_order", order_name[:60]), **_fill(r, "dedication", f.get("dedication"))}
    if kind == "well":
        ch.update(_fill(r, "customer_phone", f.get("phone")))
        if ch:
            psvc.update_project(db, r, ch, actor=None, source="shopify")
    else:
        ch.update(_fill(r, "intention", f.get("intention")))
        if ch:
            fin.update_sacrifice(db, r, ch, actor=None, source="shopify")


def _set_status(db: Session, row: ShopifyOrder) -> None:
    items = list(db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id,
                                                           ShopifyOrderItem.kind.in_(["well", "sacrifice"]))))
    if not items:
        row.status = "nothing_to_import"
        return
    levels = [i.match for i in items]
    problems = [m for m in (row.message or "").split("; ") if m and not m.startswith(("Matched", "Not in", "Linked"))]
    if all(m in {"sure", "likely", "created"} for m in levels):
        row.status = "matched"
    elif all(m == "none" for m in levels):
        row.status = "not_in_workbook"
    else:
        row.status = "check"
    if problems and row.status == "matched":
        row.status = "check"
    parts = []
    n_none = levels.count("none")
    n_guess = levels.count("guess")
    if n_guess:
        parts.append(f"Linked by date and type only ({n_guess}); dedication not copied, please check")
    if n_none:
        parts.append(f"Not in the workbook ({n_none}): press Add to HAYAH or link it")
    row.message = "; ".join(parts + problems) or None


# ---------------- manager actions ----------------
def _from_raw(raw: dict) -> dict:
    o = dict(raw)
    o["total"] = Decimal(str(o.get("total") or 0))
    o["lines"] = [{**li, "unit_price": Decimal(str(li["unit_price"])), "discount": Decimal(str(li["discount"]))}
                  for li in raw.get("lines") or []]
    return o


def add_missing(db: Session, *, order_name: str | None, user: User) -> dict:
    """Create the wells/sacrifices for past-order units that are not in the workbook."""
    db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": sh.LOCK_ID})
    cfg = sh.config(db)
    q = select(ShopifyOrder).where(ShopifyOrder.source == "history", ShopifyOrder.status.in_(["not_in_workbook", "check"]))
    if order_name:
        q = q.where(ShopifyOrder.name == "#" + sh._order_no(order_name))
    made = []
    for row in db.scalars(q.order_by(ShopifyOrder.created_at_shop)):
        o = _from_raw(row.raw or {})
        units, _ = sh._plan(db, row, o, cfg)
        items = {(i.line_item_id, i.unit): i for i in db.scalars(select(ShopifyOrderItem).where(ShopifyOrderItem.order_id == row.id))}
        for x in units:
            it = items.get((x["line"]["id"], x["unit"]))
            if it is None or it.project_id or it.sacrifice_id:
                continue
            made.append(sh._create_unit(db, row, o, x, cfg, True, item=it, match="created"))
        _set_status(db, row)
    if order_name and not made:
        raise HTTPException(404, "Nothing left to add for this order")
    audit(db, "shopify.history_added", "shopify_order", order_name or "all", actor=user, after={"created": made})
    return {"created": made}


def link_unit(db: Session, *, item_id: int, number: int, user: User) -> dict:
    """A manager says which workbook row this past-order unit is (replaces a guess or a 'not in workbook')."""
    it = db.get(ShopifyOrderItem, item_id)
    if not it or it.kind not in {"well", "sacrifice"}:
        raise HTTPException(404, "Order line not found")
    row = db.get(ShopifyOrder, it.order_id)
    if row.source != "history":
        raise HTTPException(409, "Only past orders can be linked by hand")
    if it.match == "created":
        raise HTTPException(409, "A record was already created for this line")
    if it.kind == "well":
        r = psvc.get_by_well_id(db, number)
        if not r:
            raise HTTPException(404, f"Well ID {number} not found")
        clash = db.scalar(select(ShopifyOrderItem).where(ShopifyOrderItem.project_id == r.id, ShopifyOrderItem.id != it.id))
    else:
        r = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == number))
        if not r:
            raise HTTPException(404, f"Sacrifice {number} not found")
        clash = db.scalar(select(ShopifyOrderItem).where(ShopifyOrderItem.sacrifice_id == r.id, ShopifyOrderItem.id != it.id))
    if clash:
        other = db.get(ShopifyOrder, clash.order_id)
        if clash.match != "guess":
            raise HTTPException(409, f"That record is already linked to order {other.name}")
        clash.project_id = clash.sacrifice_id = None  # it was only a guess for another order
        clash.match = "none"
        _set_status(db, other)
    it.project_id, it.sacrifice_id = (r.id, None) if it.kind == "well" else (None, r.id)
    it.match = "sure"
    o = _from_raw(row.raw or {})
    cfg = sh.config(db)
    unit = next((x for x in sh._plan(db, row, o, cfg)[0] if x["line"]["id"] == it.line_item_id and x["unit"] == it.unit), None)
    if unit:
        _fill_record(db, it.kind, r, row.name, sh._unit_fields(db, o, unit, cfg))
    db.flush()
    _set_status(db, row)
    audit(db, "shopify.history_linked", "shopify_order", row.name, actor=user,
          after={"item": it.id, "kind": it.kind, "number": number})
    return {"ok": True, "status": row.status}


def summary(db: Session) -> dict:
    rows = db.execute(text("""
        select coalesce(i.match, 'none') m, count(*) from shopify_order_items i join shopify_orders o on o.id = i.order_id
        where o.source = 'history' and i.kind in ('well', 'sacrifice') group by 1""")).all()
    by_status = dict(db.execute(text("select status, count(*) from shopify_orders where source = 'history' group by 1")).all())
    return {"units": {m: n for m, n in rows}, "orders": by_status, "last_run": get_setting(db, sh.STATE).get("history")}


def review_orders(db: Session, limit: int = 300) -> list[dict]:
    """Past orders that need a manager: guesses and units not in the workbook."""
    out = []
    q = (select(ShopifyOrder).where(ShopifyOrder.source == "history", ShopifyOrder.status.in_(["check", "not_in_workbook"]))
         .order_by(ShopifyOrder.created_at_shop).limit(limit))
    for r in db.scalars(q):
        items = db.execute(select(ShopifyOrderItem, Project.well_id, Sacrifice.sacrifice_no)
                           .outerjoin(Project, Project.id == ShopifyOrderItem.project_id)
                           .outerjoin(Sacrifice, Sacrifice.id == ShopifyOrderItem.sacrifice_id)
                           .where(ShopifyOrderItem.order_id == r.id, ShopifyOrderItem.kind.in_(["well", "sacrifice"]))
                           .order_by(ShopifyOrderItem.id)).all()
        ded = {}
        for li in (r.raw or {}).get("lines") or []:
            ded[li["id"]] = sh._prop(li.get("props") or {}, sh.config(db)["dedication_keys"])
        out.append({"name": r.name, "created_at": r.created_at_shop, "customer_name": r.customer_name,
                    "total": float(r.total or 0), "currency": r.currency, "status": r.status, "message": r.message,
                    "items": [{"id": i.id, "kind": i.kind, "title": i.title, "unit": i.unit, "match": i.match,
                               "amount": float(i.amount or 0), "well_id": w, "sacrifice_no": s,
                               "dedication": ded.get(i.line_item_id)} for i, w, s in items]})
    return out

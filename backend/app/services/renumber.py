"""Changing the number of a project (Well ID) or of a sacrifice after it was created.

Every table links to projects/sacrifices by their internal id, so a new number shows on every
page, report and link at once. What holds the number itself is updated too:
  * the change history (audit_log.entity_id), so undo, "remove this import" and plaque history still find it;
  * the plaque drafts drawn in the browser (their design carries the number);
  * the Google Sheets row key of a well, and the notes that name a sheep's well / a well's sheep.
Plaque images that were already saved keep the old number (versions are never overwritten), so the
result lists them: a new plaque version has to be saved for those.

Numbers stay unique (database constraint plus a check with a clear message). Several sacrifices can be
renumbered in one go, including swaps (3098 -> 3091 while 3091 -> 3093 ...): the moves are applied in
two steps through temporary numbers, inside one transaction.
"""
from __future__ import annotations

import hashlib
import json
import re

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from app.models import (AuditLog, Plaque, PlaqueVersion, Project, Sacrifice, SheetRowState, ShopifyOrder,
                        ShopifyOrderItem, User, utcnow)
from app.services.audit import audit, jsonable

MAX_NO = 10**12
TMP = 10**11  # temporary offset while numbers are being swapped
KEEP = object()  # apply_moves: leave the order as it is


# ---------------------------------------------------------------- numbering
def next_sacrifice_no(db: Session, start: int | None = None) -> int:
    """The next free sacrifice number: one more than the highest real one (sample rows 90001+ ignored).
    Taken under a transaction lock so two orders arriving together never get the same number."""
    db.execute(text("select pg_advisory_xact_lock(hashtext('hayah:sacrifice_no'))"))
    hi = db.scalar(select(func.max(Sacrifice.sacrifice_no)).where(Sacrifice.is_sample.is_(False),
                                                                Sacrifice.sacrifice_no < TMP)) or 0
    return max(hi + 1, int(start or 0))


def order_key(v) -> str | None:
    """'#1231', '1231 ', 1231 -> '1231'. None when there is no number."""
    d = re.sub(r"\D", "", str(v or ""))
    return d.lstrip("0") or None if d else None


def order_label(key: str | None) -> str | None:
    return f"#{key}" if key else None


def _norm_col(col):
    return func.regexp_replace(func.coalesce(col, ""), r"\D", "", "g")


# ---------------------------------------------------------------- shared helpers
def _rewrite_audit(db: Session, entity_type: str, moves: dict[int, int]) -> None:
    for old, new in moves.items():
        db.execute(update(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(old))
                   .values(entity_id=f"~{new}"))
    db.execute(update(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id.like("~%"))
               .values(entity_id=func.substr(AuditLog.entity_id, 2)))


def _plaque_drafts(db: Session, plaque: Plaque | None, key: str, moves: dict[int, int]) -> bool:
    """Put the new number into the plaque drafts. Returns True when a saved plaque image shows the old one."""
    if plaque is None:
        return False
    image = False
    for v in db.scalars(select(PlaqueVersion).where(PlaqueVersion.plaque_id == plaque.id)):
        if v.media_id or v.drive_file_id:
            image = True
            continue
        d = dict(v.design or {})
        try:
            cur = int(str(d.get(key) or "").strip())
        except ValueError:
            continue
        if cur in moves:
            d[key] = str(moves[cur])
            v.design = d
    return image


def _swap_words(s: str | None, words: str, moves: dict[int, int]) -> str | None:
    if not s:
        return s
    return re.sub(rf"((?:{words})\s*)(\d+)", lambda m: m.group(1) + str(moves.get(int(m.group(2)), m.group(2))), s)


# ---------------------------------------------------------------- projects
def renumber_project(db: Session, project: Project, new_no: int, *, actor: User | None, ip: str | None = None) -> dict:
    old = project.well_id
    if not 0 < new_no < MAX_NO:
        raise HTTPException(422, "The number must be a positive whole number")
    if new_no == old:
        return {"well_id": old, "changed": False, "plaque_image_old_number": False}
    other = db.scalar(select(Project).where(Project.well_id == new_no))
    if other is not None:
        raise HTTPException(409, f"Number {new_no} is already used by another project")
    moves = {old: new_no}
    project.well_id = new_no
    project.updated_at = utcnow()
    db.flush()
    _rewrite_audit(db, "project", moves)
    db.execute(update(SheetRowState).where(SheetRowState.row_key == str(old)).values(row_key=str(new_no)))
    plaque = db.scalar(select(Plaque).where(Plaque.project_id == project.id))
    image = _plaque_drafts(db, plaque, "well_id", moves)
    for s in db.scalars(select(Sacrifice).where(Sacrifice.parent_project_id == project.id)):
        s.notes = _swap_words(s.notes, "البئر|well", moves)
    from app.services.projects import add_event
    add_event(db, project, "number_changed", source="dashboard", actor=actor,
              summary=f"رقم المشروع تغيّر من {old} إلى {new_no} · Project number changed from {old} to {new_no}",
              payload={"from": old, "to": new_no})
    audit(db, "project.renumber", "project", new_no, actor=actor, before={"well_id": old}, after={"well_id": new_no}, ip=ip)
    db.flush()
    return {"well_id": new_no, "changed": True, "from": old, "plaque_image_old_number": image}


# ---------------------------------------------------------------- sacrifices
def _row(db: Session, s: Sacrifice) -> dict:
    return {"id": s.id, "sacrifice_no": s.sacrifice_no, "order": order_label(order_key(s.shopify_order)),
            "donor_name": s.donor_name, "animal_type": s.animal_type, "order_date": s.order_date,
            "sale_price": s.sale_price, "parent_well_id": s.parent_well_id, "dedication": (s.dedication or "")[:120] or None}


def apply_moves(db: Session, moves: list[tuple], *, actor: User | None,
                reason: str = "edit", ip: str | None = None) -> dict:
    """moves: (sacrifice, new number, new order key, None to clear it, or KEEP). One transaction, swaps allowed."""
    new_nos = [n for _, n, _ in moves]
    if len(set(new_nos)) != len(new_nos):
        raise HTTPException(422, "Two sacrifices cannot get the same number")
    if any(not 0 < n < TMP for n in new_nos):
        raise HTTPException(422, "Sacrifice numbers must be positive whole numbers")
    ids = {s.id for s, _, _ in moves}
    clash = db.scalars(select(Sacrifice).where(Sacrifice.sacrifice_no.in_(new_nos), Sacrifice.id.not_in(ids))).all()
    if clash:
        raise HTTPException(409, "Already used by another sacrifice: " + ", ".join(str(c.sacrifice_no) for c in clash))
    num_moves = {s.sacrifice_no: n for s, n, _ in moves if s.sacrifice_no != n}
    before = {s.id: {"sacrifice_no": s.sacrifice_no, "shopify_order": s.shopify_order} for s, _, _ in moves}
    for s, n, _ in moves:  # step 1: out of the way
        if s.sacrifice_no != n:
            s.sacrifice_no = TMP + n
    db.flush()
    for s, n, o in moves:  # step 2: final numbers and orders
        s.sacrifice_no = n
        if o is not KEEP and order_key(s.shopify_order) != o:
            s.shopify_order = order_label(o) if o else None
        s.updated_at = utcnow()
    db.flush()
    images = []
    if num_moves:
        _rewrite_audit(db, "sacrifice", num_moves)
        wells = {s.parent_project_id for s, _, _ in moves if s.parent_project_id}
        for p in db.scalars(select(Project).where(Project.id.in_(wells))) if wells else []:
            p.notes = _swap_words(p.notes, "sacrifice|ذبيحة|ذبائح|ذبيحة رقم", num_moves)
        for s, n, _ in moves:
            plaque = db.scalar(select(Plaque).where(Plaque.sacrifice_id == s.id))
            if _plaque_drafts(db, plaque, "sacrifice_no", num_moves) and before[s.id]["sacrifice_no"] != n:
                images.append(n)
    out = []
    for s, n, _ in moves:
        b = before[s.id]
        a = {"sacrifice_no": s.sacrifice_no, "shopify_order": s.shopify_order}
        if a != b:
            audit(db, "sacrifice.renumber", "sacrifice", s.sacrifice_no, actor=actor, before=b, after=a, ip=ip)
            out.append({"id": s.id, "from": b, "to": a})
    db.flush()
    return {"changed": out, "plaque_image_old_number": images, "reason": reason}


def renumber_sacrifice(db: Session, s: Sacrifice, new_no: int, *, actor: User | None, ip: str | None = None) -> dict:
    return apply_moves(db, [(s, new_no, KEEP)], actor=actor, ip=ip)


# ---------------------------------------------------------------- many at once (preview, apply, undo)
def _by_no(db: Session, no: int) -> Sacrifice | None:
    return db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no))


def _linked_to_order(db: Session, key: str) -> list[Sacrifice]:
    via_items = select(ShopifyOrderItem.sacrifice_id).join(ShopifyOrder, ShopifyOrder.id == ShopifyOrderItem.order_id).where(
        _norm_col(ShopifyOrder.name) == key, ShopifyOrderItem.sacrifice_id.is_not(None))
    return list(db.scalars(select(Sacrifice).where(or_(_norm_col(Sacrifice.shopify_order) == key, Sacrifice.id.in_(via_items)))
                           .order_by(Sacrifice.sacrifice_no)))


def plan(db: Session, renames: list[dict], orders: list[dict]) -> dict:
    """renames: [{"from": 3098, "to": 3091}]; orders: [{"order": "1225", "numbers": [3091, 3092]}].
    Works out which sacrifice gets which number and order, without changing anything."""
    errors: list[str] = []
    target: dict[int, int] = {}     # sacrifice id -> new number
    new_order: dict[int, str] = {}  # sacrifice id -> order key
    objs: dict[int, Sacrifice] = {}
    taken: dict[int, int] = {}      # new number -> sacrifice id

    def claim(s: Sacrifice, n: int) -> bool:
        if s.id in target and target[s.id] != n:
            errors.append(f"Sacrifice {s.sacrifice_no} would get two numbers ({target[s.id]} and {n})")
            return False
        if n in taken and taken[n] != s.id:
            errors.append(f"Number {n} is given twice")
            return False
        target[s.id], taken[n], objs[s.id] = n, s.id, s
        return True

    for r in renames:
        a, b = int(r["from"]), int(r["to"])
        s = _by_no(db, a)
        if s is None:
            errors.append(f"There is no sacrifice number {a}")
            continue
        claim(s, b)

    seen_orders = set()
    for o in orders:
        key = order_key(o.get("order"))
        nums = [int(x) for x in o.get("numbers") or []]
        if not key or not nums:
            errors.append(f"Order line without an order number or sacrifice numbers: {o}")
            continue
        if key in seen_orders:
            errors.append(f"Order #{key} is listed twice")
        seen_orders.add(key)
        pending = []
        for n in nums:
            sid = taken.get(n)
            if sid is not None:  # already placed by a rename
                new_order[sid] = key
                continue
            holder = _by_no(db, n)
            if holder is not None and holder.id not in target and order_key(holder.shopify_order) in (None, key):
                claim(holder, n)  # already has the right number: keep it, link the order
                new_order[holder.id] = key
            else:
                pending.append(n)
        if pending:
            free = [s for s in _linked_to_order(db, key) if s.id not in target]
            if len(free) < len(pending):
                errors.append(f"Order #{key}: {len(pending)} more sacrifice(s) needed for {', '.join(map(str, pending))}"
                              f" but only {len(free)} other sacrifice(s) of this order were found")
            for s, n in zip(free, pending):
                claim(s, n)
                new_order[s.id] = key

    # a number in the plan that is held by a sacrifice the plan does not move
    for n, sid in taken.items():
        holder = _by_no(db, n)
        if holder is not None and holder.id != sid and holder.id not in target:
            errors.append(f"Number {n} belongs to sacrifice {holder.sacrifice_no} (order {order_label(order_key(holder.shopify_order)) or '—'}, "
                          f"{holder.donor_name or 'no name'}), which this plan does not move")

    rows = []
    for sid, n in sorted(target.items(), key=lambda kv: kv[1]):
        s = objs[sid]
        b = _row(db, s)
        after_order = order_label(new_order.get(sid)) if sid in new_order else b["order"]
        rows.append({**b, "before_no": s.sacrifice_no, "after_no": n, "before_order": b["order"], "after_order": after_order,
                     "changes": s.sacrifice_no != n or after_order != b["order"]})
    lo = min([r["before_no"] for r in rows] + [r["after_no"] for r in rows], default=0)
    hi = max([r["before_no"] for r in rows] + [r["after_no"] for r in rows], default=0)
    around = [] if not rows else [
        _row(db, s) for s in db.scalars(select(Sacrifice).where(Sacrifice.sacrifice_no.between(lo - 3, hi + 3),
                                                                Sacrifice.id.not_in(list(target))).order_by(Sacrifice.sacrifice_no))]
    state = [(r["id"], r["before_no"], r["before_order"]) for r in rows]
    token = hashlib.sha256(json.dumps([state, renames, orders], sort_keys=True, default=str).encode()).hexdigest()[:16]
    out = jsonable({"ok": not errors and bool(rows), "errors": errors, "rows": rows, "untouched_nearby": around, "token": token})
    out["_moves"] = [(sid, n, new_order.get(sid, KEEP)) for sid, n in target.items()]
    return out



def apply_plan(db: Session, renames: list[dict], orders: list[dict], token: str, *, actor: User | None,
               ip: str | None = None) -> dict:
    p = plan(db, renames, orders)
    if not p["ok"]:
        raise HTTPException(422, "; ".join(p["errors"]) or "Nothing to change")
    if p["token"] != token:
        raise HTTPException(409, "The sacrifices changed since the preview. Press Preview again.")
    sacs = {s.id: s for s in db.scalars(select(Sacrifice).where(Sacrifice.id.in_([m[0] for m in p["_moves"]])).with_for_update())}
    res = apply_moves(db, [(sacs[sid], n, o) for sid, n, o in p["_moves"]], actor=actor, reason="plan", ip=ip)
    undo = [{"id": c["id"], "from": c["to"], "to": c["from"]} for c in res["changed"]]
    row = audit(db, "sacrifices.renumbered", "renumber", None, actor=actor,
                after={"renames": renames, "orders": orders, "changed": res["changed"], "undo": undo,
                       "plaque_image_old_number": res["plaque_image_old_number"]}, ip=ip)
    db.flush()
    row.entity_id = str(row.id)
    p.pop("_moves")
    return {**p, "applied": True, "batch_id": row.id, "changed": len(res["changed"]),
            "plaque_image_old_number": res["plaque_image_old_number"]}


def batches(db: Session) -> list[dict]:
    undone = set(db.scalars(select(AuditLog.entity_id).where(AuditLog.action == "sacrifices.renumber_undone")))
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "sacrifices.renumbered").order_by(AuditLog.id.desc()).limit(20))
    return [{"id": r.id, "at": r.at, "by": r.actor_label, "changed": (r.after or {}).get("changed", []),
             "undone": str(r.id) in undone} for r in rows]


def undo_batch(db: Session, batch_id: int, *, actor: User | None, ip: str | None = None) -> dict:
    row = db.get(AuditLog, batch_id)
    if row is None or row.action != "sacrifices.renumbered":
        raise HTTPException(404, "No such renumbering")
    if db.scalar(select(AuditLog.id).where(AuditLog.action == "sacrifices.renumber_undone", AuditLog.entity_id == str(batch_id))):
        raise HTTPException(409, "This renumbering was already undone")
    steps = (row.after or {}).get("undo") or []
    sacs = {s.id: s for s in db.scalars(select(Sacrifice).where(Sacrifice.id.in_([x["id"] for x in steps])).with_for_update())}
    moves = []
    for x in steps:
        s = sacs.get(x["id"])
        if s is None or s.sacrifice_no != x["from"]["sacrifice_no"] or (s.shopify_order or None) != (x["from"]["shopify_order"] or None):
            raise HTTPException(409, f"Sacrifice {x['from']['sacrifice_no']} was changed after the renumbering, so it can't be undone automatically")
        moves.append((s, x["to"]["sacrifice_no"], order_key(x["to"]["shopify_order"])))
    res = apply_moves(db, moves, actor=actor, reason="undo", ip=ip)
    audit(db, "sacrifices.renumber_undone", "renumber", batch_id, actor=actor, after={"changed": res["changed"]}, ip=ip)
    db.flush()
    return {"undone": True, "changed": len(steps)}


# ---------------------------------------------------------------- an order and its sacrifices
def order_view(db: Session, order) -> dict:
    key = order_key(order)
    if not key:
        raise HTTPException(422, "Order number needed")
    sacs = _linked_to_order(db, key)
    via_items = select(ShopifyOrderItem.project_id).join(ShopifyOrder, ShopifyOrder.id == ShopifyOrderItem.order_id).where(
        _norm_col(ShopifyOrder.name) == key, ShopifyOrderItem.project_id.is_not(None))
    wells = db.scalars(select(Project).where(or_(_norm_col(Project.shopify_order) == key, Project.id.in_(via_items)),
                                             Project.merged_into_id.is_(None)).order_by(Project.well_id))
    so = db.scalar(select(ShopifyOrder).where(_norm_col(ShopifyOrder.name) == key))
    return jsonable({"order": order_label(key),
                     "shopify": {"name": so.name, "created_at": so.created_at_shop, "customer_name": so.customer_name,
                                 "total": so.total, "currency": so.currency, "cancelled": so.cancelled,
                                 "status": so.status} if so else None,
                     "sacrifices": [_row(db, s) for s in sacs],
                     "wells": [{"well_id": p.well_id, "customer_name": p.customer_name, "well_type": p.well_type,
                                "country": p.country} for p in wells]})

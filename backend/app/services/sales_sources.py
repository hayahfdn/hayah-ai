"""Unified sales sources.

Every well and sacrifice keeps the source exactly as it was typed or received
(`sales_source`, kept for review) and gets one unified source (`source_group`)
that reports and lists use. The groups and the values under each one are a
setting that a manager edits in Settings -> Sales sources; saving re-applies
them to every record (the original text never changes, so this can always be
redone).

Rules (Hayah, 2026-11-19):
- Case, spaces and small spelling mistakes do not matter ("Insta ads", "reffral").
- An empty or unreadable source is "Unknown". A real source that fits no group is "Other".
- Nothing is guessed: a value only joins a group when it matches one of the group's values.
"""
from __future__ import annotations

import difflib
import re

from sqlalchemy import event, inspect, select, update
from sqlalchemy.orm import Session

from app.models import Project, Sacrifice
from app.services.audit import audit
from app.services.settings_store import get_setting, set_setting

SETTING = "sales_sources"
OTHER, UNKNOWN = "Other", "Unknown"

# The order matters only for display. Values are compared after `_clean`.
DEFAULT_GROUPS: list[dict] = [
    {"name": "Insta Ads", "values": ["insta ads", "ads/ig", "ig ads", "instagram ads", "ads", "Shopify (Insta Ads)"]},
    {"name": "Referral", "values": ["referral", "custom referal", "custm referal", "customer ref", "customer referral",
                                    "frind", "friend", "reffral", "refrral", "repeated"]},
    {"name": "Instagram", "values": ["instagram", "ig", "Shopify (Instagram)"]},
    {"name": "Google", "values": ["google", "Shopify (Google)"]},
    {"name": "Lina", "values": ["lina"]},
    {"name": "Facebook", "values": ["facebook", "fb", "Shopify (Facebook)"]},
    {"name": "ChatGPT", "values": ["chatgpt", "chat gpt", "Shopify (ChatGPT)"]},
    {"name": "Influencer", "values": ["influencer"]},
    {"name": "TikTok", "values": ["tiktok", "tik tok", "Shopify (TikTok)"]},
]
EMPTY = {"", "-", "—", "?", "none", "null", "n/a", "na", "unknown", "shopify"}


def _clean(v: str | None) -> str:
    v = (v or "").strip().lower()
    v = re.sub(r"\s+", " ", v)
    return v


def _inner(v: str) -> str:
    """'shopify (insta ads · gulf - reels)' -> 'insta ads'."""
    m = re.fullmatch(r"shopify \((.*)\)", v)
    if m:
        v = m.group(1)
    return v.split("·")[0].strip()


def groups(db: Session) -> list[dict]:
    return get_setting(db, SETTING).get("groups") or DEFAULT_GROUPS


def save_groups(db: Session, new: list[dict], user) -> dict:
    seen, clean = set(), []
    for g in new:
        name = (g.get("name") or "").strip()[:40]
        if not name or name.lower() in seen or name in (OTHER, UNKNOWN):
            continue
        seen.add(name.lower())
        vals = sorted({_clean(v) for v in g.get("values") or [] if _clean(v)})
        clean.append({"name": name, "values": vals})
    before = groups(db)
    set_setting(db, SETTING, {"groups": clean}, user.id if user else None)
    changed = apply_all(db)
    audit(db, "sales_sources.saved", "setting", SETTING, actor=user, before={"groups": before},
          after={"groups": clean, "records_changed": changed})
    return {"groups": clean, "records_changed": changed}


def _index(gs: list[dict]) -> dict[str, str]:
    idx = {}
    for g in gs:
        idx[_clean(g["name"])] = g["name"]
        for v in g.get("values") or []:
            idx[_clean(v)] = g["name"]
            idx[_inner(_clean(v))] = g["name"]
    return idx


def unify(raw: str | None, gs: list[dict] | None = None, _idx: dict | None = None) -> str:
    idx = _idx if _idx is not None else _index(gs or DEFAULT_GROUPS)
    v = _clean(raw)
    if v in EMPTY:
        return UNKNOWN
    for cand in (v, _inner(v)):
        if cand in idx:
            return idx[cand]
    inner = _inner(v)
    if inner in EMPTY:
        return UNKNOWN
    # small spelling mistakes only (e.g. "reffral", "instagarm"); short words must match exactly
    if len(inner) >= 5:
        close = difflib.get_close_matches(inner, [k for k in idx if len(k) >= 5], n=1, cutoff=0.84)
        if close:
            return idx[close[0]]
    return OTHER


def group_names(db: Session) -> list[str]:
    return [g["name"] for g in groups(db)] + [OTHER, UNKNOWN]


def apply_one(db: Session, obj) -> None:
    obj.source_group = unify(obj.sales_source, groups(db))


def apply_all(db: Session) -> int:
    """Recompute the unified source of every record. Returns how many changed."""
    idx = _index(groups(db))
    changed = 0
    for model in (Project, Sacrifice):
        rows = db.execute(select(model.id, model.sales_source, model.source_group)).all()
        by_new: dict[str, list[int]] = {}
        for rid, raw, cur in rows:
            new = unify(raw, _idx=idx)
            if new != cur:
                by_new.setdefault(new, []).append(rid)
        for new, ids in by_new.items():
            # a plain UPDATE: the original text is untouched, so no version bump or audit per row
            db.execute(update(model).where(model.id.in_(ids)).values(source_group=new)
                       .execution_options(synchronize_session=False))
            changed += len(ids)
    db.flush()
    return changed


def overview(db: Session) -> dict:
    """Groups with counts, and the original values under Other/Unknown for review."""
    out: dict[str, dict] = {n: {"name": n, "count": 0, "raw": {}} for n in group_names(db)}
    for model in (Project, Sacrifice):
        for raw, grp in db.execute(select(model.sales_source, model.source_group)).all():
            g = out.setdefault(grp or UNKNOWN, {"name": grp or UNKNOWN, "count": 0, "raw": {}})
            g["count"] += 1
            key = (raw or "").strip() or "—"
            g["raw"][key] = g["raw"].get(key, 0) + 1
    gs = {g["name"]: g for g in groups(db)}
    rows = []
    for n, g in out.items():
        raw = sorted(g["raw"].items(), key=lambda kv: -kv[1])
        rows.append({"name": n, "values": gs.get(n, {}).get("values", []), "count": g["count"],
                     "raw": [{"value": k, "count": c} for k, c in raw[:40]], "fixed": n in (OTHER, UNKNOWN)})
    return {"groups": rows}


@event.listens_for(Session, "before_flush")
def _keep_group_current(session: Session, _ctx, _inst) -> None:
    """Whenever a well or sacrifice is added or its source changes, set its unified source."""
    todo = [o for o in list(session.new) + list(session.dirty) if isinstance(o, (Project, Sacrifice))
            and (o in session.new or inspect(o).attrs.sales_source.history.has_changes() or o.source_group is None)]
    if not todo:
        return
    with session.no_autoflush:
        idx = _index(groups(session))
    for o in todo:
        o.source_group = unify(o.sales_source, _idx=idx)

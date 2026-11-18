"""The four well types HAYAH uses, and how older names map onto them.

Every write of Project.well_type goes through normalize() (a model validator), so a
long name such as "بئر ارتوازي متوسط" from the workbook, Shopify or a form is stored
as "متوسط" and the same type never appears twice in reports or filters.

"كهربائي" is kept only for the one old electric well. It is not offered for new wells.
"""
from __future__ import annotations

import re

TYPES = ["يدوي", "متوسط", "عميق", "شمسي"]
LEGACY = "كهربائي"  # discontinued: one old project only
ALL = TYPES + [LEGACY]

# Hayah's table (2026-11-18). Checked in order; the first rule that matches wins.
_RULES: list[tuple[str, list[str]]] = [
    (LEGACY, ["كهربائي", "كهربا", "electric"]),
    ("شمسي", ["شمسي", "شمسية", "طاقة شمسية", "solar"]),
    ("عميق", ["متوضأ", "متوضا", "عميق", "deep", "wudu"]),
    ("متوسط", ["متوسط", "medium"]),
    ("يدوي", ["يدوي", "يدوية", "سطحي", "hand", "manual"]),
]


def _clean(v: str) -> str:
    v = re.sub(r"[ً-ْـ]", "", v)  # tashkeel and tatweel
    return re.sub(r"\s+", " ", v).strip()


def normalize(value: str | None) -> str | None:
    """Map any known spelling onto one of the four types (or the legacy electric type).
    Unknown text is returned cleaned but unchanged, so nothing is ever lost."""
    if value is None:
        return None
    v = _clean(str(value))
    if not v:
        return None
    low = v.lower()
    for target, words in _RULES:
        if any(w in low for w in words):
            return target
    return v


def is_known(value: str | None) -> bool:
    return value is None or value in ALL



# ---------------- unifying existing rows (reversible, logged) ----------------
# Plain SQL on a connection so the database migration and the Settings page share it.
# Each run writes one audit row 'well_types.normalized' holding every change, so it can be undone.
def preview(conn) -> list[dict]:
    """What normalize_rows would change: [{'from', 'to', 'count'}], largest first."""
    from sqlalchemy import text
    rows = conn.execute(text("select well_type, count(*) from projects where well_type is not null group by well_type")).all()
    out = [{"from": old, "to": normalize(old), "count": n} for old, n in rows if normalize(old) != old]
    return sorted(out, key=lambda r: -r["count"])


def unknown(conn) -> list[dict]:
    """Types that are none of the four (and not the old electric one), left for a person to fix."""
    from sqlalchemy import text
    rows = conn.execute(text("select well_type, count(*) from projects where well_type is not null group by well_type")).all()
    return [{"value": v, "count": n} for v, n in rows if normalize(v) not in ALL]


def normalize_rows(conn, *, actor_label: str, actor_id: int | None = None) -> dict:
    from sqlalchemy import text
    rows = conn.execute(text("select id, well_id, well_type, extras from projects where well_type is not null order by well_id")).all()
    changes = []
    for pid, well_id, old, extras in rows:
        new = normalize(old)
        if new == old:
            continue
        ch = {"id": pid, "well_id": well_id, "before": old, "after": new}
        # "يدوي مع سيراميك" becomes "يدوي"; keep the ceramic as an extra so it is not lost.
        if "سيراميك" in old and "سيراميك" not in (extras or ""):
            ch["extras_before"] = extras
            ch["extras_after"] = ((extras + "، ") if extras else "") + "سيراميك"
        changes.append(ch)
    for ch in changes:
        if "extras_after" in ch:
            conn.execute(text("update projects set well_type = :t, extras = :e, version = version + 1 where id = :id"),
                         {"t": ch["after"], "e": ch["extras_after"], "id": ch["id"]})
        else:
            conn.execute(text("update projects set well_type = :t, version = version + 1 where id = :id"),
                         {"t": ch["after"], "id": ch["id"]})
    audit_id = None
    if changes:
        import json
        audit_id = conn.execute(text(
            "insert into audit_log (at, actor_user_id, actor_label, action, entity_type, entity_id, before, after) "
            "values (now(), :uid, :label, 'well_types.normalized', 'project', null, null, cast(:after as jsonb)) returning id"),
            {"uid": actor_id, "label": actor_label,
             "after": json.dumps({"changes": changes, "count": len(changes)}, ensure_ascii=False)}).scalar()
    return {"changed": len(changes), "audit_id": audit_id}


def undo_rows(conn, audit_id: int, *, actor_label: str, actor_id: int | None = None) -> dict:
    """Put back the old names from one run. A well whose type was changed again since is skipped."""
    import json
    from sqlalchemy import text
    row = conn.execute(text("select after from audit_log where id = :id and action = 'well_types.normalized'"),
                       {"id": audit_id}).first()
    if not row:
        raise LookupError("No well-type unification with that number")
    if conn.execute(text("select 1 from audit_log where action = 'well_types.restored' and entity_id = :id"),
                    {"id": str(audit_id)}).first():
        raise ValueError("This unification was already undone")
    restored, skipped = 0, []
    for ch in (row[0] or {}).get("changes", []):
        n = conn.execute(text("update projects set well_type = :old, version = version + 1 where id = :id and well_type = :new"),
                         {"old": ch["before"], "new": ch["after"], "id": ch["id"]}).rowcount
        if not n:
            skipped.append(ch["well_id"])
            continue
        restored += 1
        if "extras_after" in ch:
            conn.execute(text("update projects set extras = :e where id = :id and extras = :now"),
                         {"e": ch.get("extras_before"), "now": ch["extras_after"], "id": ch["id"]})
    conn.execute(text(
        "insert into audit_log (at, actor_user_id, actor_label, action, entity_type, entity_id, before, after) "
        "values (now(), :uid, :label, 'well_types.restored', 'audit', :eid, null, cast(:after as jsonb))"),
        {"uid": actor_id, "label": actor_label, "eid": str(audit_id),
         "after": json.dumps({"restored": restored, "skipped_well_ids": skipped})})
    return {"restored": restored, "skipped_well_ids": skipped}


def runs(conn) -> list[dict]:
    from sqlalchemy import text
    undone = {r[0] for r in conn.execute(text("select entity_id from audit_log where action = 'well_types.restored'"))}
    rows = conn.execute(text("select id, at, actor_label, after from audit_log where action = 'well_types.normalized' order by id desc limit 20")).all()
    return [{"id": i, "at": at.isoformat() if at else None, "by": by, "count": (a or {}).get("count", 0),
             "undone": str(i) in undone} for i, at, by, a in rows]

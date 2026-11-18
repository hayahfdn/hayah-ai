""""Edit with a prompt".

A manager types what they want in plain Arabic or English ("mark well 1305
as completed, cost 450"). Claude turns it into a list of proposed operations.
Nothing is written at that point. The server checks every operation against
the same validation the normal pages use, and shows a before/after preview.
Only when the manager presses Apply are the operations executed, all in one
transaction, through the normal audited services.

Hard rules (enforced here, not left to the model):
- Only the operations in OPS exist. There is no delete.
- Delivery status/date cannot be changed by a prompt.
- A new Well ID or sacrifice number must be written in the prompt itself;
  the model can never invent one.
- Contractors and accounts are matched by their exact code or name.
"""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Contractor, FinanceAccount, Project, Sacrifice, Transaction, TxKind, UsageRecord, User
from app.schemas import (
    ProjectCreate, ProjectUpdate, SacrificeCreate, SacrificeUpdate, TransactionCreate, TransactionUpdate,
)
from app.services import finance as fin, projects as psvc
from app.services.audit import audit, jsonable, snapshot
from app.services.settings_store import get_setting
from app.services.usage import month_ai_cost

WELL_FIELDS = [f for f in ProjectUpdate.model_fields if f != "expected_version"]
SAC_FIELDS = [f for f in SacrificeUpdate.model_fields if f != "expected_version"]
TX_FIELDS = [f for f in TransactionUpdate.model_fields if f != "expected_version"]

OPS = {
    "update_well": "Change fields of an existing well. target = its Well ID.",
    "create_well": "Add a new well. target = the Well ID written in the request.",
    "update_sacrifice": "Change fields of an existing sacrifice. target = its number.",
    "create_sacrifice": "Add a new sacrifice. target = the number written in the request.",
    "add_transaction": "Record money: payment to contractor, ad spend, expense, income, partner movement. target = empty.",
    "update_transaction": "Change a money row. target = its transaction id.",
    "void_transaction": "Cancel a wrong money row (it stays in history). target = its id, fields: reason.",
}

PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "operations", "questions"],
    "properties": {
        "summary": {"type": "string", "description": "One short sentence, in the user's language, of what will change."},
        "questions": {"type": "array", "items": {"type": "string"},
                      "description": "Ask here instead of guessing when something is unclear."},
        "operations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["op", "target", "fields"],
            "properties": {
                "op": {"type": "string", "enum": list(OPS)},
                "target": {"type": "string"},
                "fields": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["name", "value"],
                    "properties": {"name": {"type": "string"}, "value": {"type": "string"}}}},
            }}},
    },
}


class AssistantUnavailable(HTTPException):
    def __init__(self, msg: str, code: str = "unavailable"):
        super().__init__(503, msg)
        self.code = code


# ---------------- model call ----------------
def _system_prompt(db: Session) -> str:
    contractors = ", ".join(f"{c.code} ({c.name})" for c in db.scalars(select(Contractor).order_by(Contractor.code)))
    accounts = ", ".join(f"{a.code} ({a.name}, {a.kind})" for a in db.scalars(select(FinanceAccount).order_by(FinanceAccount.sort_order)))
    return f"""You turn requests from the HAYAH Foundation team into edits for their operations database
(water wells and sacrifices, with costs, sales and money accounts). Today is {date.today().isoformat()}.
Requests may be in Arabic or English, with Arabic or Western digits.

Return only operations from this list:
{json.dumps(OPS, ensure_ascii=False, indent=1)}

Field names you may use:
- wells: {", ".join(WELL_FIELDS)}
- sacrifices: {", ".join(SAC_FIELDS)}
- transactions: {", ".join(TX_FIELDS)}
Values are strings. Dates are YYYY-MM-DD. Money is a plain number. An empty string clears a field.
For contractor_id give the contractor code; for account_id give the account code.
Status values: construction_status = new_order|scheduled|in_progress|completed|on_hold|cancelled;
payment_status = unpaid|partial|paid|refunded; video_status = none|raw_received|processing|in_review|completed;
transaction kind = {"|".join(k.value for k in TxKind)}.
Contractors: {contractors or "none"}. Accounts: {accounts or "none"}.

Rules:
- Never invent a Well ID, sacrifice number or transaction id. Use only numbers the user wrote or rows in the context.
- Delivery status and delivery date cannot be changed here; if asked, add a question saying the delivery must be confirmed on the Delivery page.
- Nothing can be deleted. A wrong money row is voided.
- If the request is unclear, return no operations and ask in "questions".
- Keep the summary short and in the user's language."""


def _context_rows(db: Session, page: dict | None) -> str:
    """A small slice of the rows the user is looking at, so 'the Ahmed well' can be resolved.
    Phone numbers are never sent."""
    page = page or {}
    rows: list[dict] = []
    if page.get("month") and page.get("kind") == "sacrifices":
        for s in fin.list_sacrifices(db, month=page["month"])[:200]:
            rows.append({"sacrifice_no": s.sacrifice_no, "donor": s.donor_name, "animal": s.animal_type,
                         "contractor": s.contractor.code if s.contractor else None, "cost": s.cost, "sale_price": s.sale_price})
    elif page.get("account"):
        a = db.scalar(select(FinanceAccount).where(func.upper(FinanceAccount.code) == str(page["account"]).upper()))
        if a:
            for t in fin.list_transactions(db, account_id=a.id)[-150:]:
                rows.append({"id": t.id, "date": t.date, "kind": t.kind, "amount": t.amount, "description": t.description, "voided": t.voided})
    else:
        q = select(Project).where(Project.merged_into_id.is_(None))
        if page.get("month"):
            a, b = fin.month_bounds(page["month"])
            q = q.where(Project.order_date >= a, Project.order_date < b)
        if page.get("contractor"):
            q = q.join(Contractor, Project.contractor_id == Contractor.id).where(func.upper(Contractor.code) == str(page["contractor"]).upper())
        for p in db.scalars(q.order_by(Project.well_id.desc()).limit(200)):
            rows.append({"well_id": p.well_id, "customer": p.customer_name, "country": p.country, "type": p.well_type,
                         "contractor": p.contractor.code if p.contractor else None, "status": p.construction_status,
                         "cost": p.cost, "sale": p.sale_amount})
    return json.dumps(jsonable(rows), ensure_ascii=False)


def _call_model(db: Session, prompt: str, page: dict | None) -> tuple[dict, dict]:
    """Returns (plan, usage). Isolated so tests can replace it."""
    import anthropic

    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=120.0)
    try:
        resp = client.beta.messages.create(
            model=s.anthropic_model,
            max_tokens=16000,
            system=_system_prompt(db),
            messages=[{"role": "user", "content": f"Rows on the page the user is looking at:\n{_context_rows(db, page)}\n\nRequest:\n{prompt}"}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise AssistantUnavailable("The Anthropic API key was rejected. Check HAYAH_ANTHROPIC_API_KEY on the server.")
    except anthropic.RateLimitError:
        raise AssistantUnavailable("Claude is busy right now (rate limit). Try again in a minute.")
    except anthropic.APIStatusError as e:
        raise AssistantUnavailable(f"Claude could not answer ({e.status_code}). Nothing was changed.")
    except anthropic.APIConnectionError:
        raise AssistantUnavailable("Could not reach Claude. Check the server's internet connection. Nothing was changed.")
    usage = {"model": resp.model, "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    if resp.stop_reason == "refusal":
        return {"summary": "", "operations": [], "questions": ["Claude declined this request. Please rephrase it."]}, usage
    if resp.stop_reason == "max_tokens":
        raise HTTPException(422, "The request was too big to plan in one go. Split it into smaller requests.")
    text = "".join(b.text for b in resp.content if b.type == "text")
    try:
        return json.loads(text), usage
    except json.JSONDecodeError:
        raise HTTPException(502, "Claude returned something unexpected. Nothing was changed. Try again.")


def _record_usage(db: Session, usage: dict, ref: str):
    s = get_settings()
    cost = (usage.get("input_tokens", 0) * s.anthropic_input_usd_per_mtok
            + usage.get("output_tokens", 0) * s.anthropic_output_usd_per_mtok) / 1_000_000
    db.add(UsageRecord(service="anthropic", operation="assistant_plan", units=usage, est_cost_usd=Decimal(str(round(cost, 6))), ref=ref))
    return cost


def check_available(db: Session) -> None:
    s = get_settings()
    cfg = get_setting(db, "ai")
    if not s.anthropic_api_key:
        raise AssistantUnavailable(
            "Editing with a prompt needs Claude (Anthropic API), which is not connected yet. "
            "An admin adds the API key on the server (HAYAH_ANTHROPIC_API_KEY) and turns AI on in Settings. "
            "Cost stays inside the monthly AI budget you set. Until then, edit the cells directly.", "no_key")
    if not cfg.get("ai_enabled"):
        raise AssistantUnavailable("AI is turned off in Settings. An admin can turn it on there.", "ai_off")
    if month_ai_cost(db) >= float(cfg.get("monthly_budget_usd", 0)):
        raise AssistantUnavailable("This month's AI budget is used up. An admin can raise it in Settings, or edit the cells directly.", "budget")


# ---------------- validation / preview ----------------
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _numbers_in(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\d+", text.translate(DIGITS))}


def _resolve_refs(db: Session, fields: dict) -> dict:
    out = dict(fields)
    if "contractor_id" in out and out["contractor_id"] not in (None, ""):
        v = str(out["contractor_id"]).strip()
        c = db.scalar(select(Contractor).where((func.upper(Contractor.code) == v.upper()) | (func.lower(Contractor.name) == v.lower())))
        if not c and v.isdigit():
            c = db.get(Contractor, int(v))
        if not c:
            raise ValueError(f"Unknown contractor '{v}'")
        out["contractor_id"] = c.id
    if "account_id" in out and out["account_id"] not in (None, ""):
        v = str(out["account_id"]).strip()
        a = db.scalar(select(FinanceAccount).where((func.upper(FinanceAccount.code) == v.upper()) | (func.lower(FinanceAccount.name) == v.lower())))
        if not a:
            raise ValueError(f"Unknown account '{v}'")
        out["account_id"] = a.id
    return {k: (None if v == "" else v) for k, v in out.items()}


def _fields(op: dict) -> dict:
    f = op.get("fields") or []
    if isinstance(f, dict):
        return {str(k): ("" if v is None else str(v).translate(DIGITS)) for k, v in f.items()}
    return {str(x["name"]): ("" if x.get("value") is None else str(x["value"]).translate(DIGITS)) for x in f}


def _validate(schema, data: dict) -> dict:
    try:
        return schema.model_validate(data).model_dump(exclude_unset=True)
    except ValidationError as e:
        raise ValueError("; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()))


def _diff(obj, changes: dict) -> list[dict]:
    before = snapshot(obj) if obj is not None else {}
    after = jsonable(changes)
    return [{"field": k, "from": before.get(k), "to": after[k]} for k in after if before.get(k) != after[k]]


def check_operation(db: Session, op: dict, prompt: str, user: User) -> dict:
    """Validate one operation. Returns a preview row (with 'error' if it cannot be applied)."""
    kind = op.get("op")
    target = str(op.get("target") or "").strip().translate(DIGITS)
    row = {"op": kind, "target": target, "fields": _fields(op), "changes": [], "error": None}
    try:
        if kind not in OPS:
            raise ValueError("Unknown operation")
        f = _resolve_refs(db, row["fields"])
        if kind in ("update_well", "create_well"):
            if not target.isdigit():
                raise ValueError("A Well ID is needed")
            wid = int(target)
            if {"delivery_status", "delivery_date"} & set(f):
                raise ValueError("Delivery can only be confirmed on the Delivery page")
            unknown = set(f) - set(WELL_FIELDS)
            if unknown:
                raise ValueError(f"Unknown field(s): {', '.join(sorted(unknown))}")
            p = psvc.get_by_well_id(db, wid)
            if kind == "update_well":
                if not p:
                    raise ValueError(f"No well with ID {wid}")
                data = _validate(ProjectUpdate, f)
                row["changes"], row["expected_version"] = _diff(p, data), p.version
                row["label"] = f"{wid} · {p.customer_name or ''}".strip(" ·")
            else:
                if p:
                    raise ValueError(f"Well ID {wid} already exists")
                if wid not in _numbers_in(prompt):
                    raise ValueError(f"Well ID {wid} was not written in your request, so it will not be created")
                data = _validate(ProjectCreate, f | {"well_id": wid})
                row["changes"], row["label"] = _diff(None, data), f"{wid} (new)"
        elif kind in ("update_sacrifice", "create_sacrifice"):
            if not target.isdigit():
                raise ValueError("A sacrifice number is needed")
            no = int(target)
            s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no))
            if kind == "update_sacrifice":
                if not s:
                    raise ValueError(f"No sacrifice number {no}")
                data = _validate(SacrificeUpdate, f)
                row["changes"], row["expected_version"], row["label"] = _diff(s, data), s.version, f"S {no}"
            else:
                if s:
                    raise ValueError(f"Sacrifice number {no} already exists")
                if no not in _numbers_in(prompt):
                    raise ValueError(f"Sacrifice number {no} was not written in your request, so it will not be created")
                data = _validate(SacrificeCreate, f | {"sacrifice_no": no})
                row["changes"], row["label"] = _diff(None, data), f"S {no} (new)"
        elif kind == "add_transaction":
            data = _validate(TransactionCreate, f)
            fin_ok = data.get("kind") != TxKind.contractor_payment or data.get("contractor_id")
            if not fin_ok:
                raise ValueError("A contractor payment needs a contractor")
            row["changes"], row["label"] = _diff(None, data), "New money row"
        elif kind in ("update_transaction", "void_transaction"):
            if not target.isdigit():
                raise ValueError("A transaction id is needed")
            t = db.get(Transaction, int(target))
            if not t:
                raise ValueError(f"No transaction {target}")
            if t.voided:
                raise ValueError("This row is already voided")
            if kind == "void_transaction":
                reason = (f.get("reason") or "").strip() or "Voided by prompt"
                row["changes"], row["label"] = [{"field": "voided", "from": False, "to": True}, {"field": "void_reason", "from": None, "to": reason}], f"Row {t.id}"
            else:
                data = _validate(TransactionUpdate, f)
                row["changes"], row["expected_version"], row["label"] = _diff(t, data), t.version, f"Row {t.id}"
        if not row["changes"]:
            raise ValueError("Nothing would change")
        for c in row["changes"]:  # show codes, not database ids
            for fld, model in (("contractor_id", Contractor), ("account_id", FinanceAccount)):
                if c["field"] == fld:
                    for side in ("from", "to"):
                        if c[side] is not None:
                            obj = db.get(model, int(c[side]))
                            c[side] = obj.code if obj else c[side]
    except ValueError as e:
        row["error"] = str(e)
    except HTTPException as e:
        row["error"] = e.detail
    return row


def plan(db: Session, prompt: str, page: dict | None, user: User) -> dict:
    check_available(db)
    raw, usage = _call_model(db, prompt, page)
    cost = _record_usage(db, usage, ref=user.email)
    audit(db, "assistant.plan", "assistant", None, actor=user, after={"prompt": prompt, "page": page, "plan": raw})
    db.commit()
    ops = [check_operation(db, op, prompt, user) for op in (raw.get("operations") or [])[:100]]
    return {"summary": raw.get("summary") or "", "questions": raw.get("questions") or [], "operations": ops,
            "cost_usd": round(cost, 4), "can_apply": bool(ops) and all(not o["error"] for o in ops)}


def apply(db: Session, prompt: str, operations: list[dict], user: User) -> dict:
    """Re-validate every operation and execute them together. All or nothing."""
    checked = [check_operation(db, op, prompt, user) | {"expected_version": op.get("expected_version")} for op in operations]
    bad = [c for c in checked if c["error"]]
    if bad:
        raise HTTPException(422, "; ".join(f"{c.get('label') or c['target']}: {c['error']}" for c in bad))
    done = []
    for op in checked:
        f = _resolve_refs(db, op["fields"])
        k, ev, src = op["op"], op.get("expected_version"), "assistant"
        if k == "update_well":
            p = psvc.require_project(db, int(op["target"]), for_update=True)
            psvc.update_project(db, p, _validate(ProjectUpdate, f), actor=user, source=src, expected_version=ev)
        elif k == "create_well":
            psvc.create_project(db, _validate(ProjectCreate, f | {"well_id": int(op["target"])}), actor=user, source=src)
        elif k == "update_sacrifice":
            s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == int(op["target"])).with_for_update())
            fin.update_sacrifice(db, s, _validate(SacrificeUpdate, f), actor=user, expected_version=ev, source=src)
        elif k == "create_sacrifice":
            fin.create_sacrifice(db, _validate(SacrificeCreate, f | {"sacrifice_no": int(op["target"])}), actor=user, source=src)
        elif k == "add_transaction":
            fin.create_transaction(db, _validate(TransactionCreate, f), actor=user, source=src)
        elif k == "update_transaction":
            t = db.get(Transaction, int(op["target"]), with_for_update=True)
            fin.update_transaction(db, t, _validate(TransactionUpdate, f), actor=user, expected_version=ev, source=src)
        elif k == "void_transaction":
            t = db.get(Transaction, int(op["target"]), with_for_update=True)
            fin.void_transaction(db, t, (f.get("reason") or "Voided by prompt"), actor=user, source=src)
        done.append({"op": k, "target": op["target"], "label": op.get("label")})
    audit(db, "assistant.apply", "assistant", None, actor=user, after={"prompt": prompt, "operations": jsonable(checked)})
    db.commit()
    return {"applied": len(done), "operations": done}

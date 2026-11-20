"""The floating assistant: explains how to use HAYAH AI (Hayah, 2026-11-19).

- Answers from the system guide (`app/system_guide.md`), in Arabic or English.
- Read only. It has no tool that writes; it can only look up one well (and, for managers, one
  sacrifice) by its number, through the same visibility rules as the pages:
  costs and money only for managers, a contractor only sees their own wells, phone numbers never.
- Uses the same Anthropic key and the same monthly AI budget as «عدّل بكتابة طلب».
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import MANAGERS
from app.models import FinalVideo, Plaque, Project, Role, Sacrifice, UsageRecord, User
from app.services import assistant as edit_svc
from app.services.audit import jsonable

GUIDE = Path(__file__).resolve().parent.parent / "system_guide.md"
MAX_TURNS = 12          # messages kept from the conversation
MAX_TOOL_ROUNDS = 3

UNAVAILABLE = {
    "no_key": "The assistant needs the AI key, which is not connected yet. A manager adds it in Settings → AI.",
    "ai_off": "AI is turned off in Settings. A manager can turn it on there.",
    "budget": "This month's AI budget is used up. A manager can see it in Settings → AI.",
}


@lru_cache
def _guide_sections() -> list[tuple[str, str]]:
    text = GUIDE.read_text(encoding="utf-8")
    parts = re.split(r"<!--\s*section:\s*(\w+)\s*-->", text)
    out = [("all", parts[0])]
    for i in range(1, len(parts), 2):
        out.append((parts[i], parts[i + 1]))
    return out


def guide_for(role: Role) -> str:
    """The guide with the manager-only sections removed for everyone else."""
    manager = role in MANAGERS
    return "".join(body for who, body in _guide_sections() if who == "all" or (who == "managers" and manager)).strip()


def _system(user: User) -> list[dict]:
    manager = user.role in MANAGERS
    rules = f"""You are the help assistant inside HAYAH AI, the HAYAH Foundation's operations system.
The person asking is signed in as role "{user.role.value}"{" (a manager)" if manager else ""}.

How to answer:
- Answer in the language of the question (Arabic or English). Be short, friendly and practical: say where
  to tap or which page to open, step by step when useful. Use the page names exactly as in the guide.
- Answer only from the guide below and from the lookup tools. If the guide does not cover it, say you are
  not sure and suggest asking a manager. Never invent pages, buttons or numbers.
- You only explain. You cannot change anything. If asked to change data, explain how the person can do it
  themselves{" (or that «عدّل بكتابة طلب» can do it with a preview)" if manager else ""}.
- {"You may discuss money, costs and profit." if manager else "Never discuss cost, contractor cost, profit, ads, money accounts or finance. If asked, say that this is for managers only."}
- Never reveal phone numbers, API keys or other people's personal details.
- To answer about a specific well{" or sacrifice" if manager else ""}, use the lookup tool with its number.

The system guide:
"""
    return [{"type": "text", "text": rules + guide_for(user.role), "cache_control": {"type": "ephemeral"}}]


def _tools(user: User) -> list[dict]:
    tools = [{"name": "lookup_well", "description": "Look up one well (project) by its Well ID / project number.",
              "input_schema": {"type": "object", "properties": {"number": {"type": "integer"}}, "required": ["number"]}}]
    if user.role in MANAGERS:
        tools.append({"name": "lookup_sacrifice", "description": "Look up one sacrifice by its number.",
                      "input_schema": {"type": "object", "properties": {"number": {"type": "integer"}}, "required": ["number"]}})
    return tools


def _status(db: Session, model, col, obj_id) -> str | None:
    row = db.scalar(select(model).where(col == obj_id))
    return row.status.value if row else None


def lookup_well(db: Session, user: User, number: int) -> dict:
    p = db.scalar(select(Project).where(Project.well_id == int(number), Project.merged_into_id.is_(None)))
    if not p or (user.role == Role.contractor and p.contractor_id != user.contractor_id):
        return {"found": False, "number": number}
    out = {"found": True, "well_id": p.well_id, "page": f"/projects/{p.well_id}", "customer": p.customer_name,
           "country": p.country, "well_type": p.well_type,
           "contractor": p.contractor.name if p.contractor else None,
           "order_date": p.order_date, "construction_status": p.construction_status,
           "delivery_status": p.delivery_status, "delivery_date": p.delivery_date,
           "payment_status": p.payment_status, "video_status": p.video_status,
           "sales_source": p.source_group, "selling_price_usd": p.sale_amount,
           "plaque_status": _status(db, Plaque, Plaque.project_id, p.id),
           "final_video_status": _status(db, FinalVideo, FinalVideo.project_id, p.id)}
    if user.role in MANAGERS:
        out["cost_usd"] = p.cost
    if user.role in (Role.contractor, Role.viewer, Role.maintenance):
        out.pop("selling_price_usd")
        out.pop("payment_status")
    return jsonable(out)


def lookup_sacrifice(db: Session, user: User, number: int) -> dict:
    if user.role not in MANAGERS:
        return {"error": "Sacrifices are for managers only."}
    s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == int(number)))
    if not s:
        return {"found": False, "number": number}
    return jsonable({"found": True, "sacrifice_no": s.sacrifice_no, "page": f"/plaque/sacrifice/{s.sacrifice_no}",
                     "donor": s.donor_name, "animal": s.animal_type, "order_date": s.order_date,
                     "delivery_date": s.delivery_date, "contractor": s.contractor.name if s.contractor else None,
                     "sales_source": s.source_group, "sale_price_usd": s.sale_price, "cost_usd": s.cost,
                     "plaque_status": _status(db, Plaque, Plaque.sacrifice_id, s.id),
                     "final_video_status": _status(db, FinalVideo, FinalVideo.sacrifice_id, s.id)})


def run_tool(db: Session, user: User, name: str, args: dict) -> dict:
    try:
        n = int(str((args or {}).get("number", "")).strip())
    except ValueError:
        return {"error": "A number is needed."}
    if name == "lookup_well":
        return lookup_well(db, user, n)
    if name == "lookup_sacrifice":
        return lookup_sacrifice(db, user, n)
    return {"error": "Unknown tool"}


def _create(db: Session, **kw):
    """One model call. Isolated so tests can replace it."""
    import anthropic

    from app.services.secrets_store import anthropic_key
    client = anthropic.Anthropic(api_key=anthropic_key(db), timeout=90.0)
    try:
        return client.beta.messages.create(model=get_settings().anthropic_model, max_tokens=4000,
                                           output_config={"effort": "low"},
                                           betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
    except anthropic.AuthenticationError:
        raise edit_svc.AssistantUnavailable("The AI key was rejected. A manager can paste a new key in Settings → AI.", "no_key")
    except anthropic.RateLimitError:
        raise edit_svc.AssistantUnavailable("The assistant is busy right now. Try again in a minute.", "busy")
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        raise edit_svc.AssistantUnavailable("The assistant could not answer right now. Try again.", "error")


def _record(db: Session, resp, user: User) -> float:
    s, u = get_settings(), resp.usage
    tokens_in = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) * 1.25 \
        + (getattr(u, "cache_read_input_tokens", 0) or 0) * 0.1
    cost = (tokens_in * s.anthropic_input_usd_per_mtok + (u.output_tokens or 0) * s.anthropic_output_usd_per_mtok) / 1_000_000
    db.add(UsageRecord(service="anthropic", operation="help_chat", ref=user.email,
                       units={"model": resp.model, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
                       est_cost_usd=Decimal(str(round(cost, 6)))))
    return cost


def ask(db: Session, user: User, messages: list[dict], page: str | None = None) -> dict:
    try:
        edit_svc.check_available(db)
    except edit_svc.AssistantUnavailable as e:
        raise edit_svc.AssistantUnavailable(UNAVAILABLE.get(e.code, e.detail), e.code)
    convo = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in messages[-MAX_TURNS:]
             if m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()]
    while convo and convo[0]["role"] != "user":
        convo.pop(0)
    if not convo or convo[-1]["role"] != "user":
        raise HTTPException(422, "Ask a question first.")
    if page:
        convo[-1] = {"role": "user", "content": f"(I am on the page {page[:200]})\n{convo[-1]['content']}"}
    system, tools, cost, looked_up = _system(user), _tools(user), 0.0, []
    for _ in range(MAX_TOOL_ROUNDS + 1):
        resp = _create(db, system=system, tools=tools, messages=convo)
        cost += _record(db, resp, user)
        if resp.stop_reason != "tool_use":
            break
        convo.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                r = run_tool(db, user, b.name, b.input)
                looked_up.append({"tool": b.name, "number": (b.input or {}).get("number"), "found": r.get("found")})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(r, ensure_ascii=False)})
        convo.append({"role": "user", "content": results})
    db.commit()
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "refusal" or not text:
        text = "I can't help with that one. Try asking another way."
    return {"answer": text, "looked_up": looked_up, "cost_usd": round(cost, 4)}

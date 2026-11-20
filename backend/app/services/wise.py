"""Wise, read only (Hayah, 2026-11-19, item 6).

- Only GET requests are ever sent to Wise. There is no code that creates, funds or cancels a
  transfer. The token is a Wise *read only* personal API token, stored encrypted on the server
  (Settings → Wise), never sent to the browser.
- sync(): reads the business profile's activity feed (newest first) and stores each activity once
  (unique `wise_id`), so running it again never duplicates anything.
- Each activity is classified: shopify_payout (money in from SHOPIFY; Shopify pays out in batches,
  not one payment per order), contractor (out to a recipient mapped to a contractor), ads (Facebook /
  Meta / Google ads), tools (Hetzner, Anthropic, Shopify plan ...), conversion / neutral, other.
- Matching: an activity is matched to an existing Wise ledger row with the same direction, the same
  USD amount (to the cent) and a date within 5 days. Ambiguous cases are left unmatched for a person.
- Unmatched activities are listed. A manager can match one to a ledger row, ignore it, or record it
  in the ledger (one click, using the classification); recording twice is impossible.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Contractor, FinanceAccount, Transaction, TxKind, User, WiseTransaction, utcnow
from app.services import finance as fin
from app.services.audit import audit
from app.services.jobs import handler
from app.services.secrets_store import get_secret, secret_hint, set_secret
from app.services.settings_store import get_setting, set_setting

API = "https://api.wise.com"
SECRET = "wise_token"
SETTING = "wise"
DEFAULT_CFG = {
    "profile_id": None,  # chosen automatically: the BUSINESS profile
    "recipient_contractors": {},  # "ghaidaa sabbah" -> "UK1"  (confirmed by a manager)
    "ads_words": ["facebook", "facebk", "meta", "instagram", "google ads", "tiktok"],
    "tool_words": ["hetzner", "anthropic", "shopify", "openai", "canva", "google", "apple", "zoom"],
    "first_sync_days": 120,
}
WINDOW_DAYS = 5


# ---------------- settings / token ----------------
def cfg(db: Session) -> dict:
    return DEFAULT_CFG | (get_setting(db, SETTING) or {})


def save_cfg(db: Session, changes: dict, user: User) -> dict:
    new = cfg(db) | {k: v for k, v in changes.items() if k in DEFAULT_CFG}
    if "recipient_contractors" in changes:
        new["recipient_contractors"] = {_norm(k): str(v).strip().upper() for k, v in (changes["recipient_contractors"] or {}).items()
                                        if str(k).strip() and str(v).strip()}
        for code in new["recipient_contractors"].values():
            if not db.scalar(select(Contractor.id).where(func.upper(Contractor.code) == code)):
                raise HTTPException(422, f"Unknown contractor code {code}")
    set_setting(db, SETTING, new, user.id)
    audit(db, "wise.settings", "setting", SETTING, actor=user, after={k: new[k] for k in ("profile_id", "recipient_contractors")})
    return new


def set_token(db: Session, token: str | None, user: User) -> dict:
    token = (token or "").strip()
    if token:
        prof = _business_profile(token)  # check it works (read only) before saving
        set_secret(db, SECRET, token, user.id)
        c = cfg(db); c["profile_id"] = prof["id"]; c["profile_name"] = _profile_name(prof)
        set_setting(db, SETTING, c, user.id)
    else:
        set_secret(db, SECRET, None, user.id)
    audit(db, "wise.token", "setting", SECRET, actor=user, after={"set": bool(token)})
    db.commit()
    return status(db)


def status(db: Session) -> dict:
    c = cfg(db)
    last = db.scalar(select(func.max(WiseTransaction.at)))
    counts = dict(db.execute(select(WiseTransaction.match_status, func.count()).group_by(WiseTransaction.match_status)).all())
    return {"token": secret_hint(db, SECRET), "profile_id": c.get("profile_id"), "profile_name": c.get("profile_name"),
            "last_activity": last, "last_sync": c.get("last_sync"), "last_error": c.get("last_error"),
            "counts": {k: counts.get(k, 0) for k in ("unmatched", "matched", "ignored")},
            "recipient_contractors": c.get("recipient_contractors") or {}}


# ---------------- Wise API (GET only) ----------------
def _get(token: str, path: str, params: dict | None = None) -> dict | list:
    try:
        r = httpx.get(API + path, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach Wise. Try again later.")
    if r.status_code in (401, 403):
        raise HTTPException(400, "Wise refused the token. Make a new read only token in Wise (Settings → API tokens) and paste it again.")
    if r.status_code >= 400:
        raise HTTPException(502, f"Wise answered {r.status_code}. Nothing was changed.")
    return r.json()


def _profile_name(p: dict) -> str:
    d = p.get("details") or {}
    return p.get("fullName") or d.get("name") or d.get("businessName") or str(p.get("id"))


def _business_profile(token: str) -> dict:
    profiles = _get(token, "/v2/profiles")
    biz = [p for p in profiles if str(p.get("type", "")).upper() == "BUSINESS"]
    if not biz:
        raise HTTPException(422, "This Wise token has no business profile.")
    return biz[0]


def fetch_activities(token: str, profile_id: int, since: datetime) -> list[dict]:
    """Newest first, until `since`. Isolated so tests can replace it."""
    out, cursor = [], None
    for _ in range(50):  # at most 50 pages of 100
        params = {"size": 100, "since": since.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
        if cursor:
            params["nextCursor"] = cursor
        page = _get(token, f"/v1/profiles/{profile_id}/activities", params)
        out += page.get("activities") or []
        cursor = page.get("cursor")
        if not cursor or not page.get("activities"):
            break
    return out


# ---------------- parsing / classification ----------------
_TAG = re.compile(r"<[^>]+>")
_AMT = re.compile(r"([+\-−])?\s*([\d.,]+)\s*([A-Z]{3})")


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _text(s) -> str:
    return html.unescape(_TAG.sub("", str(s or ""))).strip()


def parse_amount(s) -> tuple[str | None, Decimal | None, str | None]:
    """'<positive>+ 2,570.38 USD</positive>' -> ('+', 2570.38, 'USD')."""
    raw = str(s or "")
    m = _AMT.search(_text(raw))
    if not m:
        return None, None, None
    sign = m.group(1) or ("+" if "<positive>" in raw else ("-" if "<negative>" in raw else None))
    try:
        return sign, Decimal(m.group(2).replace(",", "")), m.group(3)
    except InvalidOperation:
        return None, None, None


def parse_activity(a: dict) -> dict:
    sign, amount, cur = parse_amount(a.get("primaryAmount"))
    _, sec_amount, sec_cur = parse_amount(a.get("secondaryAmount"))
    title, desc = _text(a.get("title")), _text(a.get("description"))
    t = str(a.get("type") or "").upper()
    if t in ("BALANCE_CASHBACK", "INTEREST") or sign == "+" or _norm(desc).startswith(("received", "added")):
        direction = "in"
    elif t in ("CONVERSION", "BALANCE_DEPOSIT_MOVE") or (amount == 0) or "CARD_CHECK" in t:
        direction = "neutral"
    else:
        direction = "out"
    usd = amount if cur == "USD" else (sec_amount if sec_cur == "USD" else None)
    res = a.get("resource") or {}
    return {"wise_id": str(a.get("id")), "at": _dt(a.get("createdOn")), "activity_type": t[:40] or None,
            "status": str(a.get("status") or "")[:30] or None, "direction": direction, "amount": amount or Decimal(0),
            "currency": cur or "USD", "usd_amount": usd, "counterparty": title[:200] or None, "description": desc or None,
            "resource_type": str(res.get("type") or "")[:40] or None, "resource_id": str(res.get("id") or "")[:60] or None}


def _dt(s) -> datetime:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return utcnow()


def classify(db: Session, row: dict, c: dict) -> tuple[str, int | None]:
    who = _norm(row.get("counterparty"))
    if row["direction"] == "neutral":
        return "neutral", None
    if row["direction"] == "in":
        return ("shopify_payout" if "shopify" in who else "income"), None
    code = (c.get("recipient_contractors") or {}).get(who)
    if code:
        cid = db.scalar(select(Contractor.id).where(func.upper(Contractor.code) == code.upper()))
        return "contractor", cid
    if any(w in who for w in c.get("ads_words") or []):
        return "ads", None
    if any(w in who for w in c.get("tool_words") or []):
        return "tools", None
    if row.get("activity_type") == "TRANSFER":
        return "transfer_out", None  # someone paid by transfer, not yet mapped to a contractor
    return "other", None


# ---------------- matching ----------------
def _wise_account(db: Session) -> FinanceAccount | None:
    return db.scalar(select(FinanceAccount).where(func.upper(FinanceAccount.code) == "WISE"))


def find_match(db: Session, w: WiseTransaction) -> Transaction | None:
    acc = _wise_account(db)
    if not acc or w.direction == "neutral" or w.usd_amount is None:
        return None
    d = w.at.date()
    taken = select(WiseTransaction.transaction_id).where(WiseTransaction.transaction_id.is_not(None))
    q = select(Transaction).where(Transaction.account_id == acc.id, Transaction.voided.is_(False),
                                  Transaction.direction == w.direction, Transaction.amount == w.usd_amount,
                                  Transaction.date.between(d - timedelta(days=WINDOW_DAYS), d + timedelta(days=WINDOW_DAYS)),
                                  Transaction.id.not_in(taken))
    hits = db.scalars(q).all()
    return hits[0] if len(hits) == 1 else None  # two candidates: a person decides


def _link(w: WiseTransaction, t: Transaction, by: str):
    w.transaction_id, w.match_status, w.matched_by, w.matched_at = t.id, "matched", by, utcnow()


# ---------------- sync ----------------
def sync(db: Session, actor: User | None = None, *, _fetch=None) -> dict:
    token = get_secret(db, SECRET)
    if not token:
        raise HTTPException(422, "Wise is not connected. Paste a read only token in Settings → Wise.")
    c = cfg(db)
    if not c.get("profile_id"):
        prof = _business_profile(token)
        c["profile_id"], c["profile_name"] = prof["id"], _profile_name(prof)
    last = db.scalar(select(func.max(WiseTransaction.at)))
    since = (last - timedelta(days=3)) if last else utcnow() - timedelta(days=int(c.get("first_sync_days") or 120))
    try:
        acts = (_fetch or fetch_activities)(token, int(c["profile_id"]), since)
    except HTTPException as e:
        c["last_error"] = e.detail; set_setting(db, SETTING, c, actor.id if actor else None); db.commit()
        raise
    new = matched = 0
    known = set(db.scalars(select(WiseTransaction.wise_id).where(WiseTransaction.wise_id.in_([str(a.get("id")) for a in acts]))))
    for a in acts:
        row = parse_activity(a)
        if row["wise_id"] in known or not row["wise_id"]:
            continue
        if row["status"] and row["status"].upper() in ("CANCELLED", "REFUNDED"):
            continue
        row["category"], row["contractor_id"] = classify(db, row, c)
        w = WiseTransaction(profile_id=int(c["profile_id"]), raw=a, **row)
        if row["direction"] == "neutral":
            w.match_status = "ignored"
        db.add(w); db.flush()
        known.add(row["wise_id"]); new += 1
        t = find_match(db, w) if w.match_status == "unmatched" else None
        if t:
            _link(w, t, "auto"); matched += 1
    c["last_sync"], c["last_error"] = utcnow().isoformat(), None
    set_setting(db, SETTING, c, actor.id if actor else None)
    audit(db, "wise.sync", "wise", c["profile_id"], actor=actor, actor_label=None if actor else "worker",
          after={"read": len(acts), "new": new, "auto_matched": matched})
    db.commit()
    return {"read": len(acts), "new": new, "auto_matched": matched}


@handler("wise_sync")
def _job(db: Session, payload: dict):
    if get_secret(db, SECRET):
        return sync(db)
    return {"skipped": "not connected"}


# ---------------- review actions (managers) ----------------
def list_rows(db: Session, status_: str | None = "unmatched", limit: int = 300) -> list[dict]:
    q = select(WiseTransaction).order_by(WiseTransaction.at.desc()).limit(limit)
    if status_:
        q = q.where(WiseTransaction.match_status == status_)
    out = []
    for w in db.scalars(q):
        out.append({"id": w.id, "at": w.at, "direction": w.direction, "amount": w.amount, "currency": w.currency,
                    "usd_amount": w.usd_amount, "counterparty": w.counterparty, "description": w.description,
                    "type": w.activity_type, "category": w.category, "contractor": w.contractor.code if w.contractor else None,
                    "match_status": w.match_status, "transaction_id": w.transaction_id})
    return out


def _require(db: Session, wid: int) -> WiseTransaction:
    w = db.get(WiseTransaction, wid, with_for_update=True)
    if not w:
        raise HTTPException(404, "No such Wise transaction")
    return w


def match(db: Session, wid: int, transaction_id: int, user: User) -> dict:
    w, t = _require(db, wid), db.get(Transaction, transaction_id)
    if not t or t.voided:
        raise HTTPException(404, "No such ledger row")
    if db.scalar(select(WiseTransaction.id).where(WiseTransaction.transaction_id == t.id, WiseTransaction.id != w.id)):
        raise HTTPException(409, "That ledger row is already matched to another Wise transaction")
    _link(w, t, user.email)
    audit(db, "wise.match", "wise_transaction", w.id, actor=user, after={"transaction_id": t.id})
    db.commit()
    return {"ok": True}


def ignore(db: Session, wid: int, user: User, undo: bool = False) -> dict:
    w = _require(db, wid)
    if w.match_status == "matched":
        raise HTTPException(409, "It is matched. Unmatch it first.")
    w.match_status = "unmatched" if undo else "ignored"
    audit(db, "wise.unignore" if undo else "wise.ignore", "wise_transaction", w.id, actor=user)
    db.commit()
    return {"ok": True}


def unmatch(db: Session, wid: int, user: User) -> dict:
    w = _require(db, wid)
    before = w.transaction_id
    w.transaction_id, w.match_status, w.matched_by, w.matched_at = None, "unmatched", None, None
    audit(db, "wise.unmatch", "wise_transaction", w.id, actor=user, before={"transaction_id": before})
    db.commit()
    return {"ok": True}


KIND_BY_CATEGORY = {"shopify_payout": TxKind.income, "income": TxKind.income, "contractor": TxKind.contractor_payment,
                    "ads": TxKind.ad_spend, "tools": TxKind.operating_expense}


def record(db: Session, wid: int, user: User, kind: str | None = None, contractor_code: str | None = None) -> dict:
    """Add an unmatched Wise transaction to the ledger (Wise account) and link it. Never twice."""
    w = _require(db, wid)
    if w.match_status != "unmatched":
        raise HTTPException(409, "Only unmatched transactions can be recorded")
    if w.usd_amount is None:
        raise HTTPException(422, "The US dollar amount is not known for this one. Record it by hand.")
    acc = _wise_account(db)
    if not acc:
        raise HTTPException(422, "There is no Wise account in the ledger")
    k = TxKind(kind) if kind else KIND_BY_CATEGORY.get(w.category, TxKind.other)
    cid = w.contractor_id
    if contractor_code:
        cid = db.scalar(select(Contractor.id).where(func.upper(Contractor.code) == contractor_code.strip().upper()))
        if not cid:
            raise HTTPException(422, "Unknown contractor")
    desc = f"Wise: {w.counterparty or ''}" + (f" ({w.amount} {w.currency})" if w.currency != "USD" else "")
    t = fin.create_transaction(db, {"date": w.at.date(), "kind": k, "direction": w.direction, "account_id": acc.id,
                                    "contractor_id": cid if k == TxKind.contractor_payment else None,
                                    "channel": w.counterparty if k == TxKind.ad_spend else None,
                                    "amount": w.usd_amount, "currency": "USD", "description": desc,
                                    "reference": f"wise:{w.resource_id or w.id}"[:120]}, actor=user, source="wise")
    _link(w, t, user.email)
    db.commit()
    return {"transaction_id": t.id}


def candidates(db: Session, wid: int) -> list[dict]:
    """Ledger rows a person might match this to (same direction, Wise account, ±10 days)."""
    w, acc = _require(db, wid), _wise_account(db)
    if not acc:
        return []
    d = w.at.date()
    taken = select(WiseTransaction.transaction_id).where(WiseTransaction.transaction_id.is_not(None))
    rows = db.scalars(select(Transaction).where(Transaction.account_id == acc.id, Transaction.voided.is_(False),
                                                Transaction.direction == w.direction, Transaction.id.not_in(taken),
                                                Transaction.date.between(d - timedelta(days=10), d + timedelta(days=10)))
                      .order_by(func.abs(Transaction.amount - (w.usd_amount or 0))).limit(8))
    return [{"id": t.id, "date": t.date, "amount": t.amount, "kind": t.kind.value, "description": t.description} for t in rows]

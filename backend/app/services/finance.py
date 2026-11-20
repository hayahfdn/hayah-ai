"""Finance workbook: sacrifices, money accounts, transactions, ledgers and the
Financial Summary. Mirrors HAYAH's Excel workbook (one tab per contractor,
partner, bank account and month) but every number is computed from the
database, so the pages can never drift apart.

Rules:
- Nothing is deleted. A wrong transaction is voided with a reason.
- Every write is validated, versioned and written to the audit log.
- Sacrifice numbers and Well IDs come from people, never from AI.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Contractor, FinanceAccount, Project, Sacrifice, Transaction, TX_DEFAULT_DIRECTION, TxKind, User, utcnow,
)
from app.services import phones
from app.services.audit import audit, snapshot

# The tabs HAYAH asked for. Codes are stable; names can be edited in Contractors.
DEFAULT_CONTRACTORS = [
    ("PAK1", "Pak 1", "Pakistan"), ("PAK2", "Pak 2", "Pakistan"), ("PAK3", "Pak 3", "Pakistan"),
    ("PAK4", "Pak 4", "Pakistan"), ("PAK5", "Pak 5", "Pakistan"),
    ("NEP1", "Nepal 1", "Nepal"), ("NEP2", "Nepal 2", "Nepal"), ("NEP3", "Nepal 3", "Nepal"),
    ("BANG1", "Bangladesh 1", "Bangladesh"), ("TZ1", "Tanzania 1", "Tanzania"),
]
DEFAULT_ACCOUNTS = [
    ("WISE", "Wise bank (UK company account)", "bank", 0),
    ("MOHAMMED", "Mohammed", "partner", 1),
    ("GHAZI", "Ghazi", "partner", 2),
    ("CLIQ", "Haya Cliq (Jordan)", "partner", 3),
]
D0 = Decimal("0")
# An operating expense in this category, linked to a contractor, is extra work the contractor
# billed (transport, filming, repairs): it adds to what the company owes that contractor.
EXTRA_WORK = "Contractor extra work"


def ensure_workbook_defaults(db: Session) -> None:
    """Create the standard contractor and account tabs if they are missing. Safe to run repeatedly."""
    for code, name, country in DEFAULT_CONTRACTORS:
        if not db.scalar(select(Contractor).where(Contractor.code == code)):
            db.add(Contractor(code=code, name=name, country=country))
    for code, name, kind, order in DEFAULT_ACCOUNTS:
        if not db.scalar(select(FinanceAccount).where(FinanceAccount.code == code)):
            db.add(FinanceAccount(code=code, name=name, kind=kind, sort_order=order))
    db.flush()


def _d(v) -> Decimal:
    return Decimal(v) if v is not None else D0


def _check_contractor(db: Session, cid: int | None):
    if cid is not None and not db.get(Contractor, cid):
        raise HTTPException(422, "Unknown contractor")


def month_bounds(month: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in month.split("-"))
        start = date(y, m, 1)
    except Exception:
        raise HTTPException(422, "Month must look like 2026-11")
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start, end


# ---------------- sacrifices ----------------
def create_sacrifice(db: Session, data: dict, *, actor: User | None, is_sample: bool = False,
                     source: str = "dashboard") -> Sacrifice:
    if db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == data["sacrifice_no"])):
        raise HTTPException(409, f"Sacrifice number {data['sacrifice_no']} already exists")
    _check_contractor(db, data.get("contractor_id"))
    hints = data.pop("_phone_hints", None)
    fallback = data.pop("_phone_fallback_country", None)
    if data.get("extras") is not None:
        from app.services.addons import normalize
        data["extras"] = normalize(data["extras"])
    s = Sacrifice(**data, is_sample=is_sample)
    phones.apply(s, hints=hints, fallback_country=fallback)
    try:
        with db.begin_nested():
            db.add(s)
            db.flush()
    except IntegrityError:
        raise HTTPException(409, f"Sacrifice number {data['sacrifice_no']} already exists")
    audit(db, "sacrifice.create", "sacrifice", s.sacrifice_no, actor=actor, actor_label=_label(actor, source),
          after=snapshot(s))
    from app.services.plaque_flow import maybe_create_for_new_order
    maybe_create_for_new_order(db, s, source=source, is_sample=is_sample, actor=actor)
    return s


def update_sacrifice(db: Session, s: Sacrifice, changes: dict, *, actor: User | None,
                     expected_version: int | None = None, source: str = "dashboard") -> Sacrifice:
    if expected_version is not None and expected_version != s.version:
        raise HTTPException(409, "This sacrifice was changed by someone else. Reload and try again.")
    bad = {"id", "sacrifice_no", "version", "is_sample"} & set(changes)
    if bad:
        raise HTTPException(422, f"These fields cannot be changed here: {', '.join(sorted(bad))}")
    if "contractor_id" in changes:
        _check_contractor(db, changes["contractor_id"])
    if changes.get("extras") is not None:
        from app.services.addons import normalize
        changes = {**changes, "extras": normalize(changes["extras"])}
    before = snapshot(s)
    for k, v in changes.items():
        setattr(s, k, v)
    if {"customer_phone", "customer_phone_country"} & set(changes):
        phones.apply(s)
    if snapshot(s) == before:
        return s
    s.updated_at = utcnow()
    db.flush()
    audit(db, "sacrifice.update", "sacrifice", s.sacrifice_no, actor=actor, actor_label=_label(actor, source),
          before=before, after=snapshot(s))
    return s


def list_sacrifices(db: Session, *, month: str | None = None, contractor_id: int | None = None) -> list[Sacrifice]:
    q = select(Sacrifice)
    if month:
        a, b = month_bounds(month)
        q = q.where(Sacrifice.order_date >= a, Sacrifice.order_date < b)
    if contractor_id:
        q = q.where(Sacrifice.contractor_id == contractor_id)
    return list(db.scalars(q.order_by(Sacrifice.order_date.desc().nulls_last(), Sacrifice.sacrifice_no.desc())))


# ---------------- transactions ----------------
def create_transaction(db: Session, data: dict, *, actor: User | None, is_sample: bool = False,
                       source: str = "dashboard") -> Transaction:
    data = dict(data)
    kind = TxKind(data["kind"])
    data["direction"] = data.get("direction") or TX_DEFAULT_DIRECTION[kind]
    if data.get("account_id") is not None and not db.get(FinanceAccount, data["account_id"]):
        raise HTTPException(422, "Unknown account")
    _check_contractor(db, data.get("contractor_id"))
    if kind == TxKind.contractor_payment and not data.get("contractor_id"):
        raise HTTPException(422, "A contractor payment needs a contractor")
    t = Transaction(**data, is_sample=is_sample, created_by_id=actor.id if actor else None)
    db.add(t)
    db.flush()
    audit(db, "transaction.create", "transaction", t.id, actor=actor, actor_label=_label(actor, source),
          after=snapshot(t))
    return t


def update_transaction(db: Session, t: Transaction, changes: dict, *, actor: User | None,
                       expected_version: int | None = None, source: str = "dashboard") -> Transaction:
    if t.voided:
        raise HTTPException(409, "This row was voided and cannot be edited")
    if expected_version is not None and expected_version != t.version:
        raise HTTPException(409, "This row was changed by someone else. Reload and try again.")
    bad = {"id", "version", "voided", "void_reason", "is_sample", "created_by_id"} & set(changes)
    if bad:
        raise HTTPException(422, f"These fields cannot be changed here: {', '.join(sorted(bad))}")
    if "account_id" in changes and changes["account_id"] is not None and not db.get(FinanceAccount, changes["account_id"]):
        raise HTTPException(422, "Unknown account")
    if "contractor_id" in changes:
        _check_contractor(db, changes["contractor_id"])
    before = snapshot(t)
    for k, v in changes.items():
        setattr(t, k, v)
    if "kind" in changes and "direction" not in changes:
        t.direction = TX_DEFAULT_DIRECTION[TxKind(t.kind)]
    if snapshot(t) == before:
        return t
    t.updated_at = utcnow()
    db.flush()
    audit(db, "transaction.update", "transaction", t.id, actor=actor, actor_label=_label(actor, source),
          before=before, after=snapshot(t))
    return t


def void_transaction(db: Session, t: Transaction, reason: str, *, actor: User | None, source: str = "dashboard"):
    if t.voided:
        raise HTTPException(409, "Already voided")
    before = snapshot(t)
    t.voided, t.void_reason, t.updated_at = True, reason, utcnow()
    db.flush()
    audit(db, "transaction.void", "transaction", t.id, actor=actor, actor_label=_label(actor, source),
          before=before, after=snapshot(t))
    return t


def list_transactions(db: Session, *, account_id: int | None = None, contractor_id: int | None = None,
                      kind: str | None = None, month: str | None = None, include_voided: bool = True):
    q = select(Transaction)
    if account_id:
        q = q.where(Transaction.account_id == account_id)
    if contractor_id:
        q = q.where(Transaction.contractor_id == contractor_id)
    if kind:
        q = q.where(Transaction.kind == kind)
    if month:
        a, b = month_bounds(month)
        q = q.where(Transaction.date >= a, Transaction.date < b)
    if not include_voided:
        q = q.where(Transaction.voided.is_(False))
    return list(db.scalars(q.order_by(Transaction.date, Transaction.id)))


def _label(actor: User | None, source: str) -> str | None:
    if source == "assistant":
        return f"{actor.email if actor else 'system'} (via prompt)"
    return None


# ---------------- ledgers & summary ----------------
def _live_projects():
    return select(Project).where(Project.merged_into_id.is_(None))


def contractor_ledger(db: Session, c: Contractor) -> dict:
    wells = list(db.scalars(_live_projects().where(Project.contractor_id == c.id)
                            .order_by(Project.order_date.desc().nulls_last(), Project.well_id.desc())))
    sac = list_sacrifices(db, contractor_id=c.id)
    payments = list_transactions(db, contractor_id=c.id, kind=TxKind.contractor_payment.value)
    extras = [t for t in list_transactions(db, contractor_id=c.id, kind=TxKind.operating_expense.value)
              if not t.voided and t.category == EXTRA_WORK]
    invoiced = (sum((_d(p.cost) for p in wells), D0) + sum((_d(s.cost) for s in sac), D0)
                + sum((t.amount for t in extras), D0))
    paid = sum((_d(t.amount) for t in payments if not t.voided), D0)
    rows = sorted(payments + extras, key=lambda t: (t.date, t.id))  # extra work shows on the same sheet
    return {"contractor": c, "wells": wells, "sacrifices": sac, "payments": rows,
            "totals": _owed(invoiced, paid) | {"wells": len(wells), "sacrifices": len(sac)}}


def _owed(invoiced: Decimal, paid: Decimal) -> dict:
    return {"invoiced": float(invoiced), "paid": float(paid), "owed": float(invoiced - paid),
            "pct_paid": round(float(paid / invoiced * 100), 1) if invoiced else None}


def account_ledger(db: Session, a: FinanceAccount) -> dict:
    rows = list_transactions(db, account_id=a.id)
    balance, running = D0, []
    sums: dict[str, Decimal] = defaultdict(lambda: D0)
    for t in rows:
        if not t.voided:
            balance += t.amount if t.direction == "in" else -t.amount
            sums[t.kind.value] += t.amount
        running.append(float(balance))
    totals = {"balance": float(balance), "in": float(sum((t.amount for t in rows if not t.voided and t.direction == "in"), D0)),
              "out": float(sum((t.amount for t in rows if not t.voided and t.direction == "out"), D0)),
              "by_kind": {k: float(v) for k, v in sums.items()}}
    if a.kind == "partner":
        took, spent, withdrawn = sums[TxKind.partner_took.value], sums[TxKind.partner_spent.value], sums[TxKind.partner_withdrawal.value]
        totals |= {"took_from_company": float(took), "spent_on_company": float(spent),
                   "withdrawn": float(withdrawn), "loans": float(sums[TxKind.loan.value]),
                   # What the partner still holds of company money (+) or is owed by the company (−).
                   "still_with_partner": float(took - spent)}
    return {"account": a, "transactions": rows, "running_balance": running, "totals": totals}


def months(db: Session) -> dict:
    def ms(col, model):
        q = select(func.distinct(func.to_char(func.date_trunc("month", col), "YYYY-MM"))).where(col.is_not(None))
        if model is Project:
            q = q.where(Project.merged_into_id.is_(None))
        return sorted(m for m in db.scalars(q) if m)
    this = date.today().strftime("%Y-%m")
    wells = ms(Project.order_date, Project)
    sac = ms(Sacrifice.order_date, Sacrifice)
    return {"wells": sorted(set(wells) | {this}), "sacrifices": sorted(set(sac) | {this}), "current": this}


def summary(db: Session, *, include_samples: bool = True) -> dict:
    pq, sq = _live_projects(), select(Sacrifice)
    tq = select(Transaction).where(Transaction.voided.is_(False))
    if not include_samples:
        pq, sq, tq = pq.where(Project.is_sample.is_(False)), sq.where(Sacrifice.is_sample.is_(False)), tq.where(Transaction.is_sample.is_(False))
    projects, sacrifices, txs = list(db.scalars(pq)), list(db.scalars(sq)), list(db.scalars(tq))

    monthly: dict[str, dict] = defaultdict(lambda: {"well_sales": D0, "well_cost": D0, "wells": 0, "sac_sales": D0,
                                                    "sac_cost": D0, "sacrifices": 0, "ads": D0, "opex": D0})
    for p in projects:
        if p.order_date:
            m = monthly[p.order_date.strftime("%Y-%m")]
            m["well_sales"] += _d(p.sale_amount); m["well_cost"] += _d(p.cost); m["wells"] += 1
    for s in sacrifices:
        if s.order_date:
            m = monthly[s.order_date.strftime("%Y-%m")]
            m["sac_sales"] += _d(s.sale_price); m["sac_cost"] += _d(s.cost); m["sacrifices"] += 1
    ads_channel: dict[str, Decimal] = defaultdict(lambda: D0)
    opex_cat: dict[str, Decimal] = defaultdict(lambda: D0)
    for t in txs:
        key = t.date.strftime("%Y-%m")
        amt = t.amount if t.direction == "out" else -t.amount  # a refund ("in") reduces the spend
        if t.kind == TxKind.ad_spend:
            monthly[key]["ads"] += amt; ads_channel[t.channel or "—"] += amt
        elif t.kind == TxKind.operating_expense:
            monthly[key]["opex"] += amt; opex_cat[t.category or "—"] += amt

    by_month = []
    for k in sorted(monthly):
        m = monthly[k]
        sales, cost = m["well_sales"] + m["sac_sales"], m["well_cost"] + m["sac_cost"]
        gross = sales - cost
        by_month.append({"month": k, "wells": m["wells"], "sacrifices": m["sacrifices"],
                         "well_sales": float(m["well_sales"]), "well_cost": float(m["well_cost"]),
                         "well_profit": float(m["well_sales"] - m["well_cost"]),
                         "sac_sales": float(m["sac_sales"]), "sac_cost": float(m["sac_cost"]),
                         "sac_profit": float(m["sac_sales"] - m["sac_cost"]),
                         "sales": float(sales), "cost": float(cost), "gross_profit": float(gross),
                         "ads": float(m["ads"]), "opex": float(m["opex"]),
                         "pure_profit": float(gross - m["ads"] - m["opex"])})

    total_sales = sum((r["sales"] for r in by_month), 0.0)
    total_cost = sum((r["cost"] for r in by_month), 0.0)
    gross = total_sales - total_cost
    ads_total = float(sum(ads_channel.values(), D0))
    opex_total = float(sum(opex_cat.values(), D0))

    # contractors
    invoiced: dict[int, Decimal] = defaultdict(lambda: D0)
    paid: dict[int, Decimal] = defaultdict(lambda: D0)
    for p in projects:
        if p.contractor_id:
            invoiced[p.contractor_id] += _d(p.cost)
    for s in sacrifices:
        if s.contractor_id:
            invoiced[s.contractor_id] += _d(s.cost)
    for t in txs:
        if t.kind == TxKind.contractor_payment and t.contractor_id:
            paid[t.contractor_id] += t.amount
        elif t.kind == TxKind.operating_expense and t.contractor_id and t.category == EXTRA_WORK:
            invoiced[t.contractor_id] += t.amount
    contractors = []
    for c in db.scalars(select(Contractor).order_by(Contractor.country, Contractor.code)):
        if c.id in invoiced or c.id in paid or c.is_active:
            contractors.append({"id": c.id, "code": c.code, "name": c.name, "country": c.country or "—"}
                               | _owed(invoiced[c.id], paid[c.id]))
    owed_total = sum(max(0.0, r["owed"]) for r in contractors)

    accounts = []
    for a in db.scalars(select(FinanceAccount).where(FinanceAccount.is_active.is_(True)).order_by(FinanceAccount.sort_order)):
        led = account_ledger(db, a)["totals"]
        if not include_samples:  # recompute without sample rows
            rows = [t for t in txs if t.account_id == a.id]
            led = led | {"balance": float(sum((t.amount if t.direction == "in" else -t.amount for t in rows), D0))}
        accounts.append({"id": a.id, "code": a.code, "name": a.name, "kind": a.kind, "currency": a.currency} | led)
    cash = sum(r["balance"] for r in accounts if r["kind"] == "bank")

    # same-day comparison: this month to date vs last month up to the same day
    today = date.today()
    this_start = today.replace(day=1)
    last_start = (this_start - timedelta(days=1)).replace(day=1)
    last_same = last_start.replace(day=min(today.day, calendar.monthrange(last_start.year, last_start.month)[1]))

    def window(a, b):
        w = [p for p in projects if p.order_date and a <= p.order_date <= b]
        s = [x for x in sacrifices if x.order_date and a <= x.order_date <= b]
        sales = sum((_d(p.sale_amount) for p in w), D0) + sum((_d(x.sale_price) for x in s), D0)
        cost = sum((_d(p.cost) for p in w), D0) + sum((_d(x.cost) for x in s), D0)
        return {"from": a, "to": b, "wells": len(w), "sacrifices": len(s), "sales": float(sales),
                "profit": float(sales - cost)}

    loans = [{"partner": a["name"], "amount": a.get("loans", 0.0)} for a in accounts if a["kind"] == "partner"]
    return {
        "headline": {"total_sales": total_sales, "cost": total_cost, "gross_profit": gross,
                     "margin_pct": round(gross / total_sales * 100, 1) if total_sales else None,
                     "ad_spend": ads_total, "operating_expenses": opex_total,
                     "pure_profit": gross - ads_total - opex_total, "cash_on_hand": cash,
                     "owed_to_contractors": owed_total, "wells": len(projects), "sacrifices": len(sacrifices)},
        "by_month": by_month, "contractors": contractors,
        "ads_by_channel": [{"channel": k, "amount": float(v)} for k, v in sorted(ads_channel.items(), key=lambda x: -x[1])],
        "opex_by_category": [{"category": k, "amount": float(v)} for k, v in sorted(opex_cat.items(), key=lambda x: -x[1])],
        "accounts": accounts, "loans": loans,
        "same_day": {"this_month": window(this_start, today), "last_month": window(last_start, last_same)},
        "includes_samples": include_samples,
        "has_samples": any(p.is_sample for p in projects) or any(s.is_sample for s in sacrifices) or any(t.is_sample for t in txs),
    }

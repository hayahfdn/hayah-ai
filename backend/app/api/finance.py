"""Finance workbook API: sacrifices, accounts, transactions, ledgers, summary.
Money pages are for managers only (super admin, operations manager)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import MANAGERS, client_ip, require_roles
from app.models import Contractor, FinanceAccount, Sacrifice, Transaction, User
from app.schemas import (
    AccountIn, AccountOut, ContractorOut, DirectDeliveryIn, ProjectOut, SacrificeCreate, SacrificeOut,
    SacrificeUpdate, TransactionCreate, TransactionOut, TransactionUpdate, TransactionVoid,
)
from app.services import delivery as dsvc, finance as fin, projects as psvc
from app.services.audit import audit

router = APIRouter(prefix="/api/finance", tags=["finance"])
sacrifices = APIRouter(prefix="/api/sacrifices", tags=["sacrifices"])
MGR = Depends(require_roles(MANAGERS))


# ---------- workbook tabs ----------
@router.get("/workbook")
def workbook(db: Session = Depends(get_db), _: User = MGR):
    """Everything the bottom tab strip needs, in Excel order."""
    accounts = list(db.scalars(select(FinanceAccount).where(FinanceAccount.is_active.is_(True)).order_by(FinanceAccount.sort_order, FinanceAccount.id)))
    contractors = list(db.scalars(select(Contractor).where(Contractor.is_active.is_(True)).order_by(Contractor.country, Contractor.code)))
    return {"accounts": [AccountOut.model_validate(a) for a in accounts],
            "contractors": [ContractorOut.model_validate(c) for c in contractors],
            "months": fin.months(db)}


@router.get("/summary")
def summary(include_samples: bool = True, db: Session = Depends(get_db), _: User = MGR):
    return fin.summary(db, include_samples=include_samples)


# ---------- accounts ----------
@router.get("/accounts", response_model=list[AccountOut])
def accounts(db: Session = Depends(get_db), _: User = MGR):
    return list(db.scalars(select(FinanceAccount).order_by(FinanceAccount.sort_order, FinanceAccount.id)))


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, db: Session = Depends(get_db), user: User = MGR):
    code = body.code.upper()
    if db.scalar(select(FinanceAccount).where(func.upper(FinanceAccount.code) == code)):
        raise HTTPException(409, "An account with this code already exists")
    n = db.scalar(select(func.count(FinanceAccount.id))) or 0
    a = FinanceAccount(**body.model_dump() | {"code": code}, sort_order=n)
    db.add(a)
    db.flush()
    audit(db, "account.create", "finance_account", a.code, actor=user, after=body.model_dump())
    db.commit()
    return a


@router.get("/accounts/{code}/ledger")
def account_ledger(code: str, db: Session = Depends(get_db), _: User = MGR):
    a = db.scalar(select(FinanceAccount).where(func.upper(FinanceAccount.code) == code.upper()))
    if not a:
        raise HTTPException(404, "No such account")
    led = fin.account_ledger(db, a)
    return {"account": AccountOut.model_validate(a),
            "transactions": [TransactionOut.model_validate(t).model_dump() | {"balance": b}
                             for t, b in zip(led["transactions"], led["running_balance"])],
            "totals": led["totals"]}


@router.get("/contractors/{code}/ledger")
def contractor_ledger(code: str, db: Session = Depends(get_db), _: User = MGR):
    c = db.scalar(select(Contractor).where(func.upper(Contractor.code) == code.upper()))
    if not c:
        raise HTTPException(404, "No such contractor")
    led = fin.contractor_ledger(db, c)
    return {"contractor": ContractorOut.model_validate(c),
            "wells": [ProjectOut.model_validate(p) for p in led["wells"]],
            "sacrifices": [SacrificeOut.model_validate(s) for s in led["sacrifices"]],
            "payments": [TransactionOut.model_validate(t) for t in led["payments"]],
            "totals": led["totals"]}


# ---------- transactions ----------
@router.get("/transactions", response_model=list[TransactionOut])
def transactions(account_id: int | None = None, contractor_id: int | None = None, kind: str | None = None,
                 month: str | None = None, db: Session = Depends(get_db), _: User = MGR):
    return fin.list_transactions(db, account_id=account_id, contractor_id=contractor_id, kind=kind, month=month)


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_tx(body: TransactionCreate, db: Session = Depends(get_db), user: User = MGR):
    t = fin.create_transaction(db, body.model_dump(), actor=user)
    db.commit()
    db.refresh(t)
    return t


@router.patch("/transactions/{tid}", response_model=TransactionOut)
def update_tx(tid: int, body: TransactionUpdate, db: Session = Depends(get_db), user: User = MGR):
    t = db.get(Transaction, tid)
    if not t:
        raise HTTPException(404, "No such transaction")
    changes = body.model_dump(exclude_unset=True)
    ev = changes.pop("expected_version", None)
    if "amount" in changes and changes["amount"] is None or "date" in changes and changes["date"] is None \
            or "kind" in changes and changes["kind"] is None:
        raise HTTPException(422, "Date, type and amount cannot be empty")
    fin.update_transaction(db, t, changes, actor=user, expected_version=ev)
    db.commit()
    db.refresh(t)
    return t


@router.post("/transactions/{tid}/void", response_model=TransactionOut)
def void_tx(tid: int, body: TransactionVoid, db: Session = Depends(get_db), user: User = MGR):
    t = db.get(Transaction, tid)
    if not t:
        raise HTTPException(404, "No such transaction")
    fin.void_transaction(db, t, body.reason, actor=user)
    db.commit()
    return t


# ---------- direct delivery (manager-confirmed) ----------
@router.post("/deliver/{well_id}", response_model=ProjectOut)
def deliver(well_id: int, body: DirectDeliveryIn, request: Request, db: Session = Depends(get_db), user: User = MGR):
    """A manager typing a delivery date in the sheet is an explicit, authorized
    confirmation: it is recorded as a delivery confirmation and approved by
    that manager in one step, with the full audit trail."""
    p = psvc.require_project(db, well_id, for_update=True)
    if p.delivery_status.value == "delivered" and p.delivery_date == body.delivery_date:
        return p
    dc = dsvc.create_pending(db, p, delivery_date=body.delivery_date, source="dashboard", requested_by=user,
                             notes=body.note or "Entered by a manager in the sheet")
    dsvc.decide(db, dc, approve=True, actor=user, note=body.note or "Confirmed by manager in the sheet", ip=client_ip(request))
    db.commit()
    db.refresh(p)
    return p


# ---------- sacrifices ----------
@sacrifices.get("", response_model=list[SacrificeOut])
def list_sac(month: str | None = None, contractor_id: int | None = None, db: Session = Depends(get_db), _: User = MGR):
    return fin.list_sacrifices(db, month=month, contractor_id=contractor_id)


@sacrifices.get("/next-number")
def next_no(db: Session = Depends(get_db), _: User = MGR):
    hi = db.scalar(select(func.max(Sacrifice.sacrifice_no)).where(Sacrifice.is_sample.is_(False)))
    return {"highest_existing": hi, "suggested_next": (hi or 0) + 1}


@sacrifices.post("", response_model=SacrificeOut, status_code=201)
def create_sac(body: SacrificeCreate, db: Session = Depends(get_db), user: User = MGR):
    data = body.model_dump(exclude_none=True)
    s = fin.create_sacrifice(db, data, actor=user)
    db.commit()
    return s


@sacrifices.patch("/{no}", response_model=SacrificeOut)
def update_sac(no: int, body: SacrificeUpdate, db: Session = Depends(get_db), user: User = MGR):
    s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no))
    if not s:
        raise HTTPException(404, f"No sacrifice number {no}")
    changes = body.model_dump(exclude_unset=True)
    ev = changes.pop("expected_version", None)
    if changes.get("currency", "x") is None:
        changes.pop("currency")
    fin.update_sacrifice(db, s, changes, actor=user, expected_version=ev)
    db.commit()
    db.refresh(s)
    return s

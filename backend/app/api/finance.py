"""Finance workbook API: sacrifices, accounts, transactions, ledgers, summary.
Money pages are for managers only (super admin, operations manager)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import FINANCE_VIEWERS, MANAGERS, PROJECT_CREATORS, client_ip, require_roles
from app.models import Contractor, FinanceAccount, Sacrifice, Transaction, User
from app.schemas import (
    AccountIn, AccountOut, ContractorOut, DirectDeliveryIn, ProjectOut, NumberChange, RenumberPlan, SacrificeBulkCreate, SacrificeCreate, SacrificeOut,
    SacrificeUpdate, TransactionCreate, TransactionOut, TransactionUpdate, TransactionVoid,
)
from app.services import delivery as dsvc, finance as fin, projects as psvc, renumber as rn
from app.services.audit import audit

router = APIRouter(prefix="/api/finance", tags=["finance"])
sacrifices = APIRouter(prefix="/api/sacrifices", tags=["sacrifices"])
MGR = Depends(require_roles(MANAGERS))
# Employees (موظف) work with sacrifices too: every operational detail and the selling price.
# Cost and profit stay with managers: stripped from every answer, refused on every write.
SAC = Depends(require_roles(PROJECT_CREATORS))
STAFF_LOCKED_SAC = {"cost", "delivery_date"}  # a delivery date means delivered: a manager confirms it


def _sac(s: Sacrifice, user: User) -> SacrificeOut:
    o = SacrificeOut.model_validate(s)
    return o if user.role in FINANCE_VIEWERS else o.model_copy(update={"cost": None})


def _guard_sac_write(data: dict, user: User) -> None:
    if user.role in FINANCE_VIEWERS:
        return
    if bad := sorted(STAFF_LOCKED_SAC & set(data)):
        raise HTTPException(403, f"Only managers can change: {', '.join(bad)}")


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
def list_sac(month: str | None = None, contractor_id: int | None = None, db: Session = Depends(get_db), user: User = SAC):
    return [_sac(s, user) for s in fin.list_sacrifices(db, month=month, contractor_id=contractor_id)]


@sacrifices.get("/next-number")
def next_no(db: Session = Depends(get_db), _: User = SAC):
    hi = db.scalar(select(func.max(Sacrifice.sacrifice_no)).where(Sacrifice.is_sample.is_(False)))
    return {"highest_existing": hi, "suggested_next": (hi or 0) + 1}


@sacrifices.post("/bulk", response_model=list[SacrificeOut], status_code=201)
def create_many(body: SacrificeBulkCreate, db: Session = Depends(get_db), user: User = SAC):
    """One order with several sacrifices: each one gets its own next number, all linked to the order."""
    data = body.model_dump(exclude_none=True)
    _guard_sac_write(data, user)
    qty = data.pop("quantity", 1)
    if data.get("shopify_order"):
        data["shopify_order"] = rn.order_label(rn.order_key(data["shopify_order"])) or data["shopify_order"]
    out = [fin.create_sacrifice(db, dict(data), actor=user) for _ in range(qty)]
    db.commit()
    return [_sac(s, user) for s in out]


@sacrifices.get("/orders/{order}")
def order_detail(order: str, db: Session = Depends(get_db), _: User = SAC):
    """The original order and every sacrifice (and well) that belongs to it."""
    return rn.order_view(db, order)


@sacrifices.post("/renumber/preview")
def renumber_preview(body: RenumberPlan, db: Session = Depends(get_db), _: User = MGR):
    p = rn.plan(db, body.renames, body.orders)
    p.pop("_moves", None)
    return p


@sacrifices.post("/renumber/apply")
def renumber_apply(body: RenumberPlan, request: Request, db: Session = Depends(get_db), user: User = MGR):
    out = rn.apply_plan(db, body.renames, body.orders, body.token or "", actor=user, ip=client_ip(request))
    db.commit()
    return out


@sacrifices.get("/renumber/history")
def renumber_history(db: Session = Depends(get_db), _: User = MGR):
    return rn.batches(db)


@sacrifices.post("/renumber/undo/{batch_id}")
def renumber_undo(batch_id: int, request: Request, db: Session = Depends(get_db), user: User = MGR):
    out = rn.undo_batch(db, batch_id, actor=user, ip=client_ip(request))
    db.commit()
    return out


@sacrifices.get("/backup.csv")
def sacrifices_backup(db: Session = Depends(get_db), _: User = MGR):
    """Every sacrifice's number and order right now, as a CSV file to keep before a change."""
    return Response(rn.snapshot_csv(rn.snapshot(db)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="sacrifices-backup-{date.today()}.csv"'})


@sacrifices.get("/renumber/{batch_id}/backup.csv")
def renumber_backup(batch_id: int, db: Session = Depends(get_db), _: User = MGR):
    """The copy kept automatically just before that renumbering was applied."""
    return Response(rn.snapshot_csv(rn.batch_backup(db, batch_id)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="sacrifices-before-renumber-{batch_id}.csv"'})


@sacrifices.post("/renumber/verify")
def renumber_verify(body: RenumberPlan, db: Session = Depends(get_db), _: User = MGR):
    """Checks the live data against the order table: each order's sacrifice numbers, and no number used twice."""
    return rn.verify(db, body.orders)


@sacrifices.patch("/{no}/number")
def change_number(no: int, body: NumberChange, request: Request, db: Session = Depends(get_db), user: User = MGR):
    s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no).with_for_update())
    if not s:
        raise HTTPException(404, f"No sacrifice number {no}")
    out = rn.renumber_sacrifice(db, s, body.new_number, actor=user, ip=client_ip(request))
    db.commit()
    db.refresh(s)
    return {**out, "sacrifice": SacrificeOut.model_validate(s).model_dump(mode="json")}


@sacrifices.post("", response_model=SacrificeOut, status_code=201)
def create_sac(body: SacrificeCreate, db: Session = Depends(get_db), user: User = SAC):
    data = body.model_dump(exclude_none=True)
    _guard_sac_write(data, user)
    s = fin.create_sacrifice(db, data, actor=user)
    db.commit()
    return _sac(s, user)


@sacrifices.patch("/{no}", response_model=SacrificeOut)
def update_sac(no: int, body: SacrificeUpdate, db: Session = Depends(get_db), user: User = SAC):
    s = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == no))
    if not s:
        raise HTTPException(404, f"No sacrifice number {no}")
    changes = body.model_dump(exclude_unset=True)
    ev = changes.pop("expected_version", None)
    _guard_sac_write(changes, user)
    if changes.get("currency", "x") is None:
        changes.pop("currency")
    fin.update_sacrifice(db, s, changes, actor=user, expected_version=ev)
    db.commit()
    db.refresh(s)
    return _sac(s, user)

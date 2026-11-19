"""Sacrifice plaques (well plaques live under /api/projects/{well_id}/plaques)."""
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import PROJECT_CREATORS, require_roles
from app.models import User
from app.services import plaques as svc

router = APIRouter(prefix="/api/plaques", tags=["plaques"])
EDITORS = Depends(require_roles(PROJECT_CREATORS))


@router.get("/sacrifices/{no}")
def sacrifice_data(no: int, db: Session = Depends(get_db), _: User = EDITORS):
    return {"sacrifice": svc.sacrifice_plaque_data(db, no), "saved": svc.list_sacrifice_plaques(db, no)}


@router.post("/sacrifices/{no}", status_code=201)
def save_sacrifice(no: int, file: UploadFile = File(...), design: str = Form(...), approve: bool = Form(False),
                   db: Session = Depends(get_db), user: User = EDITORS):
    parsed = svc.parse_design(design)
    with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as tmp:
        shutil.copyfileobj(file.file, tmp)
        row = svc.save_sacrifice_plaque(db, no, tmp, mime_type=file.content_type, design=parsed, actor=user, approve=approve)
    db.commit()
    return row


# ---------------- plaque workflow (wells and sacrifices) ----------------
from datetime import date  # noqa: E402

from fastapi import HTTPException, Query, Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models import Plaque, PlaqueStatus, PlaqueVersion, Project, Sacrifice  # noqa: E402
from app.services import plaque_flow as flow  # noqa: E402

GROUPS = {
    "confirm": flow.OPEN,
    "approved": [PlaqueStatus.approved_for_contractor],
    "sent": [PlaqueStatus.sent_to_contractor],
}


def _plaque(db: Session, pid: int, lock: bool = False) -> Plaque:
    q = select(Plaque).where(Plaque.id == pid)
    pl = db.scalar(q.with_for_update() if lock else q)
    if not pl:
        raise HTTPException(404, "No such plaque")
    return pl


@router.get("")
def list_all(group: str = Query("confirm", pattern="^(confirm|approved|sent)$"), kind: str | None = None,
             q: str | None = None, db: Session = Depends(get_db), _: User = EDITORS):
    return flow.list_plaques(db, GROUPS[group], kind=kind, q=q)


@router.get("/counts")
def counts(db: Session = Depends(get_db), _: User = EDITORS):
    return flow.counts(db)


@router.get("/order/{kind}/{number}")
def for_order(kind: str, number: int, db: Session = Depends(get_db), _: User = EDITORS):
    """The plaque of one order (None if it has none yet)."""
    rec = _order(db, kind, number)
    pl = flow.get_plaque(db, rec)
    return flow.row(db, pl, rec, versions=True) if pl else None


@router.post("/order/{kind}/{number}", status_code=201)
def create_for_order(kind: str, number: int, db: Session = Depends(get_db), user: User = EDITORS):
    """Start the plaque of an existing order by hand (older orders have no automatic draft)."""
    rec = _order(db, kind, number)
    pl = flow.create_draft(db, rec, actor=user, source="dashboard")
    db.commit()
    return flow.row(db, pl, rec, versions=True)


def _order(db: Session, kind: str, number: int):
    if kind == "well":
        rec = db.scalar(select(Project).where(Project.well_id == number))
    elif kind == "sacrifice":
        rec = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == number))
    else:
        raise HTTPException(404, "Unknown order type")
    if not rec:
        raise HTTPException(404, f"No {kind} number {number}")
    return rec


@router.get("/{pid}")
def one(pid: int, db: Session = Depends(get_db), _: User = EDITORS):
    return flow.row(db, _plaque(db, pid), versions=True)


class StatusIn(BaseModel):
    to: PlaqueStatus
    note: str | None = Field(default=None, max_length=1000)


@router.post("/{pid}/status")
def change_status(pid: int, body: StatusIn, db: Session = Depends(get_db), user: User = EDITORS):
    pl = _plaque(db, pid, lock=True)
    flow.set_status(db, pl, body.to, user, body.note)
    db.commit()
    return flow.row(db, pl)


class SendIn(BaseModel):
    contractor_id: int
    country: str | None = Field(default=None, max_length=80)
    sent_on: date | None = None
    note: str | None = Field(default=None, max_length=1000)


@router.post("/{pid}/send-to-contractor")
def send(pid: int, body: SendIn, db: Session = Depends(get_db), user: User = EDITORS):
    pl = _plaque(db, pid, lock=True)
    flow.send_to_contractor(db, pl, contractor_id=body.contractor_id, country=body.country, on=body.sent_on,
                            actor=user, note=body.note)
    db.commit()
    return flow.row(db, pl)


@router.get("/{pid}/file")
def file(pid: int, version_id: int | None = None, download: bool = False, db: Session = Depends(get_db), _: User = EDITORS):
    pl = _plaque(db, pid)
    vid = version_id or pl.approved_version_id or pl.current_version_id
    v = db.get(PlaqueVersion, vid) if vid else None
    if not v or v.plaque_id != pl.id:
        raise HTTPException(404, "No such plaque version")
    data, mime, name = flow.version_file(db, v)
    rec = flow.record_of(db, pl)
    nice = f"{'plaque' if pl.kind == 'well' else 'sacrifice-plaque'}-{flow.number(rec)}-v{v.version}.png"
    return Response(content=data, media_type=mime, headers={
        "Content-Disposition": f'{"attachment" if download else "inline"}; filename="{nice}"',
        "Cache-Control": "private, max-age=3600"})


class ZipIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/zip")
def zip_many(body: ZipIn, db: Session = Depends(get_db), _: User = EDITORS):
    data = flow.zip_files(db, body.ids)
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="plaques-{date.today().isoformat()}.zip"'})



# ---------------------------------------------------------------- to the customer on WhatsApp
from app.services import plaque_whatsapp as pwa  # noqa: E402


@router.post("/{pid}/whatsapp-opened")
def whatsapp_opened(pid: int, db: Session = Depends(get_db), user: User = EDITORS):
    """The employee tapped the WhatsApp icon (WhatsApp opens on their device): log it."""
    pl = _plaque(db, pid, lock=True)
    out = pwa.opened(db, pl, user)
    db.commit()
    return out

"""Upload Hayah's Excel workbook and load it: preview first (nothing saved), then apply.

Also: replace everything earlier imports loaded with a new workbook (app/services/workbook_replace.py),
and the backups the app writes before doing that."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ADMINS, require_roles
from app.models import User
from app.services.audit import audit

router = APIRouter(prefix="/api/admin/import-workbook", tags=["import"])
backups = APIRouter(prefix="/api/admin/backups", tags=["import"])
MAX_BYTES = 20 * 1024 * 1024
ORDER = {"action": 0, "check": 1, "info": 2}


async def _read(file: UploadFile | None, url: str | None) -> tuple[dict, str]:
    """Give either an uploaded .xlsx file or a share link to one."""
    from fastapi.concurrency import run_in_threadpool
    from app.services.link_fetch import fetch_workbook
    from app.services.workbook_xlsx import read_workbook

    if url and url.strip():
        raw, name = await run_in_threadpool(fetch_workbook, url)
        source_name = f"{name} (link)"[:80]
    elif file is not None:
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise HTTPException(422, "Please upload the workbook as an .xlsx file")
        raw = await file.read()
        source_name = (file.filename or "upload.xlsx")[:80]
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "The file is larger than 20 MB")
    else:
        raise HTTPException(422, "Choose a file or paste a link")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "book.xlsx"
        path.write_bytes(raw)
        try:
            return read_workbook(path), source_name
        except Exception as e:  # a damaged or different file
            raise HTTPException(422, f"Could not read this workbook: {e}")


@router.post("")
async def import_workbook(file: UploadFile | None = File(None), url: str | None = Form(None), apply: bool = Form(False),
                          db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    from app.services.workbook_import import import_full_workbook

    data, source_name = await _read(file, url)
    report = import_full_workbook(db, data, actor=user)
    if apply:
        audit(db, "workbook.import", "workbook", source_name, actor=user,
              after={k: v for k, v in report.items() if k != "problems"})
        db.commit()
    else:
        db.rollback()  # preview: show what would happen, save nothing
    return {"applied": apply, "file": source_name, **report,
            "problems": sorted(data["problems"], key=lambda p: ORDER.get(p["kind"], 3))}


@router.post("/replace")
async def replace_workbook(file: UploadFile | None = File(None), url: str | None = Form(None), apply: bool = Form(False),
                           confirm: str = Form(""), db: Session = Depends(get_db),
                           user: User = Depends(require_roles(ADMINS))):
    """Replace what earlier imports loaded with this workbook. Preview first; apply needs the word typed
    (REPLACE or استبدال) and writes a database backup before anything changes."""
    from fastapi.concurrency import run_in_threadpool
    from app.services import backup as bk, workbook_replace as wr

    if apply and confirm.strip().upper() not in wr.CONFIRM_WORDS and confirm.strip() not in wr.CONFIRM_WORDS:
        raise HTTPException(422, "Type REPLACE (or استبدال) to confirm")
    data, source_name = await _read(file, url)
    backup = None
    if apply:
        backup = await run_in_threadpool(bk.make_backup, "before-replace")
    report = wr.replace_all(db, data, actor=user, file=source_name)
    if apply:
        wr.finish(db, report, actor=user, backup=backup)
        db.commit()
    else:
        db.rollback()  # preview: show what would happen, save nothing
    report.pop("created", None)
    return {"applied": apply, "backup": backup, **report,
            "problems": sorted(data["problems"], key=lambda p: ORDER.get(p["kind"], 3))}


@backups.get("")
def list_backups(_: User = Depends(require_roles(ADMINS))):
    from app.services.backup import list_backups as lb
    return lb()


@backups.get("/{name}")
def download_backup(name: str, _: User = Depends(require_roles(ADMINS))):
    from app.services.backup import backup_path
    p = backup_path(name)
    return FileResponse(p, filename=p.name, media_type="application/octet-stream")

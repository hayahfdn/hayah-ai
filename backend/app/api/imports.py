"""Upload Hayah's Excel workbook and load it: preview first (nothing saved), then apply."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ADMINS, require_roles
from app.models import User
from app.services.audit import audit

router = APIRouter(prefix="/api/admin/import-workbook", tags=["import"])
MAX_BYTES = 20 * 1024 * 1024


@router.post("")
async def import_workbook(file: UploadFile | None = File(None), url: str | None = Form(None), apply: bool = Form(False),
                          db: Session = Depends(get_db), user: User = Depends(require_roles(ADMINS))):
    """Give either an uploaded .xlsx file or a share link to one."""
    from fastapi.concurrency import run_in_threadpool
    from app.services.link_fetch import fetch_workbook
    from app.services.workbook_import import import_full_workbook
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
            data = read_workbook(path)
        except Exception as e:  # a damaged or different file
            raise HTTPException(422, f"Could not read this workbook: {e}")
    report = import_full_workbook(db, data, actor=user)
    if apply:
        audit(db, "workbook.import", "workbook", source_name, actor=user,
              after={k: v for k, v in report.items() if k != "problems"})
        db.commit()
    else:
        db.rollback()  # preview: show what would happen, save nothing
    order = {"action": 0, "check": 1, "info": 2}
    return {"applied": apply, "file": source_name, **report,
            "problems": sorted(data["problems"], key=lambda p: order.get(p["kind"], 3))}

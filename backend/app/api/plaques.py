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
def save_sacrifice(no: int, file: UploadFile = File(...), design: str = Form(...), db: Session = Depends(get_db),
                   user: User = EDITORS):
    parsed = svc.parse_design(design)
    with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as tmp:
        shutil.copyfileobj(file.file, tmp)
        row = svc.save_sacrifice_plaque(db, no, tmp, mime_type=file.content_type, design=parsed, actor=user)
    db.commit()
    return row

"""A database backup written by the app itself, right before a big change (Hayah, 23 Nov 2026).

Two files are written into the backup folder (Settings: HAYAH_BACKUP_DIR, default <data>/backups):
  * <name>.dump      : a full PostgreSQL backup (pg_dump -Fc), when pg_dump is installed in the image.
                       Restore on the server with:  pg_restore --clean --if-exists -d hayah <name>.dump
  * <name>.json.gz   : every table as JSON, always written (needs no extra program), so a backup
                       exists even where pg_dump is missing or does not match the server version.
If neither can be written the change is refused.

The nightly server backup (deploy/backup.sh) keeps running as before; this one is extra.
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.services.audit import jsonable

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def backup_dir() -> Path:
    s = get_settings()
    d = Path(s.backup_dir or Path(s.mock_data_dir) / "backups")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _libpq_url(url: str) -> str:
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _pg_dump(path: Path) -> str | None:
    exe = shutil.which("pg_dump")
    if not exe:
        return "pg_dump is not installed"
    tmp = path.with_suffix(".tmp")
    try:
        r = subprocess.run([exe, "-Fc", "-f", str(tmp), "-d", _libpq_url(get_settings().database_url)],
                           capture_output=True, text=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return str(e)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        return (r.stderr or "pg_dump failed").strip()[:300]
    tmp.rename(path)
    return None


def _json_dump(path: Path) -> dict:
    counts = {}
    with get_engine().connect() as c:
        tables = c.execute(text("select tablename from pg_tables where schemaname='public' order by tablename")).scalars().all()
        out = {"written_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
        for t in tables:
            rows = [jsonable(dict(r._mapping)) for r in c.execute(text(f'select * from "{t}"'))]
            out["tables"][t] = rows
            counts[t] = len(rows)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, default=str)
    tmp.rename(path)
    return counts


def make_backup(reason: str) -> dict:
    """Write the backup now (outside the request's transaction, so it holds the data as it is before the change)."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = f"hayah-{stamp}-{re.sub(r'[^a-z0-9]+', '-', reason.lower()).strip('-')[:30]}"
    d = backup_dir()
    files, notes = [], []
    err = _pg_dump(d / f"{base}.dump")
    if err is None:
        files.append(f"{base}.dump")
    else:
        notes.append(f"pg_dump: {err}")
    try:
        counts = _json_dump(d / f"{base}.json.gz")
        files.append(f"{base}.json.gz")
    except Exception as e:  # noqa: BLE001
        counts = {}
        notes.append(f"json: {e}"[:300])
    if not files:
        raise HTTPException(500, "Could not write a backup, so nothing was changed. " + " · ".join(notes))
    return {"files": files, "folder": str(d), "rows": sum(counts.values()), "notes": notes}


def list_backups() -> list[dict]:
    d = backup_dir()
    return [{"name": p.name, "bytes": p.stat().st_size,
             "at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
            for p in sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if p.is_file() and (p.name.endswith(".dump") or p.name.endswith(".json.gz"))]


def backup_path(name: str) -> Path:
    if not SAFE_NAME.match(name):
        raise HTTPException(404, "No such backup")
    p = backup_dir() / name
    if not p.is_file():
        raise HTTPException(404, "No such backup")
    return p

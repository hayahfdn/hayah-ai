"""Offline Google Drive stand-in: mirrors the HAYAH PROJECTS folder tree on local disk."""
import json
import shutil
import threading
import uuid
from pathlib import Path

from app.integrations.drive.base import DriveError


class MockDriveClient:
    _lock = threading.Lock()

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "_index.json"
        self.fail_next = 0

    def _idx(self) -> dict:
        if self.index_path.exists():
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        return {"folders": {}, "files": {}}

    def _save(self, idx):
        self.index_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")

    def _maybe_fail(self):
        if self.fail_next > 0:
            self.fail_next -= 1
            raise DriveError("Simulated Google Drive outage")

    def _path_of(self, idx, folder_id):
        if folder_id is None:
            return self.root
        f = idx["folders"][folder_id]
        return self._path_of(idx, f["parent"]) / f["name"]

    def ensure_folder(self, name, parent_id):
        self._maybe_fail()
        with self._lock:
            idx = self._idx()
            for fid, f in idx["folders"].items():
                if f["name"] == name and f["parent"] == parent_id:
                    return fid
            fid = f"mockfolder-{uuid.uuid4().hex[:12]}"
            idx["folders"][fid] = {"name": name, "parent": parent_id}
            self._path_of(idx, fid).mkdir(parents=True, exist_ok=True)
            self._save(idx)
            return fid

    def find_by_sha256(self, sha256):
        idx = self._idx()
        for fid, f in idx["files"].items():
            if f["properties"].get("sha256") == sha256:
                return {"id": fid, "url": f"mock://drive/{fid}", "name": f["name"]}
        return None

    def upload(self, fh, name, mime_type, parent_id, properties):
        self._maybe_fail()
        with self._lock:
            idx = self._idx()
            folder = self._path_of(idx, parent_id)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / name
            if target.exists():
                raise DriveError(f"Refusing to overwrite existing file {name}")
            with open(target, "wb") as out:
                shutil.copyfileobj(fh, out)
            fid = f"mockfile-{uuid.uuid4().hex[:12]}"
            idx["files"][fid] = {"name": name, "parent": parent_id, "mime": mime_type, "properties": properties,
                                 "path": str(target.relative_to(self.root))}
            self._save(idx)
            return {"id": fid, "url": f"mock://drive/{fid}"}

    def download(self, file_id):
        f = self._idx()["files"].get(file_id)
        if not f:
            raise DriveError(f"No file {file_id}")
        return (self.root / f["path"]).read_bytes()

    def local_path(self, file_id):
        """The file on this server's disk, so large videos can be streamed (with seeking) instead of read into memory."""
        f = self._idx()["files"].get(file_id)
        return (self.root / f["path"]) if f else None

    def folder_url(self, folder_id):
        return f"mock://drive/folder/{folder_id}"

    def storage_quota(self):
        usage = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        return {"limit": 15 * 1024**3, "usage": usage}

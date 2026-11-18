"""Real Google Drive client (Drive API v3). Uses resumable uploads and stores
the SHA-256 in appProperties so duplicates are detected even across restarts."""
from app.integrations.drive.base import DriveError

FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveClient:
    def __init__(self):
        from googleapiclient.discovery import build
        from app.integrations.google_auth import load_credentials
        self.svc = build("drive", "v3", credentials=load_credentials(), cache_discovery=False)

    def _run(self, req):
        from googleapiclient.errors import HttpError
        try:
            return req.execute(num_retries=3)
        except HttpError as e:
            raise DriveError(f"Google Drive API error {e.resp.status}: {e}") from e
        except OSError as e:
            raise DriveError(f"Network error talking to Google Drive: {e}") from e

    @staticmethod
    def _q(s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'")

    def ensure_folder(self, name, parent_id):
        q = f"name = '{self._q(name)}' and mimeType = '{FOLDER_MIME}' and trashed = false"
        q += f" and '{parent_id}' in parents" if parent_id else " and 'root' in parents"
        res = self._run(self.svc.files().list(q=q, fields="files(id)", pageSize=1, supportsAllDrives=True,
                                              includeItemsFromAllDrives=True))
        if res.get("files"):
            return res["files"][0]["id"]
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id] if parent_id else []}
        return self._run(self.svc.files().create(body=body, fields="id", supportsAllDrives=True))["id"]

    def find_by_sha256(self, sha256):
        q = f"appProperties has {{ key='sha256' and value='{sha256}' }} and trashed = false"
        res = self._run(self.svc.files().list(q=q, fields="files(id,name,webViewLink)", pageSize=1,
                                              supportsAllDrives=True, includeItemsFromAllDrives=True))
        f = (res.get("files") or [None])[0]
        return {"id": f["id"], "url": f.get("webViewLink"), "name": f["name"]} if f else None

    def upload(self, fh, name, mime_type, parent_id, properties):
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True, chunksize=8 * 1024 * 1024)
        body = {"name": name, "parents": [parent_id], "appProperties": {k: str(v)[:100] for k, v in properties.items()}}
        f = self._run(self.svc.files().create(body=body, media_body=media, fields="id,webViewLink",
                                              supportsAllDrives=True))
        return {"id": f["id"], "url": f.get("webViewLink")}

    def folder_url(self, folder_id):
        return f"https://drive.google.com/drive/folders/{folder_id}"

    def storage_quota(self):
        q = self._run(self.svc.about().get(fields="storageQuota"))["storageQuota"]
        return {"limit": int(q["limit"]) if q.get("limit") else None, "usage": int(q.get("usage", 0))}

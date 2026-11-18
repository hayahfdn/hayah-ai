from typing import BinaryIO, Protocol


class DriveError(Exception):
    pass


class DriveClient(Protocol):
    """Deliberately has no delete method: originals are never deleted automatically."""
    def ensure_folder(self, name: str, parent_id: str | None) -> str: ...
    def find_by_sha256(self, sha256: str) -> dict | None: ...
    def upload(self, fh: BinaryIO, name: str, mime_type: str, parent_id: str, properties: dict) -> dict:
        """Returns {"id", "url"}."""
    def folder_url(self, folder_id: str) -> str: ...
    def download(self, file_id: str) -> bytes:
        """Read a stored file (used to show plaques inside the dashboard)."""
    def storage_quota(self) -> dict:
        """{"limit": bytes|None, "usage": bytes}"""

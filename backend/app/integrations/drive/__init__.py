from pathlib import Path

from app.config import get_settings

_client = None


def get_drive_client():
    global _client
    if _client is None:
        s = get_settings()
        if s.drive_backend == "google":
            from app.integrations.drive.google import GoogleDriveClient
            _client = GoogleDriveClient()
        else:
            from app.integrations.drive.mock import MockDriveClient
            _client = MockDriveClient(Path(s.mock_data_dir) / "mock_drive")
    return _client


def set_drive_client(client):
    global _client
    _client = client

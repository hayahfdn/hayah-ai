from pathlib import Path

from app.config import get_settings

_client = None


def get_sheets_client():
    global _client
    if _client is None:
        s = get_settings()
        if s.sheets_backend == "google":
            from app.integrations.sheets.google import GoogleSheetsClient
            _client = GoogleSheetsClient()
        else:
            from app.integrations.sheets.mock import MockSheetsClient
            _client = MockSheetsClient(Path(s.mock_data_dir) / "mock_sheets.json")
    return _client


def set_sheets_client(client):
    global _client
    _client = client

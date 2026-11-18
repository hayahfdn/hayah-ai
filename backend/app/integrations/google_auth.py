"""Google credentials loader. Supports an OAuth user token (recommended: the
HAYAH business Google account authorizes once with scripts/google_oauth.py) or
a service account JSON key. Files live in SECRETS_DIR, never in the repo."""
from pathlib import Path

from app.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file",
          "https://www.googleapis.com/auth/drive.metadata.readonly"]


def load_credentials():
    s = get_settings()
    secrets = Path(s.secrets_dir)
    if s.google_service_account_file:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_file(str(secrets / s.google_service_account_file),
                                                                     scopes=SCOPES)
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    token_path = secrets / s.google_credentials_file
    if not token_path.exists():
        raise RuntimeError(f"Google is not authorized yet: run scripts/google_oauth.py to create {token_path}")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds

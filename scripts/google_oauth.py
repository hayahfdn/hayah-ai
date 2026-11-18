"""One-time Google authorization for the HAYAH business account.

1. In Google Cloud Console (HAYAH's own project), enable the Google Sheets API
   and Google Drive API, then create an OAuth client of type "Desktop app".
2. Download its JSON to secrets/google-oauth-client.json
3. Run:  python scripts/google_oauth.py
   A browser opens; sign in with the HAYAH business Google account.
4. The token is saved to secrets/google-oauth-token.json (keep it private).
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file",
          "https://www.googleapis.com/auth/drive.metadata.readonly"]
SECRETS = Path(__file__).resolve().parents[1] / "secrets"

flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS / "google-oauth-client.json"), SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
(SECRETS / "google-oauth-token.json").write_text(creds.to_json())
print("Saved secrets/google-oauth-token.json")

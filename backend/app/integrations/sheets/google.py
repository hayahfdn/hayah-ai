"""Real Google Sheets client (Sheets API v4). Not exercised by the automated
tests (they use MockSheetsClient); verify with scripts/check_google.py once the
HAYAH Google account is authorized."""
from app.config import get_settings
from app.integrations.sheets.base import SheetsError


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class GoogleSheetsClient:
    def __init__(self, spreadsheet_id: str | None = None):
        from googleapiclient.discovery import build
        from app.integrations.google_auth import load_credentials
        self.svc = build("sheets", "v4", credentials=load_credentials(), cache_discovery=False).spreadsheets()
        self.spreadsheet_id = spreadsheet_id or get_settings().sheets_spreadsheet_id or None

    def _run(self, req):
        from googleapiclient.errors import HttpError
        try:
            return req.execute(num_retries=3)
        except HttpError as e:
            raise SheetsError(f"Google Sheets API error {e.resp.status}: {e}") from e
        except OSError as e:
            raise SheetsError(f"Network error talking to Google Sheets: {e}") from e

    def ensure_spreadsheet(self, title, tabs):
        if not self.spreadsheet_id:
            body = {"properties": {"title": title}, "sheets": [{"properties": {"title": t}} for t in tabs]}
            self.spreadsheet_id = self._run(self.svc.create(body=body, fields="spreadsheetId"))["spreadsheetId"]
        meta = self._run(self.svc.get(spreadsheetId=self.spreadsheet_id, fields="sheets.properties.title"))
        existing = {s["properties"]["title"] for s in meta["sheets"]}
        missing = [t for t in tabs if t not in existing]
        if missing:
            self._run(self.svc.batchUpdate(spreadsheetId=self.spreadsheet_id, body={
                "requests": [{"addSheet": {"properties": {"title": t}}} for t in missing]}))
        for tab, header in tabs.items():
            first = self.read_tab(tab)[:1]
            if not first or not any(first[0]):
                self.update_rows(tab, [(1, header)])
        return self.spreadsheet_id

    def read_tab(self, tab):
        res = self._run(self.svc.values().get(spreadsheetId=self.spreadsheet_id, range=f"'{tab}'",
                                              valueRenderOption="FORMATTED_VALUE"))
        return [[str(c) for c in r] for r in res.get("values", [])]

    def update_rows(self, tab, updates):
        if not updates:
            return
        data = [{"range": f"'{tab}'!A{n}:{_col(len(v))}{n}", "values": [v]} for n, v in updates]
        self._run(self.svc.values().batchUpdate(spreadsheetId=self.spreadsheet_id,
                                                body={"valueInputOption": "RAW", "data": data}))

    def append_rows(self, tab, rows):
        if rows:
            self._run(self.svc.values().append(spreadsheetId=self.spreadsheet_id, range=f"'{tab}'!A1",
                                               valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                                               body={"values": rows}))

    def replace_tab(self, tab, rows):
        self._run(self.svc.values().clear(spreadsheetId=self.spreadsheet_id, range=f"'{tab}'"))
        if rows:
            self.update_rows(tab, [(1, rows[0])])
            if len(rows) > 1:
                self._run(self.svc.values().update(spreadsheetId=self.spreadsheet_id, range=f"'{tab}'!A2",
                                                   valueInputOption="RAW", body={"values": rows[1:]}))

    def spreadsheet_url(self):
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}" if self.spreadsheet_id else None

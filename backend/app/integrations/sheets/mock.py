"""Offline stand-in for Google Sheets: stores the spreadsheet as a JSON file so
the whole sync engine can run and be tested without a Google account."""
import json
import threading
from pathlib import Path

from app.integrations.sheets.base import SheetsError


class MockSheetsClient:
    _lock = threading.Lock()

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fail_next = 0  # tests: number of upcoming calls that should fail
        self.calls = 0

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"id": "mock-spreadsheet", "tabs": {}}

    def _save(self, data: dict):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def _maybe_fail(self):
        self.calls += 1
        if self.fail_next > 0:
            self.fail_next -= 1
            raise SheetsError("Simulated Google Sheets outage (HTTP 503)")

    def ensure_spreadsheet(self, title, tabs):
        self._maybe_fail()
        with self._lock:
            d = self._load()
            d["title"] = title
            for tab, header in tabs.items():
                rows = d["tabs"].setdefault(tab, [])
                if not rows:
                    rows.append(list(header))
            self._save(d)
            return d["id"]

    def read_tab(self, tab):
        self._maybe_fail()
        with self._lock:
            return [list(r) for r in self._load()["tabs"].get(tab, [])]

    def update_rows(self, tab, updates):
        self._maybe_fail()
        with self._lock:
            d = self._load()
            rows = d["tabs"].setdefault(tab, [])
            for rownum, values in updates:
                while len(rows) < rownum:
                    rows.append([])
                rows[rownum - 1] = list(values)
            self._save(d)

    def append_rows(self, tab, new_rows):
        self._maybe_fail()
        with self._lock:
            d = self._load()
            d["tabs"].setdefault(tab, []).extend([list(r) for r in new_rows])
            self._save(d)

    def replace_tab(self, tab, rows):
        self._maybe_fail()
        with self._lock:
            d = self._load()
            d["tabs"][tab] = [list(r) for r in rows]
            self._save(d)

    def spreadsheet_url(self):
        return None

    # test helper: simulate a person editing a cell in the sheet
    def manual_edit(self, tab: str, row_index: int, col_index: int, value: str):
        with self._lock:
            d = self._load()
            row = d["tabs"][tab][row_index]
            while len(row) <= col_index:
                row.append("")
            row[col_index] = value
            self._save(d)

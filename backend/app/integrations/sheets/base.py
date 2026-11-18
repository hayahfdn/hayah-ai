from typing import Protocol


class SheetsError(Exception):
    """Raised for any Google Sheets failure; the sync job retries on it."""


class SheetsClient(Protocol):
    def ensure_spreadsheet(self, title: str, tabs: dict[str, list[str]]) -> str: ...
    def read_tab(self, tab: str) -> list[list[str]]: ...
    def update_rows(self, tab: str, updates: list[tuple[int, list[str]]]) -> None:
        """updates: (1-based row number, values) pairs."""
    def append_rows(self, tab: str, rows: list[list[str]]) -> None: ...
    def replace_tab(self, tab: str, rows: list[list[str]]) -> None:
        """Overwrite a whole tab (used for read-only report tabs)."""
    def spreadsheet_url(self) -> str | None: ...

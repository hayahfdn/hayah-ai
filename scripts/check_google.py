"""Live check of the real Google integration. Creates the spreadsheet tabs and
the HAYAH PROJECTS folder tree if missing, then prints their links.
Writes no project data. Run from backend/:  HAYAH_SHEETS_BACKEND=google HAYAH_DRIVE_BACKEND=google python ../scripts/check_google.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import get_settings  # noqa: E402
from app.integrations.drive import get_drive_client  # noqa: E402
from app.integrations.sheets import get_sheets_client  # noqa: E402
from app.services.sheets_sync import ALL_TABS  # noqa: E402

s = get_settings()
sheets = get_sheets_client()
sid = sheets.ensure_spreadsheet(s.sheets_spreadsheet_title, ALL_TABS)
print("Spreadsheet:", sheets.spreadsheet_url(), "-> set HAYAH_SHEETS_SPREADSHEET_ID =", sid)
drive = get_drive_client()
root = s.drive_root_folder_id or drive.ensure_folder(s.drive_root_folder_name, None)
for name in ["Raw Footages", "Final Videos", "Maintenance & Servicing", "Unassigned Media", "Pending Review"]:
    drive.ensure_folder(name, root)
print("Drive root:", drive.folder_url(root), "-> set HAYAH_DRIVE_ROOT_FOLDER_ID =", root)
print("Storage:", drive.storage_quota())

import os
import subprocess
import sys
from pathlib import Path

os.environ["HAYAH_DATABASE_URL"] = os.environ.get("HAYAH_TEST_DATABASE_URL",
                                                  "postgresql+psycopg://hayah:hayah@localhost:5432/hayah_test")
os.environ["HAYAH_ENV"] = "test"
os.environ["HAYAH_WHATSAPP_VERIFY_TOKEN"] = "verify-me"
os.environ["HAYAH_WHATSAPP_APP_SECRET"] = "app-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated():
    from app.db import get_engine
    with get_engine().begin() as c:
        c.execute(text("drop schema public cascade; create schema public;"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True, env=os.environ.copy())
    yield


@pytest.fixture(autouse=True)
def clean(tmp_path):
    from app.db import get_engine
    from app.integrations.drive import set_drive_client
    from app.integrations.drive.mock import MockDriveClient
    from app.integrations.sheets import set_sheets_client
    from app.integrations.sheets.mock import MockSheetsClient
    from app.security import login_limiter
    with get_engine().begin() as c:
        tables = c.execute(text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'")).scalars().all()
        c.execute(text("truncate " + ", ".join(f'"{t}"' for t in tables) + " restart identity cascade"))
    sheets = MockSheetsClient(tmp_path / "sheets.json")
    drive = MockDriveClient(tmp_path / "drive")
    set_sheets_client(sheets)
    set_drive_client(drive)
    login_limiter.reset()
    yield {"sheets": sheets, "drive": drive}


@pytest.fixture
def mocks(clean):
    return clean


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def seeded():
    from app.cli import seed_demo
    seed_demo()


def login(client, email, password="Demo-Pass-2026"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client, seeded):
    return login(client, "admin@hayah.local")


@pytest.fixture
def manager(client, seeded):
    return login(client, "manager@hayah.local")

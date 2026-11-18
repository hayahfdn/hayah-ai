import pytest
from fastapi import HTTPException

from app.services import link_fetch
from tests.conftest import login
from tests.test_import_upload import _book


def test_share_links_become_download_links():
    d = link_fetch.download_url
    assert d("https://docs.google.com/spreadsheets/d/abc_123/edit#gid=0") == \
        "https://docs.google.com/spreadsheets/d/abc_123/export?format=xlsx"
    assert d("https://1drv.ms/x/s!AbCd").startswith("https://api.onedrive.com/v1.0/shares/u!")
    assert "download=1" in d("https://hayah-my.sharepoint.com/:x:/g/personal/x/EAbc?e=1")
    assert "dl=1" in d("https://www.dropbox.com/s/abc/book.xlsx?dl=0")
    with pytest.raises(HTTPException):
        d("http://example.com/book.xlsx")


def test_private_addresses_refused():
    with pytest.raises(HTTPException) as e:
        link_fetch.fetch_workbook("https://localhost/book.xlsx")
    assert "private" in e.value.detail


def test_import_from_link_preview_and_apply(client, seeded, monkeypatch):
    monkeypatch.setattr(link_fetch, "fetch_workbook", lambda url: (_book(), "Hayah.xlsx"))
    admin = login(client, "admin@hayah.local")
    link = {"url": "https://1drv.ms/x/s!test", "apply": "false"}
    r = client.post("/api/admin/import-workbook", headers=admin, data=link)
    assert r.status_code == 200, r.text
    assert r.json()["wells"] == 1 and r.json()["file"] == "Hayah.xlsx (link)"
    assert client.get("/api/projects/7001", headers=admin).status_code == 404
    r = client.post("/api/admin/import-workbook", headers=admin, data={**link, "apply": "true"})
    assert r.json()["applied"] and client.get("/api/projects/7001", headers=admin).status_code == 200


def test_needs_file_or_link(client, seeded):
    admin = login(client, "admin@hayah.local")
    assert client.post("/api/admin/import-workbook", headers=admin, data={"apply": "false"}).status_code == 422

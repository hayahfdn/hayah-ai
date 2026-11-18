import io

import openpyxl

from tests.conftest import login


def _book() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Nov"
    ws.append(["الرقم", "تاريخ الطلب", "اسم البئر", "تاريخ الاستلام", "تاريخ التسليم", "المقاول", "نوع البئر", "التكلفة", "سعر البيع"])
    ws.append([7001, "11/02/2026", "فاعل خير", None, None, "Pak 2", "يدوي", 35, 140])
    ws.append(["7002b", "11/03/2026", "x", None, None, "Pak 2", "يدوي", 35, 0])
    for name in ("Ads", "UK Account", "Mo", "Ghazi", "Cliq"):
        wb.create_sheet(name).append(["No."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_preview_saves_nothing_then_apply(client, seeded):
    admin = login(client, "admin@hayah.local")
    files = {"file": ("Hayah.xlsx", _book(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post("/api/admin/import-workbook", headers=admin, files=files, data={"apply": "false"})
    assert r.status_code == 200, r.text
    assert r.json()["wells"] == 1 and not r.json()["applied"]
    assert any("7002b" in p["problem"] for p in r.json()["problems"])
    assert client.get("/api/projects/7001", headers=admin).status_code == 404
    r = client.post("/api/admin/import-workbook", headers=admin, files=files, data={"apply": "true"})
    assert r.json()["applied"] and client.get("/api/projects/7001", headers=admin).status_code == 200


def test_upload_is_admin_only(client, seeded):
    mgr = login(client, "manager@hayah.local")
    files = {"file": ("Hayah.xlsx", _book(), "application/octet-stream")}
    assert client.post("/api/admin/import-workbook", headers=mgr, files=files).status_code == 403

from tests.conftest import login
from tests.test_import_upload import _book


def _recent(client, h, **p):
    return client.get("/api/undo/recent", headers=h, params=p).json()


def test_undo_well_edit_and_refuses_when_changed_again(client, seeded):
    mgr = login(client, "manager@hayah.local")
    old = client.get("/api/projects/9001", headers=mgr).json()
    client.patch("/api/projects/9001", headers=mgr, json={"customer_name": "Wrong name", "sale_amount": "999.00"})
    last = _recent(client, mgr, mine=True)[0]
    assert last["entity_id"] == "9001" and set(last["fields"]) == {"customer_name", "sale_amount"}
    r = client.post(f"/api/undo/{last['id']}", headers=mgr)
    assert r.status_code == 200, r.text
    now = client.get("/api/projects/9001", headers=mgr).json()
    assert now["customer_name"] == old["customer_name"] and now["sale_amount"] == old["sale_amount"]
    assert client.post(f"/api/undo/{last['id']}", headers=mgr).status_code == 409  # only once

    client.patch("/api/projects/9002", headers=mgr, json={"customer_name": "A"})
    first = _recent(client, mgr, mine=True)[0]
    client.patch("/api/projects/9002", headers=mgr, json={"customer_name": "B"})
    assert client.post(f"/api/undo/{first['id']}", headers=mgr).status_code == 409


def test_staff_undo_only_own_edits(client, seeded):
    mgr, staff = login(client, "manager@hayah.local"), login(client, "staff@hayah.local")
    client.patch("/api/projects/9003", headers=mgr, json={"customer_name": "by manager"})
    mgr_edit = _recent(client, mgr, mine=True)[0]
    assert client.post(f"/api/undo/{mgr_edit['id']}", headers=staff).status_code == 403
    client.patch("/api/projects/9003", headers=staff, json={"village": "X"})
    mine = _recent(client, staff)
    assert len(mine) == 1 and client.post(f"/api/undo/{mine[0]['id']}", headers=staff).status_code == 200


def test_remove_workbook_import_keeps_hand_entered(client, seeded):
    admin = login(client, "admin@hayah.local")
    files = {"file": ("Hayah.xlsx", _book(), "application/octet-stream")}
    assert client.post("/api/admin/import-workbook", headers=admin, files=files, data={"apply": "true"}).json()["applied"]
    client.post("/api/projects", headers=admin, json={"well_id": 7500, "customer_name": "typed by hand"})
    imp = client.get("/api/admin/imports", headers=admin).json()[0]
    preview = client.post(f"/api/admin/imports/{imp['id']}/remove", headers=admin).json()
    assert preview["well_ids"] == [7001] and not preview["applied"]
    assert client.get("/api/projects/7001", headers=admin).status_code == 200  # preview changed nothing
    done = client.post(f"/api/admin/imports/{imp['id']}/remove", headers=admin, params={"apply": True}).json()
    assert done["applied"] and done["wells"] == 1
    assert client.get("/api/projects/7001", headers=admin).status_code == 404
    assert client.get("/api/projects/7500", headers=admin).status_code == 200
    assert client.get("/api/projects/9001", headers=admin).status_code == 200
    assert client.get("/api/admin/imports", headers=admin).json()[0]["removed"]
    # the same file can be imported again afterwards
    assert client.post("/api/admin/import-workbook", headers=admin, files=files, data={"apply": "true"}).json()["wells"] == 1


def test_ai_budget_capped_at_20(client, seeded):
    admin = login(client, "admin@hayah.local")
    r = client.put("/api/settings/ai", headers=admin, json={"ai_enabled": False, "monthly_budget_usd": 50, "min_confidence": 0.9})
    assert r.status_code == 422


def test_remove_import_made_before_tracking(client, seeded, db):
    """The live server's first import was made before imports listed what they added."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified
    from app.models import AuditLog, Transaction
    admin = login(client, "admin@hayah.local")
    files = {"file": ("Hayah.xlsx", _book(), "application/octet-stream")}
    client.post("/api/admin/import-workbook", headers=admin, files=files, data={"apply": "true"})
    w = db.scalar(select(AuditLog).where(AuditLog.action == "workbook.import"))
    w.after = {k: v for k, v in w.after.items() if k != "created"}
    flag_modified(w, "after")
    db.commit()
    done = client.post(f"/api/admin/imports/{w.id}/remove", headers=admin, params={"apply": True}).json()
    assert done["well_ids"] == [7001] and done["applied"]
    assert client.get("/api/projects/7001", headers=admin).status_code == 404
    assert client.get("/api/projects/9001", headers=admin).status_code == 200

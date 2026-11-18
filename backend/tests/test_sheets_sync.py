from app.models import SyncConflict
from app.services.jobs import run_due_jobs
from app.services.sheets_sync import MASTER, MASTER_HEADER, run_sync, status

COL = {h: i for i, h in enumerate(MASTER_HEADER)}


def master(mocks):
    return mocks["sheets"].read_tab(MASTER)


def test_initial_sync_creates_all_tabs_and_rows(db, seeded, mocks):
    run = run_sync(db)
    assert run.status == "succeeded" and run.stats["appended"] == 12
    rows = master(mocks)
    assert rows[0] == MASTER_HEADER and len(rows) == 13
    tabs = mocks["sheets"]._load()["tabs"]
    assert set(tabs) == {MASTER, "Maintenance Records", "Media Library", "Contractors", "Activity Log", "Pending Review"}
    assert status(db)["state"] == "synced"


def test_resync_never_duplicates_rows(db, seeded, mocks):
    run_sync(db)
    run = run_sync(db)
    assert run.stats["appended"] == 0 and run.stats["updated"] == 0
    wells = [r[0] for r in master(mocks)[1:]]
    assert len(wells) == len(set(wells)) == 12


def test_db_change_updates_the_right_row(client, manager, db, mocks):
    run_sync(db)
    client.patch("/api/projects/9005", json={"construction_status": "in_progress"}, headers=manager)
    assert status(db)["state"] == "pending"
    run_sync(db)
    row = next(r for r in master(mocks) if r[0] == "9005")
    assert row[COL["Construction Status"]] == "in_progress"


def test_manual_sheet_edit_detected_and_not_overwritten(client, manager, db, mocks):
    run_sync(db)
    idx = next(i for i, r in enumerate(master(mocks)) if r[0] == "9004")
    mocks["sheets"].manual_edit(MASTER, idx, COL["Notes"], "edited in sheet by office")
    client.patch("/api/projects/9004", json={"city": "Sylhet City"}, headers=manager)  # unrelated DB change
    run = run_sync(db)
    assert run.stats["conflicts_new"] == 1
    row = master(mocks)[idx]
    assert row[COL["Notes"]] == "edited in sheet by office"  # person's edit kept
    assert row[COL["City"]] == "Sylhet City"  # DB change still pushed
    assert status(db)["state"] == "conflicts"
    # second run: no new conflict, no loop
    assert run_sync(db).stats["conflicts_new"] == 0
    c = db.query(SyncConflict).one()
    # manager accepts the sheet value -> DB updated through the audited path
    r = client.post(f"/api/sync/conflicts/{c.id}/resolve", json={"keep": "sheet"}, headers=manager)
    assert r.status_code == 200
    assert client.get("/api/projects/9004", headers=manager).json()["notes"] == "edited in sheet by office"
    run_sync(db)
    assert status(db)["state"] == "synced"


def test_keep_db_value_overwrites_sheet_after_resolution(client, manager, db, mocks):
    run_sync(db)
    idx = next(i for i, r in enumerate(master(mocks)) if r[0] == "9006")
    mocks["sheets"].manual_edit(MASTER, idx, COL["Village"], "WRONG")
    run_sync(db)
    c = db.query(SyncConflict).one()
    client.post(f"/api/sync/conflicts/{c.id}/resolve", json={"keep": "db"}, headers=manager)
    run_sync(db)
    assert master(mocks)[idx][COL["Village"]] == "Al-Mawasit"


def test_delivery_status_cannot_be_accepted_from_sheet(client, manager, db, mocks):
    run_sync(db)
    idx = next(i for i, r in enumerate(master(mocks)) if r[0] == "9003")
    mocks["sheets"].manual_edit(MASTER, idx, COL["Delivery Status"], "delivered")
    run_sync(db)
    c = db.query(SyncConflict).one()
    r = client.post(f"/api/sync/conflicts/{c.id}/resolve", json={"keep": "sheet"}, headers=manager)
    assert r.status_code == 422
    assert client.get("/api/projects/9003", headers=manager).json()["delivery_status"] == "not_ready"


def test_duplicate_and_unknown_rows_reported(db, seeded, mocks):
    run_sync(db)
    rows = master(mocks)
    mocks["sheets"].append_rows(MASTER, [rows[1], ["4242", "", "someone typed this"]])
    run = run_sync(db)
    assert run.stats["duplicates"] == 1 and run.stats["unknown_rows"] == 1
    kinds = {c.kind for c in db.query(SyncConflict)}
    assert kinds == {"duplicate_row", "unknown_row"}
    assert len(master(mocks)) == 15  # nothing deleted from the sheet


def test_api_failure_is_retried_by_job_queue(client, manager, db, mocks):
    mocks["sheets"].fail_next = 1
    r = client.post("/api/sync/run", headers=manager)
    assert r.status_code == 502
    assert status(db)["state"] == "error"
    from app.models import Job
    db.query(Job).update({"next_run_at": Job.created_at})  # make retry due now
    db.commit()
    stats = run_due_jobs(db)
    assert stats["succeeded"] >= 1
    assert status(db)["state"] == "synced"

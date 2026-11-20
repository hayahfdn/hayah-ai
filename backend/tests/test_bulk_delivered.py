"""Mark old projects delivered: preview first, apply only the confirmed numbers, undo restores exactly."""
from datetime import date

from app.models import BulkChange, DeliveryStatus, Project, Sacrifice
from tests.conftest import login


def _real(db):
    """Make the sample rows count as real ones for this test (bulk skips samples)."""
    db.query(Project).update({Project.is_sample: False})
    db.query(Sacrifice).update({Sacrifice.is_sample: False})
    db.commit()


def test_preview_changes_nothing_and_apply_needs_matching_numbers(client, manager, db):
    _real(db)
    before = {p.id: (p.delivery_status, p.delivery_date) for p in db.query(Project)}
    pv = client.get("/api/bulk/old-delivered/preview", headers=manager).json()
    assert pv["totals"]["wells"] + pv["totals"]["sacrifices"] > 0
    assert pv["totals"]["real_date"] + pv["totals"]["estimated_date"] == pv["totals"]["wells"] + pv["totals"]["sacrifices"]
    db.expire_all()
    assert {p.id: (p.delivery_status, p.delivery_date) for p in db.query(Project)} == before

    bad = client.post("/api/bulk/old-delivered/apply", headers=manager,
                      json={"wells": pv["totals"]["wells"] + 1, "sacrifices": pv["totals"]["sacrifices"], "confirm": True})
    assert bad.status_code == 409
    no = client.post("/api/bulk/old-delivered/apply", headers=manager,
                     json={"wells": pv["totals"]["wells"], "sacrifices": pv["totals"]["sacrifices"], "confirm": False})
    assert no.status_code == 422


def test_apply_keeps_real_dates_flags_estimates_and_undo_restores(client, manager, db):
    _real(db)
    cut = date.today().replace(day=1)
    old = db.query(Project).filter(Project.order_date < cut, Project.delivery_status != DeliveryStatus.delivered).all()
    assert old
    with_date = [p for p in old if p.delivery_date]
    if not with_date:  # make sure one has a real date typed
        old[0].delivery_date = date(2020, 1, 2); db.commit(); with_date = [old[0]]
    snapshot = {p.id: (p.delivery_status, p.delivery_date, p.sale_amount, p.well_id, p.customer_name) for p in db.query(Project)}
    new_ones = db.query(Project).filter(Project.order_date >= cut).all()

    pv = client.get("/api/bulk/old-delivered/preview", headers=manager).json()
    r = client.post("/api/bulk/old-delivered/apply", headers=manager,
                    json={"wells": pv["totals"]["wells"], "sacrifices": pv["totals"]["sacrifices"], "confirm": True})
    assert r.status_code == 200, r.text
    db.expire_all()
    for p in db.query(Project).filter(Project.id.in_([x.id for x in old])):
        assert p.delivery_status == DeliveryStatus.delivered
        st, d, price, no, name = snapshot[p.id]
        assert (p.sale_amount, p.well_id, p.customer_name) == (price, no, name)  # nothing else touched
        if d:
            assert p.delivery_date == d and p.delivery_estimated is False
        else:
            assert p.delivery_estimated is True and p.delivery_date.month == p.order_date.month and (p.delivery_date.day >= 28)
    for p in new_ones:  # this month is left alone
        db.refresh(p)
        assert snapshot[p.id][0] == p.delivery_status

    again = client.get("/api/bulk/old-delivered/preview", headers=manager).json()
    assert again["totals"]["wells"] == 0

    u = client.post(f"/api/bulk/old-delivered/{r.json()['batch_id']}/undo", headers=manager)
    assert u.status_code == 200 and u.json()["restored"] == r.json()["changed"]
    db.expire_all()
    assert {p.id: (p.delivery_status, p.delivery_date, p.sale_amount, p.well_id, p.customer_name) for p in db.query(Project)} == snapshot
    assert db.get(BulkChange, r.json()["batch_id"]).undone_at is not None
    assert client.post(f"/api/bulk/old-delivered/{r.json()['batch_id']}/undo", headers=manager).status_code == 409


def test_staff_cannot_preview_or_apply(client, seeded):
    h = login(client, "staff@hayah.local")
    assert client.get("/api/bulk/old-delivered/preview", headers=h).status_code == 403
    assert client.post("/api/bulk/old-delivered/apply", headers=h, json={"wells": 0, "sacrifices": 0, "confirm": True}).status_code == 403


def test_samples_are_never_marked(client, manager):
    pv = client.get("/api/bulk/old-delivered/preview", headers=manager).json()
    assert pv["totals"] == {"wells": 0, "sacrifices": 0, "real_date": 0, "estimated_date": 0}

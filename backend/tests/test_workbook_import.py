from sqlalchemy import select

from app.models import Contractor, DeliveryConfirmation, Project, User
from app.services.workbook_import import import_wells


def _data(rows, month="2026-04"):
    return {"sheets": [{"month": month, "rows": rows}]}


def test_import_wells_never_overwrites_or_guesses(db, seeded):
    admin = db.scalar(select(User).where(User.email == "admin@hayah.local"))
    rows = [
        {"well_id": 1001, "order_date": "2026-04-01", "customer_name": "أحمد", "contractor": "India 1", "well_type": "بئر سطحي يدوي",
         "cost": 130.0, "sale_amount": None, "delivery_date": "2026-04-05", "pages": [6, 8], "follow_up": "October"},
        {"well_id": 1002, "order_date": "2026-04-02", "contractor": "Pak 2", "cost": 55.0, "sale_amount": 240.0, "pages": [6, 8]},
        {"well_id": None, "pages": [6, 8]},
        {"well_id": 9001, "cost": 1.0, "pages": [6, 8]},  # already exists (sample) -> left alone
    ]
    before = db.scalar(select(Project).where(Project.well_id == 9001)).cost
    rep = import_wells(db, _data(rows), actor=admin)
    db.commit()
    assert rep["imported"] == 2 and rep["skipped_existing"] == [9001] and len(rep["skipped_no_id"]) == 1
    assert rep["contractors_created"] == ["IND1"]
    assert db.scalar(select(Project).where(Project.well_id == 9001)).cost == before
    p = db.scalar(select(Project).where(Project.well_id == 1001))
    assert p.contractor.code == "IND1" and p.country == "India"
    assert p.delivery_status.value == "delivered" and str(p.delivery_date) == "2026-04-05"
    dc = db.scalar(select(DeliveryConfirmation).where(DeliveryConfirmation.project_id == p.id))
    assert dc.source == "workbook_import" and dc.status.value == "approved" and dc.decided_by_id == admin.id
    assert "Follow-up: October" in p.notes and p.payment_status.value == "unpaid"
    q = db.scalar(select(Project).where(Project.well_id == 1002))
    assert q.delivery_status.value == "not_ready" and q.payment_status.value == "paid"
    assert db.scalar(select(Contractor).where(Contractor.code == "PAK2")) is not None

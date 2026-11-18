from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models import Contractor, User
from app.services import finance as fin
from app.services.workbook_xlsx import contractor_code, hint_contractor


def test_contractor_names_from_the_workbook():
    assert contractor_code("Pak 1") == "PAK1" and contractor_code("TZ1") == "TZ1" and contractor_code("Tiz 1") == "TZ1"
    assert contractor_code("India 3") == "IND3" and contractor_code("Ahmed Masri") == "TZ1" and contractor_code("تنزانيا") is None
    assert hint_contractor("باكستان (بدر الدين) pk 2") == "PAK2"
    assert hint_contractor("Bangladesh (Bang 1)") == "BANG1"
    assert hint_contractor("Ghaidaa (India 1 + Pak2)") is None  # two contractors named: never guess
    assert hint_contractor("Western Union") is None


def test_extra_work_adds_to_owed_and_ad_refunds_reduce_ads(db, seeded):
    admin = db.scalar(select(User).where(User.email == "admin@hayah.local"))
    pak3 = db.scalar(select(Contractor).where(Contractor.code == "PAK3"))
    before = fin.contractor_ledger(db, pak3)["totals"]["invoiced"]
    ads_before = fin.summary(db)["headline"]["ad_spend"]
    fin.create_transaction(db, {"date": date(2026, 10, 26), "kind": "operating_expense", "contractor_id": pak3.id,
                                "category": fin.EXTRA_WORK, "amount": Decimal("65")}, actor=admin)
    fin.create_transaction(db, {"date": date(2026, 8, 3), "kind": "ad_spend", "direction": "in", "channel": "Google",
                                "amount": Decimal("0.20")}, actor=admin)
    db.commit()
    led = fin.contractor_ledger(db, pak3)
    assert led["totals"]["invoiced"] == before + 65
    assert any(t.category == fin.EXTRA_WORK for t in led["payments"])  # shown on the contractor's sheet
    assert round(fin.summary(db)["headline"]["ad_spend"], 2) == round(ads_before - 0.20, 2)

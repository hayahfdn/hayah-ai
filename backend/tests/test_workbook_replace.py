"""Replace everything earlier workbook imports loaded with a new workbook."""
import io
from datetime import date, datetime, timezone
from decimal import Decimal

import openpyxl
import pytest
from sqlalchemy import select

from tests.conftest import login


def _w(no, name, sale, cost=Decimal("35"), **kw):
    return {"well_id": no, "sheet": "Nov", "row": 2, "order_date": date(2026, 11, 2), "customer_name": name,
            "contractor": "PAK2", "well_type": "يدوي", "cost": cost, "sale_amount": sale, **kw}


def _s(no, name, price):
    return {"sacrifice_no": no, "sheet": "S NOV", "row": 2, "order_date": date(2026, 11, 3), "donor_name": name,
            "animal_type": "خروف", "cost": Decimal("60"), "sale_price": price}


def _t(day, amount, kind="income", ref=None):
    return {"date": date(2026, 11, day), "kind": kind, "direction": "in" if kind == "income" else "out",
            "account": "WISE", "amount": Decimal(amount), "reference": ref}


def _data(wells, sacs, txs):
    return {"wells": wells, "sacrifices": sacs, "transactions": txs, "problems": []}


def _import(db, user, data, name="v1.xlsx"):
    from app.services.audit import audit
    from app.services.workbook_import import import_full_workbook
    rep = import_full_workbook(db, data, actor=user)
    audit(db, "workbook.import", "workbook", name, actor=user, after=rep)
    db.commit()


@pytest.fixture
def setup(client, seeded, db):
    from app.models import FinalVideo, Plaque, Project, Sacrifice, Transaction, User, WiseTransaction
    from app.services import projects as psvc
    admin = db.scalar(select(User).where(User.email == "admin@hayah.local"))
    _import(db, admin, _data([_w(7001, "Old name", Decimal("140")), _w(7002, "Has plaque", Decimal("140")),
                              _w(7003, "Gone", Decimal("140"))],
                             [_s(5001, "Sac one", Decimal("99")), _s(5002, "Has video", Decimal("99")),
                              _s(5003, "Sac gone", Decimal("99"))],
                             [_t(1, "100", ref="A"), _t(2, "50", "ad_spend", ref="B")]))
    # work done in the system after the import
    p1 = psvc.get_by_well_id(db, 7001)
    psvc.update_project(db, p1, {"customer_name": "Typed by hand", "village": "Mithi",
                                 "notes": (p1.notes or "") + "\nCustomer called on 20 Nov"}, actor=admin)
    db.add(Plaque(kind="well", project_id=psvc.get_by_well_id(db, 7002).id))
    s2 = db.scalar(select(Sacrifice).where(Sacrifice.sacrifice_no == 5002))
    db.add(FinalVideo(kind="sacrifice", sacrifice_id=s2.id))
    t1 = db.scalar(select(Transaction).where(Transaction.reference == "A"))
    db.add(WiseTransaction(wise_id="w-1", profile_id=1, at=datetime.now(timezone.utc), direction="in",
                           amount=Decimal("100"), currency="USD", transaction_id=t1.id, match_status="matched", raw={}))
    psvc.create_project(db, {"well_id": 7500, "customer_name": "Hand well"}, actor=admin)
    db.commit()
    return {"admin": admin, "p1_id": p1.id, "plaque_well": psvc.get_by_well_id(db, 7002).id}


def _v2():
    return _data([_w(7001, "New name", Decimal("200"), delivery_date=date(2026, 11, 20)), _w(7004, "Brand new", Decimal("300"))],
                 [_s(5001, "Sac one renamed", Decimal("120")), _s(5004, "New sac", Decimal("99"))],
                 [_t(1, "100", ref="A"), _t(3, "75", ref="C")])


def test_replace_updates_in_place_keeps_work_and_deletes_the_rest(setup, db):
    from app.models import Project, Sacrifice, Transaction, WiseTransaction
    from app.services import workbook_replace as wr
    rep = wr.replace_all(db, _v2(), actor=setup["admin"], file="v2.xlsx")
    wr.finish(db, rep, actor=setup["admin"], backup={"files": []})
    db.commit()

    wells = {p.well_id: p for p in db.scalars(select(Project).where(Project.is_sample.is_(False)))}
    assert set(wells) == {7001, 7002, 7004, 7500}          # 7003 deleted, 7002 kept for its plaque
    p1 = wells[7001]
    assert p1.id == setup["p1_id"]                         # same record: everything linked to it stays linked
    assert p1.customer_name == "New name" and p1.sale_amount == Decimal("200.00")
    assert p1.village == "Mithi"                           # not a workbook column: kept
    assert "Customer called on 20 Nov" in p1.notes         # notes typed in the system kept
    assert p1.delivery_date == date(2026, 11, 20)
    assert rep["wells_kept"] == [{"number": 7002, "why": ["plaque"]}]
    assert rep["wells_deleted"] == [7003]
    assert rep["hand_edits_overwritten"][0] == {"number": 7001, "fields": ["customer_name"]}

    sacs = {s.sacrifice_no: s for s in db.scalars(select(Sacrifice).where(Sacrifice.is_sample.is_(False)))}
    assert set(sacs) == {5001, 5002, 5004}
    assert sacs[5001].donor_name == "Sac one renamed" and sacs[5001].sale_price == Decimal("120.00")
    assert rep["sacrifices_kept"] == [{"number": 5002, "why": ["final video"]}]

    refs = sorted(t.reference for t in db.scalars(select(Transaction).where(Transaction.is_sample.is_(False))))
    assert refs == ["A", "C"]                              # B (only in the old workbook) is gone, no duplicate A
    wt = db.scalar(select(WiseTransaction))
    assert db.get(Transaction, wt.transaction_id).reference == "A" and rep["wise_relinked"] == 1


def test_replace_twice_and_remove_afterwards(setup, db, client):
    from app.models import Project
    from app.services import workbook_replace as wr
    for name in ("v2.xlsx", "v3.xlsx"):
        rep = wr.replace_all(db, _v2(), actor=setup["admin"], file=name)
        wr.finish(db, rep, actor=setup["admin"], backup={"files": []})
        db.commit()
    assert rep["previous_imports"] and len(rep["previous_imports"]) == 1   # only the last one is still active
    assert rep["wells_deleted"] == [] and rep["hand_edits_overwritten"] == []  # the replace's own edits are not hand edits
    assert rep["wells_kept"] == [{"number": 7002, "why": ["plaque"]}]
    admin = login(client, "admin@hayah.local")
    imports = client.get("/api/admin/imports", headers=admin).json()
    assert [i["removed"] for i in imports] == [False, True, True]
    done = client.post(f"/api/admin/imports/{imports[0]['id']}/remove", headers=admin, params={"apply": True}).json()
    assert done["applied"]
    left = set(db.scalars(select(Project.well_id).where(Project.is_sample.is_(False))))
    assert left == {7001, 7002, 7500}  # 7001 was edited by hand (its timeline shows it) and 7002 has a plaque: both kept


def _book(rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Nov"
    ws.append(["الرقم", "تاريخ الطلب", "اسم البئر", "تاريخ الاستلام", "تاريخ التسليم", "المقاول", "نوع البئر", "التكلفة", "سعر البيع"])
    for r in rows:
        ws.append(r)
    for name in ("Ads", "UK Account", "Mo", "Ghazi", "Cliq"):
        wb.create_sheet(name).append(["No."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_replace_api_preview_confirm_backup_and_roles(client, seeded, tmp_path, monkeypatch):
    from app.services import backup as bk
    bdir = tmp_path / "backups"
    bdir.mkdir()
    monkeypatch.setattr(bk, "backup_dir", lambda: bdir)
    admin, mgr = login(client, "admin@hayah.local"), login(client, "manager@hayah.local")
    v1 = {"file": ("v1.xlsx", _book([[7001, "11/02/2026", "Old", None, None, "Pak 2", "يدوي", 35, 140],
                                     [7002, "11/02/2026", "Gone", None, None, "Pak 2", "يدوي", 35, 140]]), "application/octet-stream")}
    assert client.post("/api/admin/import-workbook", headers=admin, files=v1, data={"apply": "true"}).json()["applied"]
    v2 = _book([[7001, "11/02/2026", "New", None, None, "Pak 2", "يدوي", 35, 150], [7003, "11/04/2026", "Added", None, None, "Pak 2", "يدوي", 35, 140]])
    f = lambda: {"file": ("v2.xlsx", v2, "application/octet-stream")}  # noqa: E731

    assert client.post("/api/admin/import-workbook/replace", headers=mgr, files=f()).status_code == 403
    r = client.post("/api/admin/import-workbook/replace", headers=admin, files=f())
    assert r.status_code == 200, r.text
    pv = r.json()
    assert not pv["applied"] and pv["wells_deleted"] == [7002] and pv["wells_updated"] == 1 and pv["wells_added"] == 1
    assert client.get("/api/projects/7002", headers=admin).status_code == 200      # preview saved nothing
    assert list(bdir.iterdir()) == []                                          # and wrote no backup

    r = client.post("/api/admin/import-workbook/replace", headers=admin, files=f(), data={"apply": "true", "confirm": "yes"})
    assert r.status_code == 422 and client.get("/api/projects/7002", headers=admin).status_code == 200

    r = client.post("/api/admin/import-workbook/replace", headers=admin, files=f(), data={"apply": "true", "confirm": "replace"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["applied"] and any(n.endswith(".json.gz") for n in out["backup"]["files"])
    assert client.get("/api/projects/7002", headers=admin).status_code == 404
    assert client.get("/api/projects/7001", headers=admin).json()["customer_name"] == "New"
    assert client.get("/api/projects/7003", headers=admin).status_code == 200
    names = [b["name"] for b in client.get("/api/admin/backups", headers=admin).json()]
    assert names and client.get(f"/api/admin/backups/{names[0]}", headers=admin).status_code == 200
    assert client.get("/api/admin/backups", headers=mgr).status_code == 403
    assert client.get("/api/admin/backups/..%2Fsecret", headers=admin).status_code == 404

    # the Arabic word works too
    r = client.post("/api/admin/import-workbook/replace", headers=admin, files=f(), data={"apply": "true", "confirm": "استبدال"})
    assert r.status_code == 200 and r.json()["wells_updated"] == 2

"""Admin commands.

  python -m app.cli create-admin --email you@hayah.org --name "Name"   (prompts for password)
  python -m app.cli setup-workbook   # creates the standard contractor/account tabs (safe to repeat)
  python -m app.cli seed-demo        # 12 SAMPLE projects, flagged is_sample=True (never real data)
  python -m app.cli import-workbook Hayah.xlsx --actor you@hayah.org   # whole workbook (.xlsx), or a wells .json from the PDF extractor
  python -m app.cli sync-sheets
  python -m app.cli export-schemas   # writes docs/schemas/*.json
"""
import argparse
import getpass
import io
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    ConstructionStatus, Contractor, MediaCategory, PaymentStatus, Project, Role, User, VideoStatus,
)
from app.security import hash_password, validate_password_strength

DEMO_PASSWORD = "Demo-Pass-2026"
# Placeholder sample data: Well IDs start at 9001 so they can never collide with real wells (1337...).
SAMPLES = [
    (9001, "Pakistan", "Tharparkar", "Mithi", "متوسط", "PAK1", "completed", "delivered"),
    (9002, "Pakistan", "Tharparkar", "Islamkot", "يدوي", "PAK1", "completed", "pending"),
    (9003, "Pakistan", "Umerkot", "Kunri", "عميق", "PAK2", "in_progress", None),
    (9004, "Bangladesh", "Sylhet", "Jaintiapur", "يدوي", "BANG1", "new_order", None),
    (9005, "Bangladesh", "Rangpur", "Pirganj", "متوسط", "BANG1", "scheduled", None),
    (9006, "Nepal", "Madhesh", "Janakpur", "شمسي", "NEP1", "in_progress", None),
    (9007, "Tanzania", "Tanga", "Muheza", "عميق", "TZ1", "completed", "delivered"),
    (9008, "Pakistan", "Sindh", "Thatta", "شمسي", None, "new_order", None),
    (9009, "Pakistan", "Punjab", "Rajanpur", "يدوي", "PAK5", "on_hold", None),
    (9010, "Pakistan", "Sindh", "Badin", "متوسط", "PAK1", "completed", "pending"),
    (9011, "Nepal", "Lumbini", "Kapilvastu", "عميق", "NEP2", "completed", "delivered"),
    (9012, "Tanzania", "Pwani", "Bagamoyo", "يدوي", "TZ1", "in_progress", None),
]
SALE = {"يدوي": 300, "متوسط": 650, "عميق": 1500, "شمسي": 2400}
COST = {"يدوي": 170, "متوسط": 420, "عميق": 1050, "شمسي": 1800}
NAMES = ["عائلة أحمد", "Fatima Trust", "مسجد النور", "Ali & Sons", "أم محمد", "Green Hope", "عبدالله سالم",
         "Noor Foundation", "Hassan family", "مدرسة الأمل", "Yusuf Ibrahim", "قرية السلام"]


def create_admin(email: str, name: str, password: str | None = None):
    password = password or getpass.getpass("Password: ")
    validate_password_strength(password)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email.lower())):
            print("User already exists")
            return
        db.add(User(email=email.lower(), full_name=name, role=Role.super_admin, password_hash=hash_password(password)))
        db.commit()
        print(f"Super admin {email} created")


def seed_demo(with_media: bool = True):
    from app.services import delivery as dsvc, maintenance as msvc, projects as psvc
    from app.services.media import store_media
    with SessionLocal() as db:
        if db.scalar(select(Project).where(Project.well_id == 9001)):
            print("Demo data already present")
            return
        from app.services.finance import ensure_workbook_defaults
        ensure_workbook_defaults(db)
        contractors = {c.code: c for c in db.scalars(select(Contractor))}
        users = [("admin@hayah.local", "Demo Super Admin", Role.super_admin, None, None),
                 ("manager@hayah.local", "Demo Operations Manager", Role.operations_manager, None, "+920000000001"),
                 ("p1@hayah.local", "Demo Contractor Pak 1", Role.contractor, "PAK1", "+920000000002"),
                 ("maint@hayah.local", "Demo Maintenance", Role.maintenance, None, "+920000000003"),
                 ("viewer@hayah.local", "Demo Viewer", Role.viewer, None, None)]
        by_email = {}
        for email, name, role, ccode, phone in users:
            u = db.scalar(select(User).where(User.email == email))
            if not u:
                u = User(email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD), phone=phone,
                         contractor_id=contractors[ccode].id if ccode else None, preferred_lang="ar")
                db.add(u)
                db.flush()
            by_email[email] = u
        admin, manager = by_email["admin@hayah.local"], by_email["manager@hayah.local"]
        today = date.today()
        for i, (wid, country, city, village, wtype, ccode, cstatus, dstatus) in enumerate(SAMPLES):
            order_date = today - timedelta(days=200 - i * 15)
            p = psvc.create_project(db, {
                "well_id": wid, "order_date": order_date, "customer_name": NAMES[i], "customer_phone": f"+00000000{wid}",
                "country": country, "city": city, "village": village, "well_type": wtype, "sales_source": "website" if i % 2 else "whatsapp",
                "contractor_id": contractors[ccode].id if ccode else None, "sale_amount": Decimal(SALE[wtype]), "cost": Decimal(COST[wtype]),
                "payment_method": "Shopify" if i % 2 else "Bank transfer", "shopify_order": f"#S{1100 + i}" if i % 2 else None,
                "extras": "سيراميك" if i % 4 == 0 else ("خزان" if i % 4 == 1 else None),
                "payment_status": PaymentStatus.paid if i % 3 else PaymentStatus.partial,
                "construction_status": ConstructionStatus.new_order, "notes": "SAMPLE DATA – not a real project"},
                actor=admin, is_sample=True)
            if cstatus != "new_order":
                psvc.update_project(db, p, {"construction_status": ConstructionStatus(cstatus),
                                            "construction_start_date": order_date + timedelta(days=10)}, actor=manager)
            if cstatus == "completed":
                psvc.update_project(db, p, {"completion_date": order_date + timedelta(days=40)}, actor=manager)
            if dstatus == "delivered":
                dc = dsvc.create_pending(db, p, delivery_date=order_date + timedelta(days=45), source="dashboard", requested_by=manager)
                dsvc.decide(db, dc, approve=True, actor=manager, note="Sample approval")
                psvc.update_project(db, p, {"video_status": VideoStatus.completed,
                                            "final_video_link": f"https://example.com/sample-video/{wid}"}, actor=manager)
            elif dstatus == "pending" and i % 2:
                dsvc.create_pending(db, p, delivery_date=today, source="dashboard", requested_by=manager,
                                    notes="Sample pending confirmation")
            if wid in (9001, 9007):
                msvc.create_record(db, p, {"date": today - timedelta(days=20), "problem_type": "pump_failure",
                                           "description": "Sample: hand pump handle broken", "technician": "Sample Tech",
                                           "repair_cost": Decimal("25.00"), "next_maintenance_date": today + timedelta(days=160)},
                                   actor=by_email["maint@hayah.local"])
            if with_media and i < 4:
                png = _tiny_png(i)
                store_media(db, io.BytesIO(png), original_filename=f"sample_{wid}.png", mime_type="image/png", project=p,
                            category=MediaCategory.construction, source="dashboard", sender="Sample data", actor=manager)
        _seed_finance(db, contractors, admin)
        db.commit()
        print(f"Seeded {len(SAMPLES)} SAMPLE projects (Well IDs 9001-9012). Demo password for *@hayah.local: {DEMO_PASSWORD}")


def _seed_finance(db, contractors, actor):
    """SAMPLE sacrifices (numbers 90001+) and money rows, all flagged is_sample."""
    from app.models import FinanceAccount, TxKind
    from app.services import finance as fin
    today = date.today()
    acc = {a.code: a for a in db.scalars(select(FinanceAccount))}
    animals = [("خروف", 120, 199), ("ماعز", 95, 159), ("بقرة", 160, 259)]
    intents = ["صدقة", "عقيقة", "بنية الشفاء", "عايدة"]
    for i in range(14):
        a, cost, price = animals[i % 3]
        od = today - timedelta(days=5 + i * 9)
        fin.create_sacrifice(db, {
            "sacrifice_no": 90001 + i, "order_date": od, "donor_name": NAMES[i % len(NAMES)],
            "received_date": od + timedelta(days=1), "delivery_date": od + timedelta(days=4) if i > 1 else None,
            "contractor_id": contractors["TZ1"].id, "animal_type": a, "cost": Decimal(cost), "sale_price": Decimal(price),
            "payment_method": "Shopify", "extras": "إطعام" if i % 3 == 0 else None, "sales_source": "Website",
            "shopify_order": f"#S{1140 + i}", "intention": intents[i % 4], "notes": "SAMPLE DATA"},
            actor=actor, is_sample=True)
    rows = [
        (40, TxKind.income, "WISE", None, None, None, 6200, "Shopify payout"),
        (12, TxKind.income, "WISE", None, None, None, 2900, "Shopify payout"),
        (35, TxKind.contractor_payment, "WISE", "PAK1", None, None, 900, "Payment for wells"),
        (20, TxKind.contractor_payment, "WISE", "PAK2", None, None, 600, "Payment for wells"),
        (18, TxKind.contractor_payment, "WISE", "TZ1", None, None, 1200, "Payment for sacrifices"),
        (15, TxKind.contractor_payment, "WISE", "NEP1", None, None, 400, "Advance"),
        (30, TxKind.ad_spend, "WISE", None, "Facebook", None, 380, "Campaign"),
        (10, TxKind.ad_spend, "WISE", None, "Google", None, 220, "Search ads"),
        (8, TxKind.ad_spend, "WISE", None, "Neutrons", None, 300, "Agency fee"),
        (25, TxKind.operating_expense, "WISE", None, None, "Software", 79, "Shopify plan"),
        (22, TxKind.operating_expense, "WISE", None, None, "Salaries", 600, "Video editor"),
        (28, TxKind.partner_took, "MOHAMMED", None, None, None, 500, "Cash for field visit"),
        (14, TxKind.partner_spent, "MOHAMMED", None, None, None, 320, "Paid PAK5 deposit"),
        (21, TxKind.partner_took, "GHAZI", None, None, None, 300, "Ads card top-up"),
        (9, TxKind.partner_withdrawal, "GHAZI", None, None, None, 150, "Personal withdrawal"),
        (60, TxKind.loan, "CLIQ", None, None, None, 1000, "Start-up loan"),
        (6, TxKind.partner_spent, "CLIQ", None, None, None, 90, "Printing"),
    ]
    for days, kind, a, ccode, channel, cat, amount, desc in rows:
        fin.create_transaction(db, {
            "date": today - timedelta(days=days), "kind": kind, "account_id": acc[a].id,
            "contractor_id": contractors[ccode].id if ccode else None, "channel": channel, "category": cat,
            "amount": Decimal(amount), "description": f"SAMPLE: {desc}"}, actor=actor, is_sample=True)


def _tiny_png(seed: int) -> bytes:
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes([seed % 256, (seed // 256) % 256, 134]) * 4 for _ in range(4))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--name", required=True)
    sub.add_parser("seed-demo")
    sub.add_parser("setup-workbook")
    sub.add_parser("sync-sheets")
    w = sub.add_parser("import-workbook")
    w.add_argument("path")
    w.add_argument("--actor", required=True, help="email of the manager running the import")
    sub.add_parser("export-schemas")
    args = ap.parse_args()
    if args.cmd == "create-admin":
        create_admin(args.email, args.name)
    elif args.cmd == "seed-demo":
        seed_demo()
    elif args.cmd == "setup-workbook":
        from app.services.finance import ensure_workbook_defaults
        with SessionLocal() as db:
            ensure_workbook_defaults(db)
            db.commit()
        print("Workbook tabs ready (contractors PAK1-5, NEP1-3, BANG1, TZ1; accounts Wise, Mohammed, Ghazi, Haya Cliq)")
    elif args.cmd == "import-workbook":
        from app.services.workbook_import import import_wells
        with SessionLocal() as db:
            actor = db.scalar(select(User).where(User.email == args.actor.lower()))
            if not actor:
                raise SystemExit("No user with that email")
            if args.path.lower().endswith(".xlsx"):
                from app.services.workbook_import import import_full_workbook
                from app.services.workbook_xlsx import read_workbook
                data = read_workbook(args.path)
                report = import_full_workbook(db, data, actor=actor) | {"problems": data["problems"]}
            else:
                report = import_wells(db, json.loads(Path(args.path).read_text()), actor=actor)
            db.commit()
        print(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    elif args.cmd == "sync-sheets":
        from app.services.sheets_sync import run_sync
        with SessionLocal() as db:
            print(run_sync(db, "manual").stats)
    elif args.cmd == "export-schemas":
        from app.integrations.ai.schemas import export_json_schemas
        out = Path(__file__).resolve().parents[2] / "docs" / "schemas"
        out.mkdir(parents=True, exist_ok=True)
        for name, schema in export_json_schemas().items():
            (out / f"{name}.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False))
        print(f"Schemas written to {out}")


if __name__ == "__main__":
    main()

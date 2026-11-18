"""Admin commands.

  python -m app.cli create-admin --email you@hayah.org --name "Name"   (prompts for password)
  python -m app.cli seed-demo        # 12 SAMPLE projects, flagged is_sample=True (never real data)
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
    (9001, "Pakistan", "Tharparkar", "Mithi", "medium_artesian", "P1", "completed", "delivered"),
    (9002, "Pakistan", "Tharparkar", "Islamkot", "shallow_hand_pump", "P1", "completed", "pending"),
    (9003, "Pakistan", "Umerkot", "Kunri", "deep_borewell", "P2", "in_progress", None),
    (9004, "Bangladesh", "Sylhet", "Jaintiapur", "shallow_hand_pump", "B1", "new_order", None),
    (9005, "Bangladesh", "Rangpur", "Pirganj", "medium_artesian", "B1", "scheduled", None),
    (9006, "Yemen", "Taiz", "Al-Mawasit", "solar_submersible", "Y1", "in_progress", None),
    (9007, "Somalia", "Baidoa", "Bonkay", "deep_borewell", "S1", "completed", "delivered"),
    (9008, "Sudan", "Kassala", "Wad Sharifey", "solar_submersible", None, "new_order", None),
    (9009, "India", "Bihar", "Kishanganj", "shallow_hand_pump", "P2", "on_hold", None),
    (9010, "Pakistan", "Sindh", "Badin", "medium_artesian", "P1", "completed", "pending"),
    (9011, "Yemen", "Hodeidah", "Bajil", "deep_borewell", "Y1", "completed", "delivered"),
    (9012, "Somalia", "Gedo", "Luuq", "shallow_hand_pump", "S1", "in_progress", None),
]
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
        contractors = {}
        for code, name, country in [("P1", "Placeholder Contractor P1", "Pakistan"), ("P2", "Placeholder Contractor P2", "Pakistan"),
                                    ("B1", "Placeholder Contractor B1", "Bangladesh"), ("Y1", "Placeholder Contractor Y1", "Yemen"),
                                    ("S1", "Placeholder Contractor S1", "Somalia")]:
            c = db.scalar(select(Contractor).where(Contractor.code == code)) or Contractor(code=code, name=name, country=country)
            db.add(c)
            db.flush()
            contractors[code] = c
        users = [("admin@hayah.local", "Demo Super Admin", Role.super_admin, None, None),
                 ("manager@hayah.local", "Demo Operations Manager", Role.operations_manager, None, "+920000000001"),
                 ("p1@hayah.local", "Demo Contractor P1", Role.contractor, "P1", "+920000000002"),
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
                "contractor_id": contractors[ccode].id if ccode else None, "sale_amount": Decimal(350 + 150 * (i % 5)),
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
        db.commit()
        print(f"Seeded {len(SAMPLES)} SAMPLE projects (Well IDs 9001-9012). Demo password for *@hayah.local: {DEMO_PASSWORD}")


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
    sub.add_parser("sync-sheets")
    sub.add_parser("export-schemas")
    args = ap.parse_args()
    if args.cmd == "create-admin":
        create_admin(args.email, args.name)
    elif args.cmd == "seed-demo":
        seed_demo()
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

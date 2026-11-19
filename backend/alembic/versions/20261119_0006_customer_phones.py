"""customer phone numbers in E.164 next to the original text

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19 01:00:00

Adds columns only. The typed phone stays exactly as it was; a standard copy (E.164),
the number's country and a status are added. Sacrifices get a phone column; for
sacrifices made from Shopify the number is copied from their "Phone: ..." note line
(the note itself is left unchanged). Local numbers with no known country are marked
needs_country for staff to choose; nothing is guessed.
"""
import re

from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

COLS = [("customer_phone_e164", 20), ("customer_phone_country", 2), ("customer_phone_status", 16)]


def upgrade():
    op.add_column('sacrifices', sa.Column('customer_phone', sa.String(40), nullable=True))
    for table in ("projects", "sacrifices"):
        for name, n in COLS:
            op.add_column(table, sa.Column(name, sa.String(n), nullable=True))
        op.create_index(f"ix_{table}_customer_phone_e164", table, ["customer_phone_e164"])

    from app.services.phones import normalize
    conn = op.get_bind()
    for sid, notes in conn.execute(sa.text("select id, notes from sacrifices where notes like '%Phone: %'")).all():
        m = re.search(r"^Phone: (.+)$", notes or "", re.M)
        if m:
            conn.execute(sa.text("update sacrifices set customer_phone = :p where id = :id"), {"p": m.group(1).strip()[:40], "id": sid})
    for table in ("projects", "sacrifices"):
        for rid, phone in conn.execute(sa.text(f"select id, customer_phone from {table} where customer_phone is not null")).all():
            r = normalize(phone)
            conn.execute(sa.text(f"update {table} set customer_phone_e164 = :e, customer_phone_country = :c, "
                                 f"customer_phone_status = :s where id = :id"),
                         {"e": r["e164"], "c": r["country"], "s": r["status"], "id": rid})


def downgrade():
    for table in ("projects", "sacrifices"):
        op.drop_index(f"ix_{table}_customer_phone_e164", table)
        for name, _ in COLS:
            op.drop_column(table, name)
    op.drop_column('sacrifices', 'customer_phone')

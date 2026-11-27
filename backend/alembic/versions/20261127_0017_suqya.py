"""سقيا الماء في الحرم: a new order type with its own numbers and plaque

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-27 11:30:00

Hayah, 27 Nov 2026: water boxes handed to the guests of al-Haram for a donor, with a portrait plaque
(Haram background, سقيا number, month, quantity, donor name and prayer). Numbers come from Counter "suqya".
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "suqya",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("suqya_no", sa.BigInteger, nullable=False),
        sa.Column("order_date", sa.Date),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="100"),
        sa.Column("donor_name", sa.String(300)),
        sa.Column("dua", sa.String(80)),
        sa.Column("customer_name", sa.String(200)),
        sa.Column("customer_phone", sa.String(40)),
        sa.Column("customer_phone_e164", sa.String(20)),
        sa.Column("customer_phone_country", sa.String(2)),
        sa.Column("customer_phone_status", sa.String(16)),
        sa.Column("sale_price", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("notes", sa.Text),
        sa.Column("design", JSONB),
        sa.Column("plaque_saved_at", sa.DateTime(timezone=True)),
        sa.Column("plaque_saved_by", sa.String(200)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("sent_by", sa.String(200)),
        sa.Column("created_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("suqya_no > 0", name="ck_suqya_no_positive"),
    )
    op.create_index("ix_suqya_suqya_no", "suqya", ["suqya_no"], unique=True)
    op.create_index("ix_suqya_order_date", "suqya", ["order_date"])
    op.create_index("ix_suqya_customer_phone_e164", "suqya", ["customer_phone_e164"])


def downgrade():
    op.drop_table("suqya")

"""Wise transactions, read only

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-20 03:00:00

wise_transactions keeps every activity read from the Wise business profile exactly once
(unique wise_id), how it was classified, and which ledger row it matches. Nothing is ever sent to
Wise except read requests. New table only.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wise_transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("wise_id", sa.String(200), nullable=False, unique=True),
        sa.Column("profile_id", sa.BigInteger, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("activity_type", sa.String(40)),
        sa.Column("status", sa.String(30)),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("usd_amount", sa.Numeric(14, 2)),
        sa.Column("counterparty", sa.String(200)),
        sa.Column("description", sa.Text),
        sa.Column("resource_type", sa.String(40)),
        sa.Column("resource_id", sa.String(60)),
        sa.Column("category", sa.String(30), nullable=False, server_default="other", index=True),
        sa.Column("contractor_id", sa.Integer, sa.ForeignKey("contractors.id")),
        sa.Column("match_status", sa.String(12), nullable=False, server_default="unmatched", index=True),
        sa.Column("transaction_id", sa.Integer, sa.ForeignKey("transactions.id"), unique=True),
        sa.Column("matched_by", sa.String(200)),
        sa.Column("matched_at", sa.DateTime(timezone=True)),
        sa.Column("raw", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("wise_transactions")

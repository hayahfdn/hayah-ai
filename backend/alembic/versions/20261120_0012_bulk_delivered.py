"""Delivered status for sacrifices, an "estimated date" flag, and reversible bulk changes

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-20 02:00:00

- projects.delivery_estimated / sacrifices.delivery_estimated: true when the delivery date was not
  known and was set to the last day of the order month by the bulk "mark old projects delivered".
- sacrifices.delivery_status (not_ready | pending | delivered), like wells. Sacrifices that already
  have a delivery date are delivered (a date typed in the workbook counts as approved); the rest
  are not_ready.
- bulk_changes: one row per bulk action, holding every record's before/after so it can be undone.
Nothing existing is changed apart from filling the new columns. Downgrade drops them.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("delivery_estimated", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("sacrifices", sa.Column("delivery_estimated", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("sacrifices", sa.Column("delivery_status", sa.String(40), nullable=False, server_default="not_ready"))
    op.create_index("ix_sacrifices_delivery_status", "sacrifices", ["delivery_status"])
    op.execute("update sacrifices set delivery_status = 'delivered' where delivery_date is not null")
    op.create_table(
        "bulk_changes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("items", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        sa.Column("undone_by", sa.Integer, sa.ForeignKey("users.id")),
    )


def downgrade():
    op.drop_table("bulk_changes")
    op.drop_index("ix_sacrifices_delivery_status", "sacrifices")
    op.drop_column("sacrifices", "delivery_status")
    op.drop_column("sacrifices", "delivery_estimated")
    op.drop_column("projects", "delivery_estimated")

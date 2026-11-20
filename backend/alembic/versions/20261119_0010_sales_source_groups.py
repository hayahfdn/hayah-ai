"""Unified sales source (source_group) on wells and sacrifices

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19 10:00:00

Adds one column per table and fills it from the existing sales_source text, which is
not changed (it stays as the original for review). Downgrade drops the column only.
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    from app.services.sales_sources import DEFAULT_GROUPS, _index, unify
    idx = _index(DEFAULT_GROUPS)
    conn = op.get_bind()
    for table in ("projects", "sacrifices"):
        op.add_column(table, sa.Column("source_group", sa.String(40), nullable=True))
        op.create_index(f"ix_{table}_source_group", table, ["source_group"])
        rows = conn.execute(sa.text(f"select id, sales_source from {table}")).all()
        by: dict[str, list[int]] = {}
        for rid, raw in rows:
            by.setdefault(unify(raw, _idx=idx), []).append(rid)
        for grp, ids in by.items():
            conn.execute(sa.text(f"update {table} set source_group = :g where id = any(:ids)"), {"g": grp, "ids": ids})


def downgrade():
    for table in ("projects", "sacrifices"):
        op.drop_index(f"ix_{table}_source_group", table_name=table)
        op.drop_column(table, "source_group")

"""Contractors work on wells, sacrifices or both

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-21 02:00:00

Hayah, 21 Nov 2026: a sacrifices contractor is chosen only on the sacrifices page and a wells contractor
only on the wells pages. contractors.kind = wells | sacrifices | both, set from what each contractor has
done so far (a contractor with no work yet stays "both" until a manager sets it on the contractors page).
"""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contractors", sa.Column("kind", sa.String(12), nullable=False, server_default="both"))
    op.execute("""
        UPDATE contractors c SET kind = CASE
          WHEN EXISTS (SELECT 1 FROM projects p WHERE p.contractor_id = c.id)
               AND NOT EXISTS (SELECT 1 FROM sacrifices s WHERE s.contractor_id = c.id) THEN 'wells'
          WHEN EXISTS (SELECT 1 FROM sacrifices s WHERE s.contractor_id = c.id)
               AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.contractor_id = c.id) THEN 'sacrifices'
          ELSE 'both' END
    """)


def downgrade():
    op.drop_column("contractors", "kind")

"""shopify history import: how each past order unit was matched

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18 15:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    # sure | likely | guess | created | none (past orders only; empty for live orders)
    op.add_column('shopify_order_items', sa.Column('match', sa.String(20), nullable=True))


def downgrade():
    op.drop_column('shopify_order_items', 'match')

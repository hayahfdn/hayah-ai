"""shopify orders and dedication text

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 14:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('dedication', sa.Text(), nullable=True))
    op.add_column('sacrifices', sa.Column('dedication', sa.Text(), nullable=True))
    op.create_table(
        'shopify_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('shopify_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(60), nullable=False),
        sa.Column('created_at_shop', sa.DateTime(timezone=True), nullable=True),
        sa.Column('financial_status', sa.String(40), nullable=True),
        sa.Column('cancelled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('total', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('customer_name', sa.String(200), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='imported'),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='webhook'),
        sa.Column('raw', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shopify_orders_shopify_id', 'shopify_orders', ['shopify_id'], unique=True)
    op.create_index('ix_shopify_orders_name', 'shopify_orders', ['name'])
    op.create_index('ix_shopify_orders_created_at_shop', 'shopify_orders', ['created_at_shop'])
    op.create_index('ix_shopify_orders_status', 'shopify_orders', ['status'])
    op.create_table(
        'shopify_order_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('shopify_orders.id'), nullable=False),
        sa.Column('line_item_id', sa.BigInteger(), nullable=False),
        sa.Column('unit', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(300), nullable=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('sacrifice_id', sa.Integer(), sa.ForeignKey('sacrifices.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('line_item_id', 'unit', name='uq_shopify_item_unit'),
    )
    op.create_index('ix_shopify_order_items_order_id', 'shopify_order_items', ['order_id'])
    op.create_index('ix_shopify_order_items_project_id', 'shopify_order_items', ['project_id'])
    op.create_index('ix_shopify_order_items_sacrifice_id', 'shopify_order_items', ['sacrifice_id'])


def downgrade():
    op.drop_table('shopify_order_items')
    op.drop_table('shopify_orders')
    op.drop_column('sacrifices', 'dedication')
    op.drop_column('projects', 'dedication')

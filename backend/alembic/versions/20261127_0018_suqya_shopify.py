"""سقيا from Shopify: order number, source and country on suqya; link from shopify_order_items

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-27 12:00:00

Hayah, 27 Nov 2026: water (سقيا) bought on Shopify becomes a سقيا project automatically, like wells and
sacrifices. Each Shopify unit is linked to the سقيا made for it (shopify_order_items.suqya_id).
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("suqya", sa.Column("shopify_order", sa.String(60)))
    op.add_column("suqya", sa.Column("sales_source", sa.String(120)))
    op.add_column("suqya", sa.Column("dedication", sa.Text))
    op.create_index("ix_suqya_shopify_order", "suqya", ["shopify_order"])
    op.add_column("shopify_order_items", sa.Column("suqya_id", sa.Integer, sa.ForeignKey("suqya.id")))
    op.create_index("ix_shopify_order_items_suqya_id", "shopify_order_items", ["suqya_id"])


def downgrade():
    op.drop_index("ix_shopify_order_items_suqya_id", "shopify_order_items")
    op.drop_column("shopify_order_items", "suqya_id")
    op.drop_index("ix_suqya_shopify_order", "suqya")
    op.drop_column("suqya", "dedication")
    op.drop_column("suqya", "sales_source")
    op.drop_column("suqya", "shopify_order")

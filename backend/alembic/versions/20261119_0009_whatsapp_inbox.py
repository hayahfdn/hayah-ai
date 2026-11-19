"""WhatsApp inbox on the official Cloud API: conversations and messages

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-19 07:00:00

New tables only. The intake number and its stored messages (inbound_messages) are not touched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'wa_conversations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('wa_id', sa.String(32), nullable=False, unique=True),
        sa.Column('phone_e164', sa.String(32), nullable=False),
        sa.Column('contact_name', sa.String(200)),
        sa.Column('status', sa.String(12), nullable=False, server_default='open'),
        sa.Column('assigned_to_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id')),
        sa.Column('sacrifice_id', sa.Integer(), sa.ForeignKey('sacrifices.id')),
        sa.Column('last_message_at', sa.DateTime(timezone=True)),
        sa.Column('last_inbound_at', sa.DateTime(timezone=True)),
        sa.Column('last_preview', sa.String(300)),
        sa.Column('last_direction', sa.String(3)),
        sa.Column('unread', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    for c in ('phone_e164', 'status', 'assigned_to_id', 'project_id', 'sacrifice_id', 'last_message_at'):
        op.create_index(f'ix_wa_conversations_{c}', 'wa_conversations', [c])
    op.create_table(
        'wa_messages',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('wa_conversations.id'), nullable=False),
        sa.Column('direction', sa.String(3), nullable=False),
        sa.Column('wa_message_id', sa.String(200), unique=True),
        sa.Column('client_ref', sa.String(64), unique=True),
        sa.Column('type', sa.String(20), nullable=False, server_default='text'),
        sa.Column('text', sa.Text()),
        sa.Column('media_asset_id', sa.Integer(), sa.ForeignKey('media_assets.id')),
        sa.Column('media', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('template', postgresql.JSONB()),
        sa.Column('status', sa.String(12), nullable=False, server_default='received'),
        sa.Column('error', sa.Text()),
        sa.Column('source', sa.String(12), nullable=False, server_default='cloud_api'),
        sa.Column('sent_by_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('sent_by_label', sa.String(200)),
        sa.Column('reply_to_wa_id', sa.String(200)),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_wa_messages_conv_id', 'wa_messages', ['conversation_id', 'id'])
    op.create_index('ix_wa_messages_status', 'wa_messages', ['status'])


def downgrade():
    op.drop_table('wa_messages')
    op.drop_table('wa_conversations')

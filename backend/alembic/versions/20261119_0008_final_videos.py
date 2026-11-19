"""final delivery video per order

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19 05:00:00

One new table. The video files themselves are media assets (category final_video), so nothing
existing changes. Orders that already have a final video file get a row with status "uploaded";
orders that only have a final video link keep it as it is.
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

STATES = ('not_uploaded', 'uploaded', 'ready_for_delivery', 'sent_to_customer')


def upgrade():
    op.create_table(
        'final_videos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True, unique=True),
        sa.Column('sacrifice_id', sa.Integer(), sa.ForeignKey('sacrifices.id'), nullable=True, unique=True),
        sa.Column('status', sa.Enum(*STATES, name='final_video_status', native_enum=False, length=40), nullable=False),
        sa.Column('current_media_id', sa.Integer(), sa.ForeignKey('media_assets.id')),
        sa.Column('uploaded_at', sa.DateTime(timezone=True)), sa.Column('uploaded_by', sa.String(200)),
        sa.Column('ready_at', sa.DateTime(timezone=True)), sa.Column('ready_by', sa.String(200)),
        sa.Column('sent_at', sa.DateTime(timezone=True)), sa.Column('sent_by', sa.String(200)),
        sa.Column('sent_note', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(project_id is null) <> (sacrifice_id is null)", name='ck_final_videos_one_order'),
    )
    op.create_index('ix_final_videos_status', 'final_videos', ['status'])
    op.create_index('ix_final_videos_updated_at', 'final_videos', ['updated_at'])
    # wells that already have a final video file stored
    op.execute("""
        insert into final_videos (kind, project_id, status, current_media_id, uploaded_at, created_at, updated_at)
        select 'well', m.project_id, 'uploaded', max(m.id), max(m.created_at), min(m.created_at), max(m.created_at)
        from media_assets m where m.category = 'FINAL' and m.project_id is not null
          and m.mime_type like 'video/%' group by m.project_id
    """)


def downgrade():
    op.drop_table('final_videos')

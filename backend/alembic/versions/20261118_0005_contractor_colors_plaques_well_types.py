"""contractor row colours, approved plaque on each well, and the four well types

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18 20:30:00

The server takes a database backup before every update (deploy/update.sh), so a copy
exists from just before this runs. The well-type changes are also written to the audit
log ('well_types.normalized') and can be undone from Settings or by downgrading.
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

# Soft, clearly different colours; dark text stays readable on all of them.
PALETTE = ["#CFE3FA", "#D3F0D9", "#FFE2C2", "#E6D9F7", "#FAD4DE", "#CDEFEA", "#FFF0B8", "#EBDDCB",
           "#DDEFC2", "#F9D3C9", "#C9DDF0", "#F2D6EC", "#D5E8E0", "#E4E4E4", "#D9D3F5", "#C8EAF5"]


def upgrade():
    op.add_column('contractors', sa.Column('color', sa.String(7), nullable=True))
    op.add_column('projects', sa.Column('plaque_status', sa.String(16), nullable=True))
    op.add_column('projects', sa.Column('plaque_media_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('plaque_approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('plaque_approved_by', sa.String(200), nullable=True))
    op.create_foreign_key('fk_projects_plaque_media', 'projects', 'media_assets', ['plaque_media_id'], ['id'])

    conn = op.get_bind()
    # A fixed colour for every existing contractor (editable later on the Contractors page).
    ids = conn.execute(sa.text("select id from contractors order by country nulls last, code")).scalars().all()
    for i, cid in enumerate(ids):
        conn.execute(sa.text("update contractors set color = :c where id = :id"), {"c": PALETTE[i % len(PALETTE)], "id": cid})

    # Wells that already have saved plaques start as drafts.
    conn.execute(sa.text("update projects set plaque_status = 'draft' where id in "
                         "(select distinct project_id from project_events where event_type = 'plaque_saved')"))

    # One name per well type (Hayah's table). Logged and reversible.
    from app.services.well_types import TYPES, normalize_rows
    normalize_rows(conn, actor_label="تحديث النظام (أنواع الآبار)")
    conn.execute(sa.text("insert into app_settings (key, value, updated_at) values ('well_types', cast(:v as jsonb), now()) "
                         "on conflict (key) do update set value = excluded.value, updated_at = now()"),
                 {"v": json.dumps({"values": TYPES}, ensure_ascii=False)})


def downgrade():
    conn = op.get_bind()
    from app.services.well_types import undo_rows
    done = {r[0] for r in conn.execute(sa.text("select entity_id from audit_log where action = 'well_types.restored'"))}
    for (aid,) in conn.execute(sa.text("select id from audit_log where action = 'well_types.normalized' order by id desc")).all():
        if str(aid) not in done:
            undo_rows(conn, aid, actor_label="System downgrade")
    op.drop_constraint('fk_projects_plaque_media', 'projects', type_='foreignkey')
    for c in ('plaque_approved_by', 'plaque_approved_at', 'plaque_media_id', 'plaque_status'):
        op.drop_column('projects', c)
    op.drop_column('contractors', 'color')

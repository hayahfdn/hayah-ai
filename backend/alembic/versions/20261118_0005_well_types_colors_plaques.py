"""unified well types, contractor row colours, approved plaque per well

- contractors.color: one fixed row colour per contractor (filled for existing contractors).
- projects.plaque_media_id / plaque_approved_at / plaque_approved_by_id: the approved plaque.
- Well types: every existing value is mapped onto يدوي / متوسط / عميق / شمسي (and the one
  "سطحي كهربائي" project onto كهربائي). Each changed well gets an audit_log row with the old
  value, so the original spelling is never lost. Values that match no rule are left as they are.
- The well type list in Settings is reset to the four types.

Nothing is deleted. Downgrade removes the new columns but does not restore old spellings
(they are in audit_log, action "project.well_type_normalized").

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18 20:00:00
"""
import json

import sqlalchemy as sa
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    from app.services.contractor_colors import next_color
    from app.services.well_types import CANONICAL, normalize

    op.add_column('contractors', sa.Column('color', sa.String(7), nullable=True))
    op.add_column('projects', sa.Column('plaque_media_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('plaque_approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('plaque_approved_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_projects_plaque_media', 'projects', 'media_assets', ['plaque_media_id'], ['id'])
    op.create_foreign_key('fk_projects_plaque_approved_by', 'projects', 'users', ['plaque_approved_by_id'], ['id'])

    bind = op.get_bind()

    # Contractor colours, in code order so the result is predictable.
    used: set[str] = set()
    for cid, in bind.execute(sa.text("select id from contractors order by code")).all():
        c = next_color(used)
        used.add(c)
        bind.execute(sa.text("update contractors set color = :c where id = :id"), {"c": c, "id": cid})

    # Well types.
    rows = bind.execute(sa.text("select id, well_id, well_type from projects where well_type is not null")).all()
    for pid, well_id, old in rows:
        new = normalize(old)
        if new == old:
            continue
        bind.execute(sa.text("update projects set well_type = :n, version = version + 1 where id = :id"), {"n": new, "id": pid})
        bind.execute(sa.text(
            "insert into audit_log (at, actor_label, action, entity_type, entity_id, before, after) "
            "values (now(), 'system (migration 0005)', 'project.well_type_normalized', 'project', :e, "
            "cast(:b as jsonb), cast(:a as jsonb))"),
            {"e": str(well_id), "b": json.dumps({"well_type": old}, ensure_ascii=False),
             "a": json.dumps({"well_type": new}, ensure_ascii=False)})

    # Settings list: only the four types are offered from now on.
    value = json.dumps({"values": CANONICAL}, ensure_ascii=False)
    bind.execute(sa.text("update app_settings set value = cast(:v as jsonb), updated_at = now() where key = 'well_types'"), {"v": value})


def downgrade():
    op.drop_constraint('fk_projects_plaque_approved_by', 'projects', type_='foreignkey')
    op.drop_constraint('fk_projects_plaque_media', 'projects', type_='foreignkey')
    op.drop_column('projects', 'plaque_approved_by_id')
    op.drop_column('projects', 'plaque_approved_at')
    op.drop_column('projects', 'plaque_media_id')
    op.drop_column('contractors', 'color')

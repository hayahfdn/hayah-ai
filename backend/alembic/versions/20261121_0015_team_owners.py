"""Team workflow v2: eight stages, one responsible person per stage, per-order reassignment, contractor colours

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-21 01:00:00

Hayah, 21 Nov 2026: every stage has exactly one responsible person (app setting "team_owners",
stage -> user id); the manager can move one order's stage to someone else (team_assignments).
users.team_stage from 0014 is converted into the owners setting and then dropped.
Contractor row colours follow HAYAH's workbook: Pak 1 #B1CF94, Pak 2 #77BD3B, Pak 5 #4EAD5B, Bang 1 #F6C9CE.
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None

OLD_TO_NEW = {"intake": ["intake", "contractor"], "customer": ["design", "approval", "delivery"], "delivery": ["review"]}
COLOURS = {"PAK1": "#B1CF94", "PAK2": "#77BD3B", "PAK5": "#4EAD5B", "BANG1": "#F6C9CE"}


def upgrade():
    op.create_table(
        "team_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by", sa.String(200)),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint("project_id", "stage", name="uq_team_assignments_project_stage"),
    )
    conn = op.get_bind()
    owners = {}
    for uid, stage in conn.execute(sa.text("select id, team_stage from users where team_stage is not null and is_active order by id")):
        for s in OLD_TO_NEW.get(stage, []):
            owners.setdefault(s, uid)
    if owners:
        row = conn.execute(sa.text("select value from app_settings where key = 'team_owners'")).first()
        if row is None:
            conn.execute(sa.text("insert into app_settings (key, value, updated_at) values ('team_owners', cast(:v as jsonb), now())"), {"v": json.dumps(owners)})
    op.drop_column("users", "team_stage")
    for code, colour in COLOURS.items():
        conn.execute(sa.text("update contractors set color = :c where upper(replace(code, ' ', '')) = :code"), {"c": colour, "code": code})


def downgrade():
    op.add_column("users", sa.Column("team_stage", sa.String(12)))
    op.drop_table("team_assignments")

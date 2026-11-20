"""Team tasks: who does which part of the order workflow

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-21 00:00:00

users.team_stage says which part of the workflow a person owns (Hayah, 21 Nov 2026):
  intake   (غازي)  receive the order, set the country, choose the contractor
  customer (شذى)   contact the customer, design the plaque, send it for approval, record the approval
  delivery (غيداء) check order number and phone, upload the final video, complete the delivery
team_steps keeps the steps that are ticked by hand (the others are read from the order itself).
New column and new table only; nothing existing changes.
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("team_stage", sa.String(12)))
    op.create_table(
        "team_steps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_by_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("done_by", sa.String(200)),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint("project_id", "step", name="uq_team_steps_project_step"),
    )


def downgrade():
    op.drop_table("team_steps")
    op.drop_column("users", "team_stage")

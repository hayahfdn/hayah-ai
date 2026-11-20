"""Project add-ons linked to sacrifices, a fixed list order for projects, per-user zoom

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-20 01:00:00

- projects.listed_at: the moment a project joined the list. The projects list is sorted by it
  (newest first) so editing a project or changing its status never moves it. Filled for existing
  rows from their creation date (created_at for projects made in the system; the order date for
  projects imported from the workbook, whose created_at is only the import time).
- sacrifices.parent_project_id: a sheep bought as an add-on of a well is its own sacrifice, linked
  to the well it was bought with. Existing Shopify sheep sacrifices are linked from the note the
  Shopify import wrote on the well ("خروف add-on: sacrifice N").
- users.ui_zoom: each person's interface zoom (80-150 %), so it follows them across devices.
Nothing existing is changed apart from filling the new columns. Downgrade drops the columns only.
"""
import re

from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

IMPORTED_SOURCES = ("workbook_import", "import", "sheets")


def upgrade():
    conn = op.get_bind()
    op.add_column("projects", sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_projects_listed_at", "projects", ["listed_at"])
    conn.execute(sa.text(LISTED_SQL), {"src": list(IMPORTED_SOURCES)})

    op.add_column("sacrifices", sa.Column("parent_project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=True))
    op.create_index("ix_sacrifices_parent_project_id", "sacrifices", ["parent_project_id"])
    rows = conn.execute(sa.text("select id, notes from projects where notes like '%add-on: sacrifice%'")).all()
    for pid, notes in rows:
        for no in re.findall(r"add-on: sacrifice (\d+)", notes or ""):
            conn.execute(sa.text("update sacrifices set parent_project_id = :p where sacrifice_no = :n and parent_project_id is null"),
                         {"p": pid, "n": int(no)})

    op.add_column("users", sa.Column("ui_zoom", sa.SmallInteger, nullable=True))


# Shared with the "re-sort projects" button (app/services/project_order.py).
LISTED_SQL = """
update projects p set listed_at = case
    when exists (select 1 from project_events e where e.project_id = p.id and e.event_type = 'project_created'
                 and e.source = any(:src)) and p.order_date is not null
        then p.order_date::timestamp at time zone 'UTC' + make_interval(secs => least(p.well_id, 86399))
    else p.created_at end
"""


def downgrade():
    op.drop_column("users", "ui_zoom")
    op.drop_index("ix_sacrifices_parent_project_id", table_name="sacrifices")
    op.drop_column("sacrifices", "parent_project_id")
    op.drop_index("ix_projects_listed_at", table_name="projects")
    op.drop_column("projects", "listed_at")

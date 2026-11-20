"""Projects list order (Hayah, 20 Nov 2026): newest project on top, by the date it was created.

The list is sorted by projects.listed_at, set once when a project is added (so a new project is
always on top). Editing a project, changing its status or reloading never moves it. The
"re-sort projects" button sets every project's place again from its creation date:
created_at for projects made in the system (dashboard, Shopify, WhatsApp, assistant), and the
order date for projects imported from the workbook (their created_at is only the import time).
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import User
from app.services.audit import audit

IMPORTED_SOURCES = ["workbook_import", "import", "sheets"]
CREATION_SQL = """
case when exists (select 1 from project_events e where e.project_id = p.id and e.event_type = 'project_created'
                  and e.source = any(:src)) and p.order_date is not null
     then p.order_date::timestamp at time zone 'UTC' + make_interval(secs => least(p.well_id, 86399))
     else p.created_at end
"""


def resort(db: Session, actor: User | None) -> int:
    """Re-sort all projects newest first by creation date. Returns how many changed place."""
    n = db.execute(text(f"update projects p set listed_at = {CREATION_SQL} "
                        f"where p.listed_at is distinct from ({CREATION_SQL})"), {"src": IMPORTED_SOURCES}).rowcount
    audit(db, "projects.resort", "project", None, actor=actor, after={"changed": n})
    return n

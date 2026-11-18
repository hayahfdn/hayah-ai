"""Background worker: runs queued jobs (retries with backoff), a periodic
Google Sheets sync, and a daily health check. Run: python -m app.worker"""
import logging
import time
from datetime import datetime, timezone

import app.services.intake  # noqa: F401  (registers handlers)
import app.services.sheets_sync  # noqa: F401
import app.services.shopify  # noqa: F401
from app.db import SessionLocal
from app.services.audit import audit
from app.services.jobs import enqueue, handler, run_due_jobs

log = logging.getLogger("hayah.worker")
SYNC_EVERY_S = 15 * 60


@handler("daily_health_check")
def daily_health(db, payload):
    from app.api.system import health_full
    from app.models import Role, User
    report = health_full(db, User(role=Role.super_admin))
    audit(db, "system.daily_health_check", "system", "health", after=report)
    if report["status"] != "ok" or report.get("failed_jobs") or report.get("sheets") == "error" or \
            (report.get("drive", {}).get("percent") or 0) > 85:
        audit(db, "system.needs_admin_attention", "system", "health", after=report)


def main():
    logging.basicConfig(level=logging.INFO)
    last_sync = 0.0
    while True:
        db = SessionLocal()
        try:
            now = time.time()
            if now - last_sync > SYNC_EVERY_S:
                enqueue(db, "sheets_sync", {"trigger": "scheduled"}, coalesce=True)
                today = datetime.now(timezone.utc).date().isoformat()
                enqueue(db, "daily_health_check", {}, key=f"health:{today}")
                enqueue(db, "shopify_sync", {"trigger": "scheduled"}, coalesce=True)
                db.commit()
                last_sync = now
            stats = run_due_jobs(db)
            if any(stats.values()):
                log.info("jobs: %s", stats)
        except Exception:  # keep the worker alive
            log.exception("worker loop error")
            db.rollback()
        finally:
            db.close()
        time.sleep(5)


if __name__ == "__main__":
    main()

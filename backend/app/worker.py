"""Background worker: runs queued jobs (retries with backoff), a periodic
Google Sheets sync, and a daily health check. Run: python -m app.worker"""
import logging
import time
from datetime import datetime, timezone

import app.services.intake  # noqa: F401  (registers handlers)
import app.services.sheets_sync  # noqa: F401
import app.services.shopify  # noqa: F401
import app.services.sales_sources  # noqa: F401  (keeps the unified source current)
import app.services.wa_inbox  # noqa: F401  (WhatsApp inbox: media download, send retries)
import app.services.wise  # noqa: F401  (Wise read only sync)
from app.db import SessionLocal
from app.services.audit import audit
from app.services.jobs import enqueue, handler, run_due_jobs

log = logging.getLogger("hayah.worker")
SYNC_EVERY_S = 15 * 60
WISE_EVERY_S = 60 * 60
SHOPIFY_EVERY_S = 2 * 60  # light catch-up for anything a webhook missed (only orders changed since last time)


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
    last_sync = last_wise = last_shopify = 0.0
    while True:
        db = SessionLocal()
        try:
            now = time.time()
            if now - last_sync > SYNC_EVERY_S:
                enqueue(db, "sheets_sync", {"trigger": "scheduled"}, coalesce=True)
                today = datetime.now(timezone.utc).date().isoformat()
                enqueue(db, "daily_health_check", {}, key=f"health:{today}")
                db.commit()
                last_sync = now
            if now - last_shopify > SHOPIFY_EVERY_S:
                enqueue(db, "shopify_sync", {"trigger": "scheduled"}, coalesce=True)
                db.commit()
                last_shopify = now
            if now - last_wise > WISE_EVERY_S:  # hourly, read only
                enqueue(db, "wise_sync", {"trigger": "scheduled"}, coalesce=True)
                db.commit()
                last_wise = now
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

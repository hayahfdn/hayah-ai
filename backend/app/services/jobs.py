"""Durable job queue on PostgreSQL (no extra infrastructure needed).

- enqueue() is idempotent via `idempotency_key`.
- run_due_jobs() claims jobs with SELECT ... FOR UPDATE SKIP LOCKED, so several
  workers can run safely.
- Failures retry with exponential backoff; after max_attempts the job is marked
  `failed` and shows up on the dashboard for an administrator.
"""
import logging
import traceback
from datetime import timedelta
from typing import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Job, JobStatus, utcnow
from app.services.audit import audit

log = logging.getLogger("hayah.jobs")
HANDLERS: dict[str, Callable[[Session, dict], dict | None]] = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(db: Session, kind: str, payload: dict | None = None, *, key: str | None = None,
            coalesce: bool = False, max_attempts: int = 6) -> Job | None:
    """coalesce=True: skip if an unfinished job of this kind already exists."""
    if coalesce:
        existing = db.scalar(select(Job).where(Job.kind == kind, Job.status.in_([JobStatus.queued, JobStatus.retrying])))
        if existing:
            return existing
    if key:
        existing = db.scalar(select(Job).where(Job.idempotency_key == key))
        if existing:
            return existing
    job = Job(kind=kind, payload=payload or {}, idempotency_key=key, max_attempts=max_attempts)
    try:
        with db.begin_nested():
            db.add(job)
    except IntegrityError:
        return db.scalar(select(Job).where(Job.idempotency_key == key))
    return job


def backoff_seconds(attempts: int) -> int:
    return min(30 * (2 ** (attempts - 1)), 3600)


def run_due_jobs(db: Session, limit: int = 20, kinds: list[str] | None = None) -> dict:
    stats = {"succeeded": 0, "retrying": 0, "failed": 0}
    for _ in range(limit):
        q = (select(Job).where(Job.status.in_([JobStatus.queued, JobStatus.retrying]), Job.next_run_at <= utcnow())
             .order_by(Job.next_run_at).limit(1).with_for_update(skip_locked=True))
        if kinds:
            q = q.where(Job.kind.in_(kinds))
        job = db.scalar(q)
        if not job:
            break
        job.status = JobStatus.running
        job.attempts += 1
        db.commit()
        fn = HANDLERS.get(job.kind)
        try:
            if not fn:
                raise RuntimeError(f"No handler for job kind {job.kind}")
            fn(db, job.payload)
            job.status = JobStatus.succeeded
            job.finished_at = utcnow()
            job.last_error = None
            db.commit()
            stats["succeeded"] += 1
        except Exception as exc:  # noqa: BLE001 - every failure must be recorded
            db.rollback()
            job = db.get(Job, job.id)
            job.last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}"[:4000]
            if job.attempts >= job.max_attempts:
                job.status = JobStatus.failed
                job.finished_at = utcnow()
                audit(db, "job_failed_needs_admin", "job", job.id, after={"kind": job.kind, "error": str(exc)[:500]})
                stats["failed"] += 1
            else:
                job.status = JobStatus.retrying
                job.next_run_at = utcnow() + timedelta(seconds=backoff_seconds(job.attempts))
                stats["retrying"] += 1
            db.commit()
            log.warning("job %s (%s) failed attempt %s: %s", job.id, job.kind, job.attempts, exc)
    return stats


def retry_job(db: Session, job: Job) -> None:
    job.status = JobStatus.queued
    job.next_run_at = utcnow()
    job.max_attempts = max(job.max_attempts, job.attempts + 3)

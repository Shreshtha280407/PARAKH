"""Durable job queue backed by PostgreSQL. No Redis/Celery -- `SELECT ...
FOR UPDATE SKIP LOCKED` is enough for the handful of verification jobs P2.1
enqueues per assessment.

Claim correctness depends on real row-level locking, which only Postgres
(among the backends this repo targets) provides -- SQLite silently ignores
`FOR UPDATE SKIP LOCKED` (single-writer database, no row locks to take).
Unit tests that merely check the queued->running state transition work
against either backend; the test that proves two concurrent claimants never
grab the same job requires a live Postgres connection (see
server/tests/test_jobs.py::test_concurrent_claims_never_double_process).
"""
import datetime
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger("parakh.jobs")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def enqueue(db: Session, job_type: str, payload: dict, max_attempts: int = 3) -> models.Job:
    job = models.Job(type=job_type, payload=payload, max_attempts=max_attempts)
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("job enqueued id=%s type=%s", job.id, job_type)
    return job


def claim_job(db: Session, worker_id: str) -> models.Job | None:
    """Atomically claim the oldest queued job. On Postgres, SKIP LOCKED
    guarantees two concurrent callers never claim the same row -- the
    second caller's SELECT simply skips rows locked by the first and (if no
    other queued row exists) returns None instead of blocking or racing."""
    stmt = (
        select(models.Job)
        .where(models.Job.status == "queued")
        .order_by(models.Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.execute(stmt).scalars().first()
    if job is None:
        return None
    job.status = "running"
    job.locked_at = utcnow()
    job.locked_by = worker_id
    job.started_at = utcnow()
    job.attempts += 1
    db.commit()
    db.refresh(job)
    logger.info("job claimed id=%s type=%s worker=%s attempt=%s", job.id, job.type, worker_id, job.attempts)
    return job


def mark_succeeded(db: Session, job: models.Job) -> None:
    job.status = "succeeded"
    job.finished_at = utcnow()
    job.last_error = None
    db.commit()
    logger.info("job succeeded id=%s type=%s", job.id, job.type)


def mark_failed(db: Session, job: models.Job, error: str) -> None:
    job.last_error = error[:2000]
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = utcnow()
        logger.error("job failed permanently id=%s type=%s attempts=%s error=%s", job.id, job.type, job.attempts, error)
    else:
        job.status = "queued"  # will be retried by a future claim
        job.locked_at = None
        job.locked_by = None
        logger.warning("job attempt failed, will retry id=%s type=%s attempts=%s error=%s", job.id, job.type, job.attempts, error)
    db.commit()

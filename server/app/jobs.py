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
from .config import settings

logger = logging.getLogger("parakh.jobs")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def enqueue(db: Session, job_type: str, payload: dict, max_attempts: int = 3, commit: bool = True) -> models.Job:
    """commit=False lets a caller fold job creation into a larger atomic
    transaction (e.g. evidence finalisation) instead of it committing on its
    own -- the caller is then responsible for the eventual db.commit()."""
    job = models.Job(type=job_type, payload=payload, max_attempts=max_attempts)
    db.add(job)
    db.flush()
    if commit:
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
    job.lease_expires_at = utcnow() + datetime.timedelta(seconds=settings.job_lease_seconds)
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


def recover_stale_jobs(db: Session) -> int:
    """Crash recovery: a job stuck in 'running' past its lease
    (lease_expires_at, set at claim time) belongs to a worker that was
    killed or crashed mid-job -- it will never call mark_succeeded/
    mark_failed itself. Treated exactly like a failed attempt: retried if
    attempts haven't hit max_attempts yet, permanently failed otherwise.
    Call this once per poll cycle (see worker.py's main loop) -- a plain
    UPDATE-style sweep, cheap and almost always a no-op in the normal case.

    Row-locks each candidate (FOR UPDATE SKIP LOCKED) so two worker
    processes sweeping at the same moment can't both reset the same job.
    """
    stmt = (
        select(models.Job)
        .where(models.Job.status == "running", models.Job.lease_expires_at < utcnow())
        .with_for_update(skip_locked=True)
    )
    stale_jobs = db.execute(stmt).scalars().all()
    for job in stale_jobs:
        job.last_error = "worker lease expired -- presumed crashed before finishing this job"
        job.lease_expires_at = None
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = utcnow()
            logger.error("stale job recovered as permanently failed id=%s type=%s attempts=%s", job.id, job.type, job.attempts)
        else:
            job.status = "queued"
            job.locked_at = None
            job.locked_by = None
            logger.warning("stale job recovered and requeued id=%s type=%s attempts=%s", job.id, job.type, job.attempts)
    if stale_jobs:
        db.commit()
    return len(stale_jobs)

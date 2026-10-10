"""Durable jobs queue tests. See server/app/jobs.py and conftest.py's
module docstring for why the concurrency test below requires a real
PostgreSQL connection (TEST_DATABASE_URL) and fails loudly rather than
skipping when one isn't available.
"""
import datetime
import threading

import pytest

from server.app import jobs, models


def test_enqueue_creates_a_queued_job(db_session):
    job = jobs.enqueue(db_session, "verify_evidence", {"evidence_item_id": 1})
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.type == "verify_evidence"
    assert job.payload == {"evidence_item_id": 1}


def test_claim_moves_job_to_running_and_increments_attempts(db_session):
    jobs.enqueue(db_session, "verify_evidence", {"evidence_item_id": 1})
    claimed = jobs.claim_job(db_session, "worker-a")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.locked_by == "worker-a"
    assert claimed.locked_at is not None
    assert claimed.started_at is not None


def test_claim_on_empty_queue_returns_none(db_session):
    assert jobs.claim_job(db_session, "worker-a") is None


def test_claim_returns_oldest_job_first(db_session):
    first = jobs.enqueue(db_session, "verify_evidence", {"n": 1})
    jobs.enqueue(db_session, "verify_evidence", {"n": 2})
    claimed = jobs.claim_job(db_session, "worker-a")
    assert claimed.id == first.id


def test_a_running_job_is_not_claimed_again(db_session):
    jobs.enqueue(db_session, "verify_evidence", {"n": 1})
    second_job = jobs.enqueue(db_session, "verify_evidence", {"n": 2})
    first_claim = jobs.claim_job(db_session, "worker-a")
    second_claim = jobs.claim_job(db_session, "worker-b")
    assert first_claim.id != second_claim.id
    assert second_claim.id == second_job.id
    assert jobs.claim_job(db_session, "worker-c") is None  # nothing left queued


def test_mark_succeeded(db_session):
    jobs.enqueue(db_session, "verify_evidence", {"n": 1})
    job = jobs.claim_job(db_session, "worker-a")
    jobs.mark_succeeded(db_session, job)
    assert job.status == "succeeded"
    assert job.finished_at is not None


def test_mark_failed_retries_until_max_attempts(db_session):
    job = jobs.enqueue(db_session, "verify_evidence", {"n": 1}, max_attempts=2)

    claimed1 = jobs.claim_job(db_session, "worker-a")
    jobs.mark_failed(db_session, claimed1, "boom 1")
    assert claimed1.status == "queued"  # attempt 1 of 2 -- retry
    assert claimed1.last_error == "boom 1"
    assert claimed1.locked_by is None

    claimed2 = jobs.claim_job(db_session, "worker-b")
    assert claimed2.id == job.id
    assert claimed2.attempts == 2
    jobs.mark_failed(db_session, claimed2, "boom 2")
    assert claimed2.status == "failed"  # attempt 2 of 2 -- permanent failure
    assert claimed2.finished_at is not None

    assert jobs.claim_job(db_session, "worker-c") is None  # failed jobs are never reclaimed


def test_recover_stale_jobs_is_a_no_op_when_nothing_is_stale(db_session):
    assert jobs.recover_stale_jobs(db_session) == 0

    jobs.enqueue(db_session, "verify_evidence", {"n": 1})
    claimed = jobs.claim_job(db_session, "worker-a")  # fresh lease, not expired
    assert jobs.recover_stale_jobs(db_session) == 0
    db_session.refresh(claimed)
    assert claimed.status == "running"


def test_recover_stale_jobs_requeues_a_crashed_workers_job(db_session):
    """Simulates a worker that claimed a job, then crashed before calling
    mark_succeeded/mark_failed -- the lease (set at claim time) expires,
    and the next sweep must notice and requeue it for another worker."""
    job = jobs.enqueue(db_session, "verify_evidence", {"n": 1}, max_attempts=3)
    claimed = jobs.claim_job(db_session, "worker-that-crashes")
    assert claimed.attempts == 1

    # Backdate the lease to simulate it having expired (no sleep needed).
    claimed.lease_expires_at = jobs.utcnow() - datetime.timedelta(seconds=1)
    db_session.commit()

    recovered = jobs.recover_stale_jobs(db_session)
    assert recovered == 1

    db_session.refresh(claimed)
    assert claimed.status == "queued"
    assert claimed.locked_by is None
    assert claimed.locked_at is None
    assert claimed.attempts == 1  # recovery itself doesn't count as a new attempt
    assert "crashed" in claimed.last_error

    # A different worker can now pick it up and will see attempt 2.
    reclaimed = jobs.claim_job(db_session, "worker-b")
    assert reclaimed.id == job.id
    assert reclaimed.attempts == 2


def test_recover_stale_jobs_fails_permanently_once_attempts_are_exhausted(db_session):
    jobs.enqueue(db_session, "verify_evidence", {"n": 1}, max_attempts=1)
    claimed = jobs.claim_job(db_session, "worker-that-crashes")
    assert claimed.attempts == 1  # already at max_attempts after this one claim

    claimed.lease_expires_at = jobs.utcnow() - datetime.timedelta(seconds=1)
    db_session.commit()

    assert jobs.recover_stale_jobs(db_session) == 1
    db_session.refresh(claimed)
    assert claimed.status == "failed"
    assert claimed.finished_at is not None
    assert jobs.claim_job(db_session, "worker-b") is None  # never reclaimed


def test_concurrent_claims_never_double_process(db_session):
    """Proves SELECT ... FOR UPDATE SKIP LOCKED actually prevents two
    threads from claiming the same job -- requires a real PostgreSQL
    connection (row-level locking; SQLite has none). This test FAILS
    loudly if TEST_DATABASE_URL isn't a Postgres URL -- it does not quietly
    skip, so a local run without Postgres can't be mistaken for a passing
    concurrency guarantee. Run via: TEST_DATABASE_URL=postgresql+psycopg://... pytest server/tests/test_jobs.py
    """
    if db_session.bind.dialect.name != "postgresql":
        pytest.fail(
            "this test requires TEST_DATABASE_URL to point at a real PostgreSQL database -- "
            "SQLite has no row-level locking, so SKIP LOCKED concurrency cannot be demonstrated "
            "against it. See server/README.md for how to run against the dockerized Postgres."
        )

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # NOT str(db_session.bind.url) -- SQLAlchemy's URL.__str__ redacts the
    # password (renders "***") to make it log-safe, which breaks a real
    # reconnect. Read the real credential straight from the env var instead.
    url = db_session.bind.url.render_as_string(hide_password=False)
    # Two independent connections/sessions, like two real worker processes.
    engine_a = create_engine(url)
    engine_b = create_engine(url)
    SessionA = sessionmaker(bind=engine_a)
    SessionB = sessionmaker(bind=engine_b)

    n_jobs = 20
    for i in range(n_jobs):
        jobs.enqueue(db_session, "verify_evidence", {"n": i})

    claimed_ids_a: list[int] = []
    claimed_ids_b: list[int] = []
    barrier = threading.Barrier(2)

    def _drain(session_factory, sink, worker_id):
        barrier.wait()
        s = session_factory()
        try:
            while True:
                job = jobs.claim_job(s, worker_id)
                if job is None:
                    break
                sink.append(job.id)
        finally:
            s.close()

    t_a = threading.Thread(target=_drain, args=(SessionA, claimed_ids_a, "worker-a"))
    t_b = threading.Thread(target=_drain, args=(SessionB, claimed_ids_b, "worker-b"))
    t_a.start()
    t_b.start()
    t_a.join(timeout=30)
    t_b.join(timeout=30)

    engine_a.dispose()
    engine_b.dispose()

    all_claimed = claimed_ids_a + claimed_ids_b
    assert len(all_claimed) == n_jobs, f"expected {n_jobs} claims total, got {len(all_claimed)}"
    assert len(set(all_claimed)) == n_jobs, (
        f"a job was claimed more than once: {sorted(all_claimed)} -- SKIP LOCKED failed to prevent double-claim"
    )
    assert claimed_ids_a, "worker-a claimed nothing -- the test didn't actually exercise concurrency"
    assert claimed_ids_b, "worker-b claimed nothing -- the test didn't actually exercise concurrency"

    remaining = db_session.query(models.Job).filter(models.Job.status == "queued").count()
    assert remaining == 0

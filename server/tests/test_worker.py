"""server/app/worker.py: the job *handlers* and the claim-process-finish
loop, as distinct from server/tests/test_jobs.py (which tests the queue
primitives directly)."""
import hashlib

from server.app import jobs, models, worker
from server.app.storage import LocalDiskStorage


def _make_evidence(db_session, storage_root, data: bytes) -> models.EvidenceItem:
    """Minimal real evidence row + real bytes on disk, enough for
    _verify_evidence to have something genuine to check."""
    user = models.User(role="worker", display_name="W", phone="9000000077")
    db_session.add(user)
    db_session.flush()

    from server.app.pack_import import import_pack
    from pathlib import Path
    pack = import_pack(db_session, Path(__file__).resolve().parents[2] / "packs" / "ae-con-q0602")

    from server.app.worker_tokens import generate_worker_token
    _raw, token_hash = generate_worker_token()
    assessment = models.Assessment(worker_id=user.id, pack_id=pack.id, worker_token_hash=token_hash)
    db_session.add(assessment)
    db_session.flush()
    task = models.AssessmentTask(assessment_id=assessment.id, task_code="T1", budget_bytes=15 * 1024 * 1024)
    db_session.add(task)
    db_session.flush()

    storage = LocalDiskStorage(storage_root)
    key = f"assessments/{assessment.id}/T1/evidence.jpg"
    storage.write(key, data)

    evidence = models.EvidenceItem(
        assessment_task_id=task.id, kind="photo", mime="image/jpeg",
        declared_size_bytes=len(data), storage_key=key, sha256=hashlib.sha256(data).hexdigest(),
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence


def test_verify_evidence_succeeds_when_bytes_match_recorded_hash(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    evidence = _make_evidence(db_session, tmp_path, b"genuine evidence bytes")

    job = jobs.enqueue(db_session, "verify_evidence", {"evidence_item_id": evidence.id})
    claimed = jobs.claim_job(db_session, "test-worker")
    worker.process_job(db_session, claimed)  # must not raise


def test_verify_evidence_fails_when_bytes_were_corrupted_on_disk(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    evidence = _make_evidence(db_session, tmp_path, b"original bytes")

    # simulate corruption: overwrite the stored file after the EvidenceItem's hash was recorded
    storage = LocalDiskStorage(tmp_path)
    storage.write(evidence.storage_key, b"corrupted!!")

    job = jobs.enqueue(db_session, "verify_evidence", {"evidence_item_id": evidence.id})
    claimed = jobs.claim_job(db_session, "test-worker")
    try:
        worker.process_job(db_session, claimed)
        assert False, "expected a mismatch error to be raised"
    except RuntimeError as e:
        assert "mismatch" in str(e)


def test_run_once_marks_job_succeeded_on_a_working_handler(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    evidence = _make_evidence(db_session, tmp_path, b"ok bytes")
    jobs.enqueue(db_session, "verify_evidence", {"evidence_item_id": evidence.id})

    processed = worker.run_once(db_session)
    assert processed is True
    job = db_session.query(models.Job).one()
    assert job.status == "succeeded"


def test_run_once_retries_a_failing_handler_then_gives_up(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    # evidence_item_id that doesn't exist -> handler always raises
    jobs.enqueue(db_session, "verify_evidence", {"evidence_item_id": 999999}, max_attempts=2)

    worker.run_once(db_session)
    job = db_session.query(models.Job).one()
    assert job.status == "queued"
    assert job.attempts == 1
    assert "not found" in job.last_error

    worker.run_once(db_session)
    db_session.refresh(job)
    assert job.status == "failed"
    assert job.attempts == 2


def test_run_once_on_empty_queue_returns_false(db_session):
    assert worker.run_once(db_session) is False


def test_unknown_job_type_fails_cleanly_without_crashing_the_worker(db_session):
    jobs.enqueue(db_session, "some_unknown_job_type", {})
    processed = worker.run_once(db_session)
    assert processed is True
    job = db_session.query(models.Job).one()
    assert job.status in ("queued", "failed")  # retried or given up, never silently dropped
    assert "unknown job type" in job.last_error

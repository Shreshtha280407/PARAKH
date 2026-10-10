"""server/app/worker.py: the job *handlers* and the claim-process-finish
loop, as distinct from server/tests/test_jobs.py (which tests the queue
primitives directly)."""
import hashlib

from server.app import jobs, models, worker
from server.app.storage import LocalDiskStorage


def _make_evidence(db_session, storage_root, data: bytes, kind: str = "photo", mime: str = "image/jpeg") -> models.EvidenceItem:
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

    ext = "jpg" if kind == "photo" else "mp4"
    storage = LocalDiskStorage(storage_root)
    key = f"assessments/{assessment.id}/T1/evidence.{ext}"
    storage.write(key, data)

    evidence = models.EvidenceItem(
        assessment_task_id=task.id, kind=kind, mime=mime,
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


def _synthetic_mp4(duration_seconds: float = 1.0) -> bytes:
    """A genuinely valid, tiny MP4 -- ffmpeg's lavfi test source, no
    external fixture file needed."""
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "synthetic.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration_seconds}:size=64x64:rate=10",
                "-pix_fmt", "yuv420p", str(out),
            ],
            capture_output=True, timeout=30, check=True,
        )
        return out.read_bytes()


def test_generate_thumbnail_extracts_a_real_frame_from_a_real_video(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    video_bytes = _synthetic_mp4()
    evidence = _make_evidence(db_session, tmp_path, video_bytes, kind="video", mime="video/mp4")

    jobs.enqueue(db_session, "generate_thumbnail", {"evidence_item_id": evidence.id})
    claimed = jobs.claim_job(db_session, "test-worker")
    worker.process_job(db_session, claimed)  # must not raise

    assert evidence.thumbnail_status == "completed"
    assert evidence.thumbnail_key is not None
    thumb_path = LocalDiskStorage(tmp_path).path_for(evidence.thumbnail_key)
    assert thumb_path.exists()
    assert thumb_path.read_bytes()[:3] == b"\xff\xd8\xff"  # real JPEG magic bytes


def test_generate_thumbnail_is_not_applicable_for_photos(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    evidence = _make_evidence(db_session, tmp_path, b"photo bytes", kind="photo", mime="image/jpeg")

    jobs.enqueue(db_session, "generate_thumbnail", {"evidence_item_id": evidence.id})
    claimed = jobs.claim_job(db_session, "test-worker")
    worker.process_job(db_session, claimed)

    assert evidence.thumbnail_status == "not_applicable"
    assert evidence.thumbnail_key is None


def test_generate_thumbnail_falls_back_gracefully_when_ffmpeg_is_missing(db_session, tmp_path, monkeypatch):
    """Missing ffmpeg must never crash the worker or fail the job -- it's a
    graceful 'unavailable', not a retryable error (the original evidence
    stays servable regardless)."""
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    evidence = _make_evidence(db_session, tmp_path, _synthetic_mp4(), kind="video", mime="video/mp4")

    def _raise_not_found(*args, **kwargs):
        raise FileNotFoundError("ffmpeg not found")

    monkeypatch.setattr(worker.subprocess, "run", _raise_not_found)

    jobs.enqueue(db_session, "generate_thumbnail", {"evidence_item_id": evidence.id})
    claimed = jobs.claim_job(db_session, "test-worker")
    worker.process_job(db_session, claimed)  # must not raise

    assert evidence.thumbnail_status == "unavailable"
    assert evidence.thumbnail_key is None


def test_generate_thumbnail_falls_back_gracefully_on_a_corrupt_video(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "evidence_dir", tmp_path)
    evidence = _make_evidence(db_session, tmp_path, b"not a real video file", kind="video", mime="video/mp4")

    jobs.enqueue(db_session, "generate_thumbnail", {"evidence_item_id": evidence.id})
    claimed = jobs.claim_job(db_session, "test-worker")
    worker.process_job(db_session, claimed)  # must not raise

    assert evidence.thumbnail_status == "unavailable"

"""Durable background worker.

Run: `python -m app.worker` (inside the Docker image, see server/Dockerfile)
or `python -m server.app.worker` (local dev, from the repo root).

Polls the jobs table (server/app/jobs.py -- PostgreSQL SELECT ... FOR UPDATE
SKIP LOCKED) and processes one job at a time. No Celery/Redis: job volume
at MVP scale (one verification per evidence upload) doesn't need it.
"""
import logging
import os
import signal
import socket
import subprocess
import time

from . import jobs, models
from .config import settings
from .db import SessionLocal
from .storage import LocalDiskStorage

logger = logging.getLogger("parakh.worker")

WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

_running = True


def _handle_stop(signum, frame) -> None:
    global _running
    logger.info("received signal %s, stopping after the current job", signum)
    _running = False


def _verify_evidence(db, job: models.Job) -> None:
    """Re-read the stored evidence bytes and confirm their SHA-256 still
    matches what was recorded at upload-complete time -- catches silent
    disk/volume corruption between upload and later use. Deliberately NOT
    thumbnailing or running any CV/AI inference -- out of scope for P2.1."""
    evidence_id = job.payload["evidence_item_id"]
    evidence = db.get(models.EvidenceItem, evidence_id)
    if evidence is None:
        raise RuntimeError(f"evidence item {evidence_id} not found")
    storage = LocalDiskStorage(settings.evidence_dir)
    if not storage.exists(evidence.storage_key):
        raise RuntimeError(f"evidence item {evidence_id} has no file at {evidence.storage_key}")
    actual = storage.sha256(evidence.storage_key)
    if actual != evidence.sha256:
        raise RuntimeError(
            f"stored evidence {evidence_id} sha256 mismatch: expected {evidence.sha256}, found {actual}"
        )
    logger.info("verified evidence id=%s sha256=%s", evidence_id, actual)


def _generate_thumbnail(db, job: models.Job) -> None:
    """ffmpeg-based video thumbnail extraction -- one frame, written as a
    JPEG alongside the source. Deliberately NOT CV/AI inference: pure frame
    extraction for a UI preview, nothing about the evidence's content is
    analysed (see docs/evidence_quality_result.md). Missing ffmpeg, a
    corrupt video, or an extraction timeout are a graceful "unavailable" --
    never a raised exception -- because the original evidence must always
    stay servable regardless of thumbnail outcome, and these aren't
    transient failures worth retrying."""
    evidence_id = job.payload["evidence_item_id"]
    evidence = db.get(models.EvidenceItem, evidence_id)
    if evidence is None:
        raise RuntimeError(f"evidence item {evidence_id} not found")
    if evidence.kind != "video":
        evidence.thumbnail_status = "not_applicable"
        return

    storage = LocalDiskStorage(settings.evidence_dir)
    source_path = storage.path_for(evidence.storage_key)
    thumbnail_key = evidence.storage_key + ".thumb.jpg"
    thumbnail_path = storage.path_for(thumbnail_key)

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(source_path), "-ss", "00:00:00.5",
                "-frames:v", "1", "-vf", "scale=320:-1", str(thumbnail_path),
            ],
            capture_output=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        evidence.thumbnail_status = "unavailable"
        logger.warning("thumbnail extraction unavailable for evidence id=%s: %s", evidence_id, e)
        return

    if result.returncode != 0 or not thumbnail_path.exists():
        evidence.thumbnail_status = "unavailable"
        logger.warning(
            "thumbnail extraction failed for evidence id=%s: %s",
            evidence_id, result.stderr.decode(errors="replace")[:500],
        )
        return

    evidence.thumbnail_status = "completed"
    evidence.thumbnail_key = thumbnail_key
    logger.info("generated thumbnail for evidence id=%s key=%s", evidence_id, thumbnail_key)


JOB_HANDLERS = {
    "verify_evidence": _verify_evidence,
    "generate_thumbnail": _generate_thumbnail,
}


def process_job(db, job: models.Job) -> None:
    handler = JOB_HANDLERS.get(job.type)
    if handler is None:
        raise ValueError(f"unknown job type: {job.type!r}")
    handler(db, job)


def run_once(db) -> bool:
    """Claim and process at most one job. Returns True if a job was found
    (caller should poll again immediately), False if the queue was empty
    (caller should back off)."""
    job = jobs.claim_job(db, WORKER_ID)
    if job is None:
        return False
    try:
        process_job(db, job)
        jobs.mark_succeeded(db, job)
    except Exception as e:  # noqa: BLE001 -- any handler failure must retry/fail the job, not crash the worker
        jobs.mark_failed(db, job, repr(e))
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    logger.info("worker starting id=%s poll_interval=%ss", WORKER_ID, settings.job_poll_interval_seconds)
    while _running:
        db = SessionLocal()
        try:
            recovered = jobs.recover_stale_jobs(db)
            if recovered:
                logger.warning("recovered %s stale job(s) from a crashed worker", recovered)
            processed = run_once(db)
        finally:
            db.close()
        if not processed:
            time.sleep(settings.job_poll_interval_seconds)
    logger.info("worker stopped id=%s", WORKER_ID)


if __name__ == "__main__":
    main()

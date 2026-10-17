"""Durable background worker.

Run: `python -m app.worker` (inside the Docker image, see server/Dockerfile)
or `python -m server.app.worker` (local dev, from the repo root).

Polls the jobs table (server/app/jobs.py -- PostgreSQL SELECT ... FOR UPDATE
SKIP LOCKED) and processes one job at a time. No Celery/Redis: job volume
at MVP scale (one verification per evidence upload) doesn't need it.
"""
import json
import logging
import os
import pathlib
import signal
import socket
import subprocess
import tempfile
import time

from . import jobs, models
from .config import settings
from .db import SessionLocal
from .storage import get_storage

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
    storage = get_storage()
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

    storage = get_storage()
    thumbnail_key = evidence.storage_key + ".thumb.jpg"

    # ffmpeg is a subprocess taking file PATHS, so cloud mode has to
    # materialise the source locally and then upload the frame it writes.
    # storage.local_path() is a no-op passthrough on local disk (the file
    # is already there) and a bounded temp-file download on S3 that is
    # always removed on the way out -- Railway's container disk is small,
    # and only one evidence item is ever resident at a time.
    with tempfile.TemporaryDirectory(prefix="parakh-thumb-") as scratch:
        thumbnail_path = pathlib.Path(scratch) / "thumb.jpg"
        try:
            with storage.local_path(evidence.storage_key) as source_path:
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

        # Into the private bucket (or the private volume) under the key the
        # evidence router will serve it from.
        storage.write(thumbnail_key, thumbnail_path.read_bytes())

    evidence.thumbnail_status = "completed"
    evidence.thumbnail_key = thumbnail_key
    logger.info("generated thumbnail for evidence id=%s key=%s", evidence_id, thumbnail_key)


def _extract_metadata(db, job: models.Job) -> None:
    """Real server-side width/height/duration extraction via ffprobe -- P6
    requirement B: "Persist duration, dimensions, MIME, byte size and job
    outcome," never trusting the client's (or the P5 manifest's) declared
    values alone. Works for both photos and videos: ffprobe reports a
    static image's dimensions on its single implicit video stream too, with
    no 'duration' field, which is handled below (duration stays None for
    photos). A failed/unavailable extraction is handled exactly like a
    failed thumbnail job (section B.4 of the spec): the evidence item stays
    fully servable, metadata_status just records 'unavailable' rather than
    raising -- this is never a retryable integrity failure, unlike
    _verify_evidence's hash check."""
    evidence_id = job.payload["evidence_item_id"]
    evidence = db.get(models.EvidenceItem, evidence_id)
    if evidence is None:
        raise RuntimeError(f"evidence item {evidence_id} not found")

    storage = get_storage()

    try:
        with storage.local_path(evidence.storage_key) as source_path:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-print_format", "json",
                    "-show_entries", "stream=width,height,duration:format=duration",
                    str(source_path),
                ],
                capture_output=True, timeout=30,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        evidence.metadata_status = "unavailable"
        logger.warning("metadata extraction unavailable for evidence id=%s: %s", evidence_id, e)
        return

    if result.returncode != 0:
        evidence.metadata_status = "unavailable"
        logger.warning(
            "metadata extraction failed for evidence id=%s: %s",
            evidence_id, result.stderr.decode(errors="replace")[:500],
        )
        return

    try:
        probe = json.loads(result.stdout)
        streams = probe.get("streams") or []
        video_stream = next((s for s in streams if "width" in s and "height" in s), None)
        if video_stream is None:
            raise ValueError("no stream with width/height in ffprobe output")
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        duration_str = video_stream.get("duration") or (probe.get("format") or {}).get("duration")
        duration_ms = int(round(float(duration_str) * 1000)) if duration_str else None
    except (ValueError, KeyError, TypeError) as e:
        evidence.metadata_status = "unavailable"
        logger.warning("metadata extraction produced unusable output for evidence id=%s: %s", evidence_id, e)
        return

    evidence.width_px = width
    evidence.height_px = height
    evidence.duration_ms = duration_ms if evidence.kind == "video" else None
    evidence.metadata_status = "completed"
    logger.info(
        "extracted metadata for evidence id=%s width=%s height=%s duration_ms=%s",
        evidence_id, width, height, evidence.duration_ms,
    )


JOB_HANDLERS = {
    "verify_evidence": _verify_evidence,
    "generate_thumbnail": _generate_thumbnail,
    "extract_metadata": _extract_metadata,
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
    logger.info("worker starting id=%s poll_interval=%ss source_sha=%s", WORKER_ID, settings.job_poll_interval_seconds, settings.source_sha)
    last_heartbeat = 0.0
    while _running:
        db = SessionLocal()
        try:
            if time.monotonic() - last_heartbeat >= 30:
                heartbeat = db.get(models.WorkerHeartbeat, "worker")
                if heartbeat is None:
                    heartbeat = models.WorkerHeartbeat(service="worker", source_sha=settings.source_sha, seen_at=models.utcnow())
                    db.add(heartbeat)
                else:
                    heartbeat.source_sha = settings.source_sha
                    heartbeat.seen_at = models.utcnow()
                db.commit()
                last_heartbeat = time.monotonic()
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

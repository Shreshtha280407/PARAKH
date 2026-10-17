"""P6 sync bootstrap: lets a worker's phone establish a server-side worker identity the
FIRST time it ever syncs, without any password/OTP/pre-provisioning. See
docs/worker_capability_tokens.md for why the worker app has no login at all -- this endpoint
extends that same "no account, no credential" design to identity creation itself: the
phone's own locally-generated device_worker_id (never a server secret) is the sole key.

Idempotent by construction: the same device_worker_id always resolves to the same worker
User row, created on first call rather than requiring any admin/seed step.
"""
import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..abuse import enrollment_limits, enrollment_capacity

router = APIRouter(prefix="/workers", tags=["workers"])


@router.post("/register", response_model=schemas.WorkerRegisterOut)
def register_worker(
    body: schemas.WorkerRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> schemas.WorkerRegisterOut:
    enrollment_limits(db, request)
    existing = db.query(models.User).filter_by(
        device_worker_id=body.device_worker_id, role="worker",
    ).one_or_none()
    if existing is not None:
        return schemas.WorkerRegisterOut(worker_id=existing.id)
    enrollment_capacity(db)
    if db.query(models.User).filter_by(role="worker").count() >= 300:
        raise HTTPException(503, "candidate registration capacity reached")

    # A device_worker_id could, in principle, collide with an already-used phone/email if
    # the client ever reused one of those fields here -- it can't (schema only accepts
    # device_worker_id), but the unique constraint on phone/email is unaffected either way
    # since this row sets neither.
    worker = models.User(role="worker", display_name=body.display_name, device_worker_id=body.device_worker_id)
    db.add(worker)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Lost the race against a concurrent registration call for the exact same device --
        # the other call's row now exists; return it rather than erroring.
        existing = db.query(models.User).filter_by(
            device_worker_id=body.device_worker_id, role="worker",
        ).one_or_none()
        if existing is not None:
            return schemas.WorkerRegisterOut(worker_id=existing.id)
        raise HTTPException(status.HTTP_409_CONFLICT, "worker registration failed") from None
    db.refresh(worker)
    return schemas.WorkerRegisterOut(worker_id=worker.id)


@router.post("/enroll", response_model=schemas.AssessmentCreatedOut)
def enroll_candidate(body: schemas.CandidateEnrollmentIn, request: Request, db: Session = Depends(get_db)):
    """One atomic, retryable offline bootstrap. A random device secret, never the
    four-digit PIN, authorizes retries and protects identity from replacement.
    Legacy bootstrap remains available but cannot publish historical records.
    """
    enrollment_limits(db, request)
    if db.bind.dialect.name == "postgresql":
        # Serialize anonymous creation/ceiling checks, including legacy creation.
        db.execute(text("SELECT pg_advisory_xact_lock(72026017)"))
    from .assessments import _new_assessment, _created_out
    from ..worker_tokens import hash_worker_token

    secret_hash = hashlib.sha256(body.enrollment_secret.encode()).hexdigest()
    worker = db.query(models.User).filter_by(device_worker_id=body.device_worker_id).with_for_update().one_or_none()
    if worker:
        if not worker.enrollment_secret_hash or not hmac.compare_digest(worker.enrollment_secret_hash, secret_hash):
            raise HTTPException(409, "device identity is already enrolled")
        if worker.display_name != body.full_name or worker.candidate_phone != body.phone:
            raise HTTPException(409, "enrollment identity differs from original registration")
    else:
        worker = models.User(role="worker", display_name=body.full_name, candidate_phone=body.phone,
                             device_worker_id=body.device_worker_id, enrollment_secret_hash=secret_hash)
        db.add(worker)
        db.flush()
    assessment = db.query(models.Assessment).filter_by(enrollment_id=body.client_assessment_id).one_or_none()
    # Stable retry capability derived from a random 256-bit device secret; no
    # server plaintext token store and no dependency on a rotating JWT key.
    raw_token = hmac.new(bytes.fromhex(body.enrollment_secret),
                         ("parakh-assessment-v1:" + body.client_assessment_id).encode(), hashlib.sha256).hexdigest()
    if assessment:
        if assessment.worker_id != worker.id or assessment.worker_token_hash != hash_worker_token(raw_token):
            raise HTTPException(409, "assessment enrollment conflict")
        if assessment.public_name_consent != body.public_name_consent:
            raise HTTPException(409, "consent differs from original enrollment")
        return _created_out(assessment, raw_token)
    enrollment_capacity(db)
    pack = db.query(models.QualificationPack).filter_by(qp_code=body.qp_code, qp_version=body.qp_version).order_by(
        models.QualificationPack.id.desc()).first()
    if not pack:
        raise HTTPException(404, "qualification pack not installed")
    if db.query(models.Assessment).filter_by(worker_id=worker.id).count() >= 5:
        raise HTTPException(429, "candidate assessment limit reached")
    assessment, _ = _new_assessment(db, worker.id, pack.id, None, "worker")
    assessment.worker_token_hash = hash_worker_token(raw_token)
    assessment.enrollment_id = body.client_assessment_id
    assessment.provenance = "candidate-v1"
    assessment.public_name_consent = body.public_name_consent
    assessment.consent_recorded_at = models.utcnow()
    db.add(models.AuditLog(assessment_id=assessment.id, actor_role="worker", action="candidate_enrolled",
                           details={"consent_version": body.consent_version, "public_name_consent": body.public_name_consent}))
    db.commit()
    db.refresh(assessment)
    return _created_out(assessment, raw_token)

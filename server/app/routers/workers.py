"""P6 sync bootstrap: lets a worker's phone establish a server-side worker identity the
FIRST time it ever syncs, without any password/OTP/pre-provisioning. See
docs/worker_capability_tokens.md for why the worker app has no login at all -- this endpoint
extends that same "no account, no credential" design to identity creation itself: the
phone's own locally-generated device_worker_id (never a server secret) is the sole key.

Idempotent by construction: the same device_worker_id always resolves to the same worker
User row, created on first call rather than requiring any admin/seed step.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/workers", tags=["workers"])


@router.post("/register", response_model=schemas.WorkerRegisterOut)
def register_worker(
    body: schemas.WorkerRegisterRequest,
    db: Session = Depends(get_db),
) -> schemas.WorkerRegisterOut:
    existing = db.query(models.User).filter_by(
        device_worker_id=body.device_worker_id, role="worker",
    ).one_or_none()
    if existing is not None:
        return schemas.WorkerRegisterOut(worker_id=existing.id)

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

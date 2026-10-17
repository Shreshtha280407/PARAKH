from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import settings
from .. import models
from ..schemas import HealthOut
from . import uploads

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unreachable"

    # The ACTIVE backend (LocalDiskStorage or S3Storage), not a hardcoded
    # local directory -- on Railway + Neon Object Storage, a writable
    # container filesystem says nothing about whether the private bucket
    # is reachable, and /health returning "ok" while evidence uploads were
    # silently failing is exactly the false pass this must not give.
    storage_status = "ok" if uploads._storage.probe() else "unreachable"
    heartbeat = db.get(models.WorkerHeartbeat, "worker") if db_status == "ok" else None
    worker_sha = None
    if heartbeat:
        from datetime import timezone
        seen = heartbeat.seen_at.replace(tzinfo=timezone.utc) if heartbeat.seen_at.tzinfo is None else heartbeat.seen_at
        if (models.utcnow() - seen).total_seconds() < 120:
            worker_sha = heartbeat.source_sha

    return HealthOut(status="ok" if db_status == storage_status == "ok" else "degraded",
                     database=db_status, storage=storage_status, source_sha=settings.source_sha, worker_source_sha=worker_sha)

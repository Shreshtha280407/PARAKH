from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unreachable"

    try:
        settings.evidence_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.evidence_dir / ".health_probe"
        probe.write_text("ok")
        probe.unlink()
        storage_status = "ok"
    except OSError:
        storage_status = "unreachable"

    return HealthOut(status="ok", database=db_status, storage=storage_status)

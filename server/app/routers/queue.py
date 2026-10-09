from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_assessor
from ..db import get_db

router = APIRouter(tags=["queue"])


@router.get("/queue", response_model=list[schemas.QueueItemOut])
def assessor_queue(
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_assessor),
) -> list[schemas.QueueItemOut]:
    """Submitted (or further-along) assessments waiting on an assessor,
    oldest first. Assessor/admin only -- see server/app/auth.py. No scoring
    here yet -- that's P6/P7."""
    rows = (
        db.query(models.Assessment, models.User, models.QualificationPack)
        .join(models.User, models.Assessment.worker_id == models.User.id)
        .join(models.QualificationPack, models.Assessment.pack_id == models.QualificationPack.id)
        .filter(models.Assessment.status != "draft")
        .order_by(models.Assessment.created_at)
        .all()
    )
    return [
        schemas.QueueItemOut(
            id=a.id,
            worker_id=a.worker_id,
            worker_name=u.display_name,
            pack_code=p.qp_code,
            status=a.status,
            created_at=a.created_at,
        )
        for a, u, p in rows
    ]

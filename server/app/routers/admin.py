from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_admin
from ..db import get_db
from ..pack_import import REPO_ROOT, import_pack_cli

router = APIRouter(prefix="/admin", tags=["admin"])


class PackImportRequest(BaseModel):
    pack_dir: str = "packs/ae-con-q0602"


@router.post("/packs/import", response_model=schemas.PackImportOut)
def import_pack_endpoint(
    body: PackImportRequest,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_admin),
) -> schemas.PackImportOut:
    """Admin-only. Re-validates with tools/pack_validate.py and
    tools/audit_qp_traceability.py before importing -- see pack_import.py."""
    pack_dir = (REPO_ROOT / body.pack_dir).resolve()
    if REPO_ROOT.resolve() not in pack_dir.parents:
        raise HTTPException(400, "pack_dir must be inside the repository")
    if not pack_dir.exists():
        raise HTTPException(404, f"pack directory not found: {pack_dir}")
    try:
        pack = import_pack_cli(pack_dir, db)
    except RuntimeError as e:
        raise HTTPException(422, str(e)) from e

    nos_count = db.query(models.NOS).filter_by(pack_id=pack.id).count()
    pc_count = db.query(models.PerformanceCriterion).join(models.NOS).filter(models.NOS.pack_id == pack.id).count()
    task_count = db.query(models.TaskTemplate).filter_by(pack_id=pack.id).count()
    return schemas.PackImportOut(
        id=pack.id, qp_code=pack.qp_code, qp_version=pack.qp_version, pack_version=pack.pack_version,
        nos_count=nos_count, pc_count=pc_count, task_count=task_count,
    )

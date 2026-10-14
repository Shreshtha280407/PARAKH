"""P6 sync bootstrap: the phone only knows its pinned QP code/version (packs/ae-con-q0602's
qp.json content, baked into the app, never a server-assigned integer) -- this lets it resolve
that to the server's qualification_packs.id before it can call POST /assessments. Read-only,
public (pack metadata is not sensitive -- the same QP code/version/rubric is already bundled
into every worker's app installation)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/packs", tags=["packs"])


@router.get("/by-code", response_model=schemas.PackLookupOut)
def lookup_pack_by_code(
    qp_code: str,
    qp_version: str,
    db: Session = Depends(get_db),
) -> schemas.PackLookupOut:
    pack = (
        db.query(models.QualificationPack)
        .filter_by(qp_code=qp_code, qp_version=qp_version)
        .order_by(models.QualificationPack.imported_at.desc())
        .first()
    )
    if pack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no imported pack for qp_code='{qp_code}' qp_version='{qp_version}'")
    return schemas.PackLookupOut(
        pack_id=pack.id, qp_code=pack.qp_code, qp_version=pack.qp_version, pack_version=pack.pack_version,
    )

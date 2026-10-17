"""Public, unauthenticated report verification -- the exact URL the signed
PDF's own QR code points at (see routers/reports.py's sign_off). Exposes
only minimal safe fields: never the worker's name/contact, never raw
evidence, never the full score breakdown. See docs/gates/P7.md section 4.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import models, report_signing, schemas
from ..db import get_db
from ..abuse import source, throttle
from . import uploads

router = APIRouter(tags=["verify"])


@router.get("/verify/{report_id}", response_model=schemas.PublicVerifyOut)
def public_verify(report_id: str, request: Request, db: Session = Depends(get_db)) -> schemas.PublicVerifyOut:
    throttle(db, "verify-global", 300, 60)
    throttle(db, "verify:" + source(request), 60, 60)
    report = db.query(models.SignedReport).filter_by(report_uid=report_id).one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no signed report exists for this report id")

    assessment = db.get(models.Assessment, report.assessment_id)
    pack = db.get(models.QualificationPack, assessment.pack_id)
    pdf_bytes = uploads._storage.read(report.pdf_storage_key)
    valid = report_signing.verify_pdf(pdf_bytes, report.pdf_sha256, report.signature, report.key_id)

    return schemas.PublicVerifyOut(
        report_id=report.report_uid,
        valid=valid,
        qp=f"{pack.qp_code} v{pack.qp_version}",
        recommendation=report.final_recommendation,
        revision_number=report.revision_number,
        sha256=report.pdf_sha256,
        key_id=report.key_id,
        signed_at=report.signed_at,
    )

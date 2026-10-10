"""Tamper-evident competency profile reports -- see docs/gates/P2_2.md
section 4. Generation is a one-time, idempotent snapshot taken once a
decision has been recorded (recommended/needs_reassessment); the public
verify endpoint re-checks the stored hash+signature and returns only a
valid/invalid verdict plus signing metadata -- it never returns the
report content or any evidence.
"""
import io
import json
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import models, report_signing, schemas
from ..auth import require_assessor
from ..db import get_db
from .assessments import _assessor_or_worker_token, _audit
from .scoring import _rubric_rows

router = APIRouter(tags=["reports"])


def _report_snapshot(db: Session, assessment: models.Assessment) -> dict:
    pack = db.get(models.QualificationPack, assessment.pack_id)
    worker = db.get(models.User, assessment.worker_id)
    rows = _rubric_rows(db, assessment.pack_id)
    scores = {
        s.pc_id: s
        for s in db.query(models.AssessmentCriterionScore).filter_by(assessment_id=assessment.id).all()
    }

    criteria = []
    overall_awarded = Decimal("0.00")
    overall_possible = Decimal("0.00")
    for item, pc, nos in rows:
        overall_possible += item.marks
        score = scores.get(pc.id)
        awarded = score.marks_awarded if score and score.scored_at is not None else Decimal("0.00")
        overall_awarded += awarded
        criteria.append({
            "pc_full_id": pc.full_id,
            "nos_code": nos.code,
            "max_marks": str(item.marks),
            "score_level": score.score_level if score else None,
            "evidence_status": score.evidence_status if score else None,
            "assessor_comment": score.assessor_comment if score else None,
            "marks_awarded": str(awarded),
        })

    overall_percent = float(overall_awarded / overall_possible * 100) if overall_possible else 0.0
    return {
        "assessment_id": assessment.id,
        "worker_name": worker.display_name,
        "qp_code": pack.qp_code,
        "qp_name": pack.qp_name,
        "qp_version": pack.qp_version,
        "status": assessment.status,
        "decision": assessment.decision,
        "decision_notes": assessment.decision_notes,
        "decided_at": assessment.decided_at.isoformat() if assessment.decided_at else None,
        "overall_marks_awarded": str(overall_awarded),
        "overall_marks_possible": str(overall_possible),
        "overall_percent": round(overall_percent, 2),
        "minimum_aggregate_passing_percent": pack.minimum_aggregate_passing_percent,
        "criteria": criteria,
        "disclaimer": schemas.COMPETENCY_PROFILE_DISCLAIMER + " This is not an official NCVET/MSDE certificate.",
    }


def _report_out(report: models.SignedReport) -> schemas.SignedReportOut:
    return schemas.SignedReportOut(
        assessment_id=report.assessment_id, sha256=report.sha256, signature=report.signature,
        key_id=report.key_id, signed_at=report.signed_at,
    )


def _render_pdf(data: dict, report: models.SignedReport) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    def _new_page_if_needed(y: float) -> float:
        if y < 70:
            c.showPage()
            return height - 50
        return y

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "KaushalPramaan -- NSQF-Aligned Competency Profile")
    y -= 18
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, y, "Decision support and an assessor recommendation only -- NOT an official NCVET/MSDE certificate.")
    y -= 26
    c.setFont("Helvetica", 10)
    for line in [
        f"Assessment: #{data['assessment_id']}    Worker: {data['worker_name']}",
        f"Qualification Pack: {data['qp_code']} -- {data['qp_name']} (v{data['qp_version']})",
        f"Decision: {data['decision'] or 'pending'}" + (f"    Notes: {data['decision_notes']}" if data['decision_notes'] else ""),
        f"Overall: {data['overall_marks_awarded']} / {data['overall_marks_possible']} marks "
        f"({data['overall_percent']}%, minimum passing {data['minimum_aggregate_passing_percent']}%)",
    ]:
        c.drawString(50, y, line)
        y -= 15
    y -= 10

    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Performance Criteria")
    y -= 14
    c.setFont("Helvetica", 7.5)
    for item in data["criteria"]:
        y = _new_page_if_needed(y)
        line = (
            f"{item['pc_full_id']}  level={item['score_level']}  status={item['evidence_status']}  "
            f"marks={item['marks_awarded']}/{item['max_marks']}"
        )
        c.drawString(50, y, line)
        y -= 11

    y = _new_page_if_needed(y - 10)
    c.setFont("Helvetica", 6.5)
    c.drawString(50, y, f"SHA-256: {report.sha256}")
    y -= 9
    c.drawString(50, y, f"Ed25519 signature (key {report.key_id}): {report.signature}")
    c.showPage()
    c.save()
    return buf.getvalue()


@router.post("/assessments/{assessment_id}/report", response_model=schemas.SignedReportOut, status_code=201)
def generate_report(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.SignedReportOut:
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    existing = db.query(models.SignedReport).filter_by(assessment_id=assessment_id).one_or_none()
    if existing is not None:
        return _report_out(existing)

    if assessment.status not in ("recommended", "needs_reassessment"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot generate a report: assessment is '{assessment.status}', no decision recorded yet",
        )

    snapshot = _report_snapshot(db, assessment)
    canonical, sha256_hex, signature_hex, key_id = report_signing.sign_report(snapshot)
    report = models.SignedReport(
        assessment_id=assessment_id, canonical_json=canonical, sha256=sha256_hex,
        signature=signature_hex, key_id=key_id,
    )
    db.add(report)
    _audit(db, assessment_id, actor_user_id=user.id, actor_role=user.role, action="report_generated")
    db.commit()
    db.refresh(report)
    return _report_out(report)


@router.get("/assessments/{assessment_id}/report")
def download_report(
    assessment_id: int,
    format: Literal["json", "pdf"] = "json",
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> Response:
    """Protected -- same dual auth as GET /assessments/{id} (assessor/admin
    JWT, or this assessment's own worker token)."""
    report = db.query(models.SignedReport).filter_by(assessment_id=assessment_id).one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no signed report exists yet for this assessment")

    if format == "json":
        return Response(content=report.canonical_json, media_type="application/json")

    pdf_bytes = _render_pdf(json.loads(report.canonical_json), report)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="assessment-{assessment_id}-report.pdf"'},
    )


@router.get("/reports/{assessment_id}/verify", response_model=schemas.ReportVerifyOut)
def verify_report(assessment_id: int, db: Session = Depends(get_db)) -> schemas.ReportVerifyOut:
    """Public, unauthenticated -- the whole point of signing is that anyone
    can check a report's authenticity without needing credentials. Returns
    only a valid/invalid verdict and signing metadata; never the report
    content, scores, or any evidence."""
    report = db.query(models.SignedReport).filter_by(assessment_id=assessment_id).one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no signed report exists for this assessment")

    valid = report_signing.verify(report.canonical_json, report.sha256, report.signature)
    return schemas.ReportVerifyOut(
        assessment_id=assessment_id, valid=valid, key_id=report.key_id, signed_at=report.signed_at,
    )

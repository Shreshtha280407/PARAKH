"""Tamper-evident signed reports -- see docs/gates/P7.md sections 4-5.

P7 redesign from P2.2: the PDF is rendered ONCE (with no hash/signature
field inside it, avoiding a circular self-reference), hashed, Ed25519-signed
over that hash, and stored IMMUTABLY -- a later download serves the exact
same stored bytes, never a re-render. Signing requires password re-entry
(POST .../sign-off), validated server-side against the AUTHENTICATED
assessor's own stored hash -- never trusted from the frontend alone, and the
password itself is never logged or stored. `canonical_json` remains an
informational, UNSIGNED snapshot for the format=json download only.
"""
import datetime
import io
import secrets
from typing import Literal

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, report_signing, schemas
from ..auth import require_assessor, verify_password
from ..config import settings
from ..db import get_db
from ..reviewer_identity import identity
from . import uploads
from .assessments import _assessor_or_worker_token, _audit
from .scoring import _rubric_rows, get_computed_outcome

router = APIRouter(tags=["reports"])

REPORT_DISCLAIMER = "Assessor recommendation — not an official certificate."


def _report_snapshot(
    db: Session,
    assessment: models.Assessment,
    computed,
    final_recommendation: str,
    override_reason: str | None,
    assessor: models.User,
    report_uid: str,
    verify_url: str,
) -> dict:
    pack = db.get(models.QualificationPack, assessment.pack_id)
    worker = db.get(models.User, assessment.worker_id)
    rows = _rubric_rows(db, assessment.pack_id)
    scores = {
        s.pc_id: s
        for s in db.query(models.AssessmentCriterionScore).filter_by(assessment_id=assessment.id).all()
    }
    rubric_version = rows[0][0].rubric_version if rows else "unknown"

    tasks_by_pc_id: dict[int, str] = {}
    task_rows = db.query(models.AssessmentTask).filter_by(assessment_id=assessment.id).all()
    task_by_code = {t.task_code: t for t in task_rows}

    criteria_by_task: dict[str, list[dict]] = {}
    for item, pc, nos in rows:
        task_code = nos.task_code or "?"
        score = scores.get(pc.id)
        criteria_by_task.setdefault(task_code, []).append({
            "pc_full_id": pc.full_id,
            "nos_code": nos.code,
            "critical": item.critical,
            "max_marks": str(item.marks),
            "score_level": score.score_level if score else None,
            "evidence_status": score.evidence_status if score else None,
            "assessor_comment": score.assessor_comment if score else None,
            "marks_awarded": str(score.marks_awarded) if score and score.scored_at is not None else "0.00",
            "revision_number": score.revision_number if score else None,
        })

    evidence_rows = []
    for t in task_rows:
        for e in db.query(models.EvidenceItem).filter_by(assessment_task_id=t.id).order_by(models.EvidenceItem.id).all():
            evidence_rows.append({
                "task_code": t.task_code, "kind": e.kind, "sha256": e.sha256,
                "declared_size_bytes": e.declared_size_bytes,
                "device_captured_at": e.device_captured_at.isoformat() if e.device_captured_at else None,
                "received_at": e.created_at.isoformat(),
            })

    revisions = (
        db.query(models.AssessmentRevision)
        .filter_by(assessment_id=assessment.id)
        .order_by(models.AssessmentRevision.revision_number)
        .all()
    )
    reassessment_requests = (
        db.query(models.ReassessmentRequest)
        .filter_by(assessment_id=assessment.id)
        .order_by(models.ReassessmentRequest.id)
        .all()
    )
    revision_history = [
        {
            "revision_number": r.revision_number, "status": r.status,
            "reopened_task_codes": r.reopened_task_codes, "created_at": r.created_at.isoformat(),
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        }
        for r in revisions
    ]
    reassessment_history = [
        {
            "task_codes": rr.task_codes, "reason": rr.reason,
            "capture_instructions": rr.capture_instructions, "requested_at": rr.requested_at.isoformat(),
            "status": rr.status,
        }
        for rr in reassessment_requests
    ]

    declaration_recorded = assessment.declared_match_result is not None
    declaration = {
        "recorded": declaration_recorded,
        "match_result": assessment.declared_match_result,
        "coverage_percent": (
            round(float(assessment.declared_coverage_fraction) * 100, 1)
            if assessment.declared_coverage_fraction is not None else None
        ),
        "gap_task_codes": assessment.declared_gap_task_codes,
        "match_reasons": assessment.declared_match_reasons,
    }

    return {
        "report_uid": report_uid,
        "assessment_id": assessment.id,
        "revision_number": assessment.revision_number,
        "verify_url": verify_url,
        "worker_name": worker.display_name,
        "qp_code": pack.qp_code,
        "qp_name": pack.qp_name,
        "qp_version": pack.qp_version,
        "rubric_version": rubric_version,
        "declaration": declaration,
        "nos_breakdown": [
            {
                "nos_code": n.nos_code, "nos_title": n.nos_title,
                "marks_awarded": str(n.marks_awarded), "marks_possible": str(n.marks_possible),
                "percent": n.percent, "meets_threshold": n.meets_threshold,
                "critical_violation": n.critical_violation,
                "has_insufficient_evidence": n.has_insufficient_evidence, "competent": n.competent,
            }
            for n in computed.nos_results
        ],
        "criteria_by_task": criteria_by_task,
        "computed_recommendation": computed.outcome,
        "final_recommendation": final_recommendation,
        "override_reason": override_reason,
        "assessor_remarks": assessment.decision_notes,
        "evidence": evidence_rows,
        "revision_history": revision_history,
        "reassessment_history": reassessment_history,
        "assessor_name": assessor.display_name,
        "reviewer_identity": identity(assessor),
        "signed_at": assessment.decided_at.isoformat() if assessment.decided_at else None,
        "minimum_aggregate_passing_percent": pack.minimum_aggregate_passing_percent,
        "disclaimer": REPORT_DISCLAIMER,
    }


def _qr_cells(url: str) -> list[list[bool]]:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    return [[bool(c) for c in row] for row in qr.get_matrix()]


def _draw_qr(c, cells: list[list[bool]], x: float, y: float, size: float) -> None:
    n = len(cells)
    if n == 0:
        return
    cell = size / n
    c.setFillColorRGB(0, 0, 0)
    for row_idx, row in enumerate(cells):
        for col_idx, filled in enumerate(row):
            if filled:
                c.rect(x + col_idx * cell, y + (n - 1 - row_idx) * cell, cell, cell, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)


def _render_pdf(data: dict) -> bytes:
    """Renders the final PDF bytes with NOTHING hash/signature-related in
    them -- those are computed from these exact bytes afterward (see
    sign_off below) and are never fed back into a re-render."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    # pageCompression=0: keeps the PDF's content streams uncompressed. Not
    # required for signing/verification (which hash the final bytes exactly
    # as produced either way), but keeps the rendered report plain-text
    # greppable -- useful for debugging/audit, and lets tests assert on
    # real PDF content instead of only magic bytes.
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=0)
    width, height = A4
    margin = 50

    def _new_page_if_needed(y: float, needed: float = 70) -> float:
        if y < needed:
            c.showPage()
            return height - margin
        return y

    def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
        """Greedy word-wrap against the real rendered width of this exact
        font/size -- this report is the evidentiary record of what an
        assessor actually wrote (override reasons, PC remarks); it must
        never silently drop characters to fit a fixed-length slice."""
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if stringWidth(candidate, font, size) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _draw_wrapped(x: float, y: float, text: str, font: str, size: float, max_width: float, line_height: float) -> float:
        c.setFont(font, size)
        for line in _wrap(text, font, size, max_width):
            y = _new_page_if_needed(y)
            c.drawString(x, y, line)
            y -= line_height
        return y

    y = height - margin
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, y, "KaushalPramaan -- NSQF-Aligned Competency Profile")
    y -= 16
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, data["disclaimer"])
    y -= 18

    c.setFont("Helvetica", 9)
    for line in [
        f"Report ID: {data['report_uid']}    Assessment ID: {data['assessment_id']}    Revision: v{data['revision_number']}",
        f"Worker: {data['worker_name']}",
        f"Qualification Pack: {data['qp_code']} -- {data['qp_name']} (v{data['qp_version']}), rubric {data['rubric_version']}",
    ]:
        c.drawString(margin, y, line)
        y -= 13
    y -= 6

    decl = data["declaration"]
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Declaration & QP match")
    y -= 13
    c.setFont("Helvetica", 8.5)
    if not decl["recorded"]:
        c.drawString(margin, y, "Not recorded.")
        y -= 11
    else:
        c.drawString(
            margin, y,
            f"Match: {decl['match_result']}    Coverage: {decl['coverage_percent']}%    "
            f"Gaps: {', '.join(decl['gap_task_codes'] or []) or 'none'}",
        )
        y -= 11
        if decl["match_reasons"]:
            for reason in decl["match_reasons"]:
                y = _new_page_if_needed(y)
                c.drawString(margin + 10, y, f"- {reason}")
                y -= 10
        else:
            c.drawString(margin, y, "Match reasoning: not recorded.")
            y -= 11
    y -= 8

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "NOS-wise competency profile")
    y -= 13
    c.setFont("Helvetica", 8)
    for n in data["nos_breakdown"]:
        y = _new_page_if_needed(y)
        flags = []
        if n["critical_violation"]:
            flags.append("CRITICAL PC BELOW LEVEL 2")
        if n["has_insufficient_evidence"]:
            flags.append("insufficient evidence")
        flag_text = f" [{', '.join(flags)}]" if flags else ""
        c.drawString(
            margin, y,
            f"{n['nos_code']} ({n['nos_title'][:50]}): {n['marks_awarded']}/{n['marks_possible']} "
            f"({n['percent']}%) {'COMPETENT' if n['competent'] else 'gap'}{flag_text}",
        )
        y -= 10
    y -= 8

    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Per-task performance criteria")
    y -= 13
    for task_code in sorted(data["criteria_by_task"]):
        y = _new_page_if_needed(y)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(margin, y, task_code)
        y -= 10
        c.setFont("Helvetica", 7.5)
        for pc in data["criteria_by_task"][task_code]:
            y = _new_page_if_needed(y)
            crit = " [CRITICAL]" if pc["critical"] else ""
            rev = f" (v{pc['revision_number']})" if pc["revision_number"] else ""
            c.drawString(
                margin + 8, y,
                f"{pc['pc_full_id']}{crit}  level={pc['score_level']}  status={pc['evidence_status']}  "
                f"marks={pc['marks_awarded']}/{pc['max_marks']}{rev}",
            )
            y -= 9
            if pc["assessor_comment"]:
                y = _draw_wrapped(
                    margin + 14, y, f"remark: {pc['assessor_comment']}",
                    "Helvetica", 7.5, width - 2 * margin - 14, 9,
                )
    y -= 8

    y = _new_page_if_needed(y, 100)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Recommendation")
    y -= 13
    c.setFont("Helvetica", 8.5)
    c.drawString(margin, y, f"Computed: {data['computed_recommendation']}    Final (assessor): {data['final_recommendation']}")
    y -= 11
    if data["override_reason"]:
        y = _draw_wrapped(margin, y, f"Override reason: {data['override_reason']}", "Helvetica", 8.5, width - 2 * margin, 11)
    if data["assessor_remarks"]:
        y = _draw_wrapped(margin, y, f"Assessor remarks: {data['assessor_remarks']}", "Helvetica", 8.5, width - 2 * margin, 11)
    y -= 6

    if data["revision_history"] or data["reassessment_history"]:
        y = _new_page_if_needed(y)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, "Reassessment / revision provenance")
        y -= 13
        c.setFont("Helvetica", 7.5)
        for rh in data["revision_history"]:
            y = _new_page_if_needed(y)
            tasks = ", ".join(rh["reopened_task_codes"]) if rh["reopened_task_codes"] else "all tasks"
            c.drawString(margin, y, f"v{rh['revision_number']} [{rh['status']}] -- tasks: {tasks}")
            y -= 9
        for rr in data["reassessment_history"]:
            y = _draw_wrapped(
                margin, y, f"Requested {', '.join(rr['task_codes'])}: {rr['reason']}",
                "Helvetica", 7.5, width - 2 * margin, 9,
            )
        y -= 6

    y = _new_page_if_needed(y, 150)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Evidence")
    y -= 13
    c.setFont("Helvetica", 7)
    for ev in data["evidence"]:
        y = _new_page_if_needed(y)
        captured = ev["device_captured_at"] or "not recorded (device-reported)"
        # The full hash, never truncated -- this IS the integrity record a
        # verifier checks a real evidence file against; a shortened hash
        # would weaken exactly the guarantee this report line exists for.
        c.drawString(margin, y, f"{ev['task_code']} {ev['kind']} sha256={ev['sha256']}")
        y -= 9
        y = _new_page_if_needed(y)
        c.drawString(margin + 8, y, f"bytes={ev['declared_size_bytes']} captured={captured} received={ev['received_at']}")
        y -= 9

    y = _new_page_if_needed(y, 150)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Assessor sign-off")
    y -= 13
    c.setFont("Helvetica", 8.5)
    c.drawString(margin, y, f"Assessor: {data['assessor_name']}    Signing date: {datetime.datetime.now(datetime.timezone.utc).date().isoformat()}")
    y -= 12
    reviewer = data.get("reviewer_identity", {})
    c.drawString(margin, y, f"Email ownership verified: {reviewer.get('email_verified', False)}; name is self-declared.")
    y -= 12
    c.drawString(margin, y, "Server Ed25519 signature proves document integrity, not personal identity.")
    y -= 12
    y = _draw_wrapped(margin, y, f"Reviewer email: {reviewer.get('email') or 'not recorded'}; time: {data.get('signed_at') or 'not recorded'}", "Helvetica", 8, width - margin * 2, 10)
    c.drawString(margin, y, "Not an official NCVET/MSDE certificate.")
    y -= 20

    c.setFont("Helvetica", 7.5)
    c.drawString(margin, y, f"Scan to verify: {data['verify_url']}")
    qr_size = 70
    qr_y = y - qr_size - 4
    if qr_y < 20:
        c.showPage()
        qr_y = height - margin - qr_size
    _draw_qr(c, _qr_cells(data["verify_url"]), margin, qr_y, qr_size)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin, 20, data["disclaimer"])
    c.showPage()
    c.save()
    return buf.getvalue()


def _report_out(report: models.SignedReport) -> schemas.SignedReportOut:
    return schemas.SignedReportOut(
        assessment_id=report.assessment_id, report_uid=report.report_uid,
        revision_number=report.revision_number, pdf_sha256=report.pdf_sha256,
        signature=report.signature, key_id=report.key_id,
        computed_recommendation=report.computed_recommendation,
        final_recommendation=report.final_recommendation, override_reason=report.override_reason,
        signed_at=report.signed_at,
    )


def _sign_off_authorized(
    assessment_id: int,
    body: schemas.SignOffIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.SignedReportOut:
    """Password-confirmed final sign-off: records the assessor's final
    recommendation (optionally overriding the computed one, with a mandatory
    reason) and produces the one, immutable, Ed25519-signed PDF for this
    assessment. Idempotent -- a retry after the first success returns the
    exact same signed artifact, never resigns. Never logs/stores the
    password itself."""
    assessment = db.execute(select(models.Assessment).where(models.Assessment.id == assessment_id).with_for_update()).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    # Lock before any read that influences what gets signed, so a
    # concurrent score PUT or a second concurrent sign-off call can't
    # interleave with this one and produce a report for an inconsistent
    # snapshot (see docs/gates/P7.md section 5).
    db.execute(select(models.Assessment).where(models.Assessment.id == assessment_id).with_for_update())

    # Password re-entry is validated on EVERY call, including an idempotent
    # retry against an already-signed report -- "password-confirmed"
    # means every sign-off request proves the password, not just the one
    # that happens to create the report.
    existing = db.query(models.SignedReport).filter_by(assessment_id=assessment_id).one_or_none()
    if existing is not None:
        return _report_out(existing)

    if assessment.status != "in_review":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot sign off: assessment is '{assessment.status}', not 'in_review'",
        )

    pending_request = (
        db.query(models.ReassessmentRequest)
        .filter_by(assessment_id=assessment_id, status="pending")
        .one_or_none()
    )
    if pending_request is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "cannot sign off: a reassessment request is still pending resubmission",
        )

    stale_score = (
        db.query(models.AssessmentCriterionScore)
        .filter_by(assessment_id=assessment_id, needs_review=True)
        .first()
    )
    if stale_score is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot sign off: PC '{stale_score.pc.full_id}' was reopened for reassessment and has not "
            "been re-reviewed since -- score it again before signing off",
        )

    computed = get_computed_outcome(db, assessment)
    if body.final_recommendation != computed.outcome and not (body.override_reason and body.override_reason.strip()):
        raise HTTPException(
            422, "override_reason is required when final_recommendation differs from the computed outcome",
        )

    now = datetime.datetime.now(datetime.timezone.utc)
    assessment.status = "recommended"
    assessment.decision = "recommended"
    assessment.decided_by_id = user.id
    assessment.decided_at = now
    assessment.decision_reviewer_identity = identity(user)

    report_uid = secrets.token_urlsafe(16)
    verify_url = f"{settings.report_verify_base_url.rstrip('/')}/#/verify/{report_uid}"
    snapshot = _report_snapshot(
        db, assessment, computed, body.final_recommendation, body.override_reason, user, report_uid, verify_url,
    )

    pdf_bytes = _render_pdf(snapshot)
    pdf_sha256, signature, key_id = report_signing.sign_pdf(pdf_bytes)
    pdf_key = f"reports/{report_uid}.pdf"
    uploads._storage.write(pdf_key, pdf_bytes)

    report = models.SignedReport(
        assessment_id=assessment_id, report_uid=report_uid, revision_number=assessment.revision_number,
        canonical_json=report_signing.canonical_json(snapshot), pdf_storage_key=pdf_key,
        pdf_sha256=pdf_sha256, signature=signature, key_id=key_id,
        computed_recommendation=computed.outcome, final_recommendation=body.final_recommendation,
        override_reason=body.override_reason, signed_by_id=user.id,
        reviewer_identity=identity(user),
    )
    db.add(report)
    _audit(db, assessment_id, actor_user_id=user.id, actor_role=user.role, action="signed_off", details={
        "reviewer_identity": identity(user),
        "computed_recommendation": computed.outcome, "final_recommendation": body.final_recommendation,
        "override_reason": body.override_reason, "report_uid": report_uid, "revision_number": assessment.revision_number,
    })
    db.commit()
    db.refresh(report)
    return _report_out(report)


@router.post("/assessments/{assessment_id}/sign-off", response_model=schemas.SignedReportOut, status_code=201)
def sign_off(assessment_id: int, body: schemas.SignOffIn, db: Session = Depends(get_db),
             user: models.User = Depends(require_assessor)) -> schemas.SignedReportOut:
    # Organizational deployments retain password re-entry on EVERY request.
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect password")
    return _sign_off_authorized(assessment_id, body, db, user)


@router.get("/assessments/{assessment_id}/report")
def download_report(
    assessment_id: int,
    format: Literal["json", "pdf", "receipt"] = "json",
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> Response:
    """Protected -- same dual auth as GET /assessments/{id}. Serves the
    STORED immutable artifact, never a re-render. format=receipt is the
    detached signature bundle tools/verify_report.py needs alongside the
    PDF -- fetched through this same authenticated channel (never the
    public /verify/{report_id} endpoint, which deliberately omits the raw
    signature) so an operator always gets it from a source they already
    trust, never an arbitrary untrusted bundle."""
    report = db.query(models.SignedReport).filter_by(assessment_id=assessment_id).one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no signed report exists yet for this assessment")

    if format == "json":
        return Response(content=report.canonical_json, media_type="application/json")

    if format == "receipt":
        import json as _json

        receipt = {
            "report_id": report.report_uid, "assessment_id": assessment_id,
            "revision_number": report.revision_number, "pdf_sha256": report.pdf_sha256,
            "signature": report.signature, "key_id": report.key_id,
            "signed_at": report.signed_at.isoformat(),
        }
        return Response(content=_json.dumps(receipt, indent=2), media_type="application/json")

    pdf_bytes = uploads._storage.read(report.pdf_storage_key)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="assessment-{assessment_id}-report-v{report.revision_number}.pdf"'},
    )


@router.get("/reports/{assessment_id}/verify", response_model=schemas.ReportVerifyOut)
def verify_report(assessment_id: int, db: Session = Depends(get_db)) -> schemas.ReportVerifyOut:
    """Public, unauthenticated -- kept for backward compatibility (looks up
    by the internal assessment_id). See GET /verify/{report_id} for the
    new, stable-public-id version the signed PDF's QR code actually points
    at."""
    report = db.query(models.SignedReport).filter_by(assessment_id=assessment_id).one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no signed report exists for this assessment")

    pdf_bytes = uploads._storage.read(report.pdf_storage_key)
    valid = report_signing.verify_pdf(pdf_bytes, report.pdf_sha256, report.signature, report.key_id)
    return schemas.ReportVerifyOut(
        assessment_id=assessment_id, valid=valid, key_id=report.key_id, signed_at=report.signed_at,
    )

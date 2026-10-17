"""Account-free, email-verified, operator-authorized review capabilities.

Existing private routes never accept these credentials. This adapter invokes
the same scoring, reassessment and report services only after explicit scope,
assessment, revision, expiry, CSRF and live allowlist checks.
"""
import datetime
import hashlib
import hmac
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..abuse import source, throttle
from ..config import settings
from ..db import get_db
from ..reviewer_identity import ReviewerActor, identity
from . import assessments, evidence, public, reassessment, reports, scoring

router = APIRouter(prefix="/reviewer", tags=["account-free review"])
COOKIE = "parakh_reviewer"
CSRF_COOKIE = "parakh_reviewer_csrf"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def allowed(email: str) -> bool:
    return email.lower() in {e.strip().lower() for e in settings.reviewer_allowed_emails.split(",") if e.strip()}


def delivery_ready() -> bool:
    return bool(settings.reviewer_smtp_host and settings.reviewer_email_from and settings.reviewer_allowed_emails)


def send_code(email: str, code: str, assessment_id: int, action: str) -> None:
    message = EmailMessage()
    message["From"] = settings.reviewer_email_from
    message["To"] = email
    message["Subject"] = "PARAKH reviewer verification code"
    message.set_content(f"Code: {code}\nAssessment: {assessment_id}\nAction: {action}\n"
                        "Expires in 10 minutes. Do not share this code. Ignore if you did not request it.")
    with smtplib.SMTP(settings.reviewer_smtp_host, settings.reviewer_smtp_port, timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if settings.reviewer_smtp_username:
            smtp.login(settings.reviewer_smtp_username, settings.reviewer_smtp_password or "")
        smtp.send_message(message)


def code_digest(challenge_id: str, code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"review-code:{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def utc(value):
    return value.replace(tzinfo=datetime.timezone.utc) if value.tzinfo is None else value


@router.get("/availability")
def availability():
    return {"available": delivery_ready(),
            "message": "Verification requires an operator-authorized email address." if delivery_ready() else
                       "Reviewer email delivery is not configured. Scoring and sign-off are unavailable."}


@router.post("/challenges")
def challenge(body: schemas.ReviewerChallengeIn, request: Request, db: Session = Depends(get_db)):
    if not delivery_ready():
        raise HTTPException(503, "reviewer email delivery is not configured")
    throttle(db, "review-email-ip:" + source(request), 20, 600)
    throttle(db, "review-email:" + body.email.lower(), 10, 600)
    throttle(db, "review-email-global", 50, 86400)
    assessment = public.visible(db).filter(models.Assessment.id == body.assessment_id).one_or_none()
    if not assessment:
        raise HTTPException(404, "public assessment not found")
    if not allowed(body.email):
        raise HTTPException(403, "this email is not authorized to review; contact the operator")
    code = f"{secrets.randbelow(1000000):06d}"
    challenge_id = secrets.token_urlsafe(24)
    row = models.ReviewerChallenge(id=challenge_id, assessment_id=assessment.id,
        revision_number=assessment.revision_number, name=body.name, email=body.email.lower(), action=body.action,
        code_hash=code_digest(challenge_id, code), expires_at=models.utcnow() + datetime.timedelta(minutes=10))
    db.add(row)
    try:
        send_code(row.email, code, assessment.id, body.action)
    except Exception:
        db.rollback()
        raise HTTPException(503, "verification email could not be delivered; no authority was granted") from None
    db.commit()
    return {"challenge_id": row.id, "expires_in_seconds": 600}


@router.post("/verify")
def verify(body: schemas.ReviewerVerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, "review-verify:" + source(request), 30, 600)
    row = db.execute(select(models.ReviewerChallenge).where(models.ReviewerChallenge.id == body.challenge_id)
                     .with_for_update()).scalar_one_or_none()
    if not row or row.used or utc(row.expires_at) <= models.utcnow() or row.attempts >= 5:
        raise HTTPException(401, "invalid or expired code")
    row.attempts += 1
    if not hmac.compare_digest(row.code_hash, code_digest(row.id, body.code)):
        db.commit()
        raise HTTPException(401, "invalid or expired code")
    if not allowed(row.email):
        raise HTTPException(403, "reviewer permission withdrawn")
    row.used = True
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = models.utcnow() + datetime.timedelta(minutes=15)
    db.add(models.ReviewerSession(token_hash=digest(token), challenge_id=row.id, csrf_hash=digest(csrf), expires_at=expires))
    db.commit()
    for name, value, http_only in ((COOKIE, token, True), (CSRF_COOKIE, csrf, False)):
        response.set_cookie(name, value, max_age=900, httponly=http_only, secure=settings.app_env != "development",
                            samesite="strict", path="/")
    return {"name": row.name, "email": row.email, "email_verified": True, "name_verified": False,
            "assessment_id": row.assessment_id, "action": row.action, "expires_at": expires}


def capability(action="read"):
    def authorize(assessment_id: int, request: Request, db: Session = Depends(get_db)):
        throttle(db, "review-requests:" + source(request), 240, 60)
        token = request.cookies.get(COOKIE, "")
        session = db.execute(select(models.ReviewerSession).where(models.ReviewerSession.token_hash == digest(token))
                             .with_for_update()).scalar_one_or_none()
        if not session or utc(session.expires_at) <= models.utcnow():
            raise HTTPException(401, "reviewer verification required or session expired")
        row = db.get(models.ReviewerChallenge, session.challenge_id)
        if row.assessment_id != assessment_id or not allowed(row.email):
            raise HTTPException(403, "reviewer capability is not valid for this assessment")
        assessment = db.execute(select(models.Assessment).where(models.Assessment.id == assessment_id)
            .with_for_update().execution_options(populate_existing=True)).scalar_one()
        if assessment.revision_number != row.revision_number:
            raise HTTPException(409, "assessment revision changed; verify again")
        if action != "read" and row.action != action:
            raise HTTPException(403, "verify the email code for this action")
        if request.method not in ("GET", "HEAD"):
            csrf = request.headers.get("X-Reviewer-CSRF", "")
            if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
                raise HTTPException(403, "missing reviewer CSRF confirmation")
        if action in ("reject", "reassessment", "sign_off"):
            session.expires_at = models.utcnow()  # one consequential action per code; same transaction as mutation
        return ReviewerActor(row.name, row.email, row.id)
    return authorize


@router.get("/assessments/{assessment_id}", response_model=schemas.AssessmentOut)
def detail(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability())):
    return assessments._assessment_out(db, db.get(models.Assessment, assessment_id))


@router.get("/assessments/{assessment_id}/review", response_model=list[schemas.CriterionReviewItemOut])
def review(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability())):
    return scoring.get_review(assessment_id, db, actor)


@router.get("/assessments/{assessment_id}/rubric", response_model=list[schemas.RubricItemOut])
def rubric(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability())):
    return assessments.get_assessment_rubric(assessment_id, db, actor)


@router.post("/assessments/{assessment_id}/start-review", response_model=schemas.AssessmentOut)
def start(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability("review"))):
    return assessments.start_review(assessment_id, db, actor)


@router.put("/assessments/{assessment_id}/review", response_model=schemas.CriterionScoreOut)
def score(assessment_id: int, body: schemas.CriterionScoreIn, db: Session = Depends(get_db), actor=Depends(capability("review"))):
    return scoring.put_score(assessment_id, body, db, actor)


@router.get("/assessments/{assessment_id}/competency-profile", response_model=schemas.CompetencyProfileOut)
def profile(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability())):
    return scoring.get_competency_profile(assessment_id, db, actor)


@router.post("/assessments/{assessment_id}/reject", response_model=schemas.AssessmentOut)
def reject(assessment_id: int, body: schemas.ReviewerRejectIn, db: Session = Depends(get_db), actor=Depends(capability("reject"))):
    assessment = db.get(models.Assessment, assessment_id)
    if assessment.status != "in_review":
        raise HTTPException(409, "assessment must be in review")
    if not body.reason.strip():
        raise HTTPException(422, "reason is required")
    assessment.status = assessment.decision = "not_recommended"
    assessment.decision_notes = body.reason.strip()
    assessment.decided_at = models.utcnow()
    assessment.decision_reviewer_identity = identity(actor)
    assessments._audit(db, assessment_id, None, actor.role, "rejected", {
        "reviewer_identity": identity(actor), "reason": body.reason.strip(), "decision": "not_recommended",
        "revision_number": assessment.revision_number, "task_codes": []})
    db.commit()
    return assessments._assessment_out(db, assessment)


class ConfirmedReassessment(schemas.ReassessmentRequestIn):
    confirmed: bool


@router.post("/assessments/{assessment_id}/reassessment-requests", response_model=schemas.ReassessmentRequestOut, status_code=201)
def request_reassessment(assessment_id: int, body: ConfirmedReassessment, db: Session = Depends(get_db),
                         actor=Depends(capability("reassessment"))):
    if not body.confirmed:
        raise HTTPException(422, "explicit confirmation is required")
    return reassessment.create_reassessment_request(assessment_id, body, db, actor)


@router.post("/assessments/{assessment_id}/sign-off", response_model=schemas.SignedReportOut, status_code=201)
def sign(assessment_id: int, body: schemas.ReviewerSignOffIn, db: Session = Depends(get_db), actor=Depends(capability("sign_off"))):
    assessment = db.get(models.Assessment, assessment_id)
    rubric = scoring._rubric_rows(db, assessment.pack_id)
    scores = {s.pc_id: s for s in db.query(models.AssessmentCriterionScore).filter_by(assessment_id=assessment_id).all()}
    if not rubric or any(pc.id not in scores or scores[pc.id].scored_at is None for _, pc, _ in rubric):
        raise HTTPException(409, "every performance criterion must be human-confirmed before sign-off")
    return reports._sign_off_authorized(assessment_id, body, db, actor)


@router.get("/assessments/{assessment_id}/reassessment-requests", response_model=list[schemas.ReassessmentRequestOut])
def history(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability())):
    return reassessment.list_reassessment_requests(assessment_id, db, actor)


@router.get("/assessments/{assessment_id}/revisions", response_model=list[schemas.AssessmentRevisionOut])
def revisions(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability())):
    return reassessment.list_revisions(assessment_id, db, actor)


@router.get("/assessments/{assessment_id}/audit-log", response_model=list[schemas.AuditLogEntryOut])
def audit(assessment_id: int, db: Session = Depends(get_db), actor=Depends(capability())):
    return assessments.get_audit_log(assessment_id, db, actor)


@router.get("/assessments/{assessment_id}/sync-status", response_model=schemas.SyncStatusOut)
def sync(assessment_id: int, revision_id: str | None = None, db: Session = Depends(get_db), actor=Depends(capability())):
    return assessments.get_sync_status(assessment_id, revision_id, db, actor)


@router.get("/assessments/{assessment_id}/evidence/{evidence_id}/content")
def content(assessment_id: int, evidence_id: int, request: Request, db: Session = Depends(get_db), actor=Depends(capability())):
    return evidence.get_evidence_content(assessment_id, evidence_id, request, db, actor)


@router.get("/assessments/{assessment_id}/evidence/{evidence_id}/thumbnail")
def thumbnail(assessment_id: int, evidence_id: int, request: Request, db: Session = Depends(get_db), actor=Depends(capability())):
    return evidence.get_evidence_thumbnail(assessment_id, evidence_id, request, db, actor)


@router.get("/assessments/{assessment_id}/report")
def report(assessment_id: int, format: str = "json", db: Session = Depends(get_db), actor=Depends(capability())):
    if format not in ("json", "pdf", "receipt"):
        raise HTTPException(422, "unknown report format")
    return reports.download_report(assessment_id, format, db, actor)

"""Assessor password accounts and legacy email-code review capabilities.

Both adapters use the same scoring, reassessment, evidence and report services.
Password accounts confirm every final action with a fresh password entry.
"""
import datetime
import hashlib
import hmac
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..abuse import source, throttle
from ..auth import hash_password, verify_password, _DUMMY_HASH
from ..config import settings
from ..db import get_db
from ..reviewer_identity import ReviewerActor, identity
from . import assessments, evidence, public, reassessment, reports, scoring

router = APIRouter(prefix="/reviewer", tags=["assessor review"])
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


def account_identity(account, session):
    return {"id": account.id, "name": account.name, "email": account.email, "phone": account.phone,
            "email_verified": False, "expires_at": session.expires_at}


def require_csrf(session, request):
    csrf = request.headers.get("X-Reviewer-CSRF", "")
    if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
        raise HTTPException(403, "missing reviewer CSRF confirmation")


def account_session(request: Request, db: Session):
    session = db.get(models.ReviewerAccountSession, digest(request.cookies.get(COOKIE, "")))
    if not session or utc(session.expires_at) <= models.utcnow():
        raise HTTPException(401, "assessor sign-in required or session expired")
    account = db.get(models.ReviewerAccount, session.account_id)
    if not account:
        raise HTTPException(401, "assessor sign-in required")
    return account, session


def create_account_session(account, response, db):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    session = models.ReviewerAccountSession(token_hash=digest(token), account_id=account.id,
        csrf_hash=digest(csrf), expires_at=models.utcnow() + datetime.timedelta(hours=8))
    db.add(session)
    db.commit()
    for name, value, http_only in ((COOKIE, token, True), (CSRF_COOKIE, csrf, False)):
        response.set_cookie(name, value, max_age=8 * 3600, httponly=http_only,
            secure=settings.app_env != "development", samesite="strict", path="/")
    return account_identity(account, session)


@router.post("/accounts", status_code=201)
def register_account(body: schemas.ReviewerRegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, "review-register:" + source(request), 20, 3600)
    account = models.ReviewerAccount(id=secrets.token_urlsafe(24), name=body.name, email=body.email,
        phone=body.phone, password_hash=hash_password(body.password.get_secret_value()))
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "an assessor account already uses this email; sign in with your password") from None
    return create_account_session(account, response, db)


@router.post("/sessions")
def login_account(body: schemas.ReviewerLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle(db, "review-login:" + source(request), 40, 600)
    throttle(db, "review-login-email:" + body.email, 15, 600)
    account = db.query(models.ReviewerAccount).filter_by(email=body.email).one_or_none()
    ok = verify_password(body.password.get_secret_value(), account.password_hash if account else _DUMMY_HASH)
    if not account or not ok:
        raise HTTPException(401, "incorrect email or password")
    return create_account_session(account, response, db)


@router.get("/account")
def current_account(request: Request, db: Session = Depends(get_db)):
    account, session = account_session(request, db)
    return account_identity(account, session)


@router.get("/queue", response_model=list[schemas.PublicAssessmentOut])
def private_queue(request: Request, response: Response, before_id: int | None = None, db: Session = Depends(get_db)):
    throttle(db, "review-requests:" + source(request), 240, 60)
    account_session(request, db)
    response.headers["Cache-Control"] = "private, no-store"
    rows = public.visible(db)
    if before_id is not None:
        rows = rows.filter(models.Assessment.id < before_id)
    assessments_rows = rows.order_by(models.Assessment.id.desc()).limit(50).all()
    signed = {r.assessment_id: r for r in db.query(models.SignedReport).filter(
        models.SignedReport.assessment_id.in_([a.id for a in assessments_rows])).all()} if assessments_rows else {}
    return [public.summary(db, a, reports=signed, private=True) for a in assessments_rows]


@router.post("/logout")
def logout_account(request: Request, response: Response, db: Session = Depends(get_db)):
    _, session = account_session(request, db)
    require_csrf(session, request)
    db.delete(session)
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"status": "signed_out"}


def confirm_account_password(actor, password, request, db, *, require_password=False):
    if not actor.account_id:
        if require_password:
            raise HTTPException(403, "signed finalization requires a password-based assessor account; sign in to continue")
        return  # Existing email-code capabilities already authorize exactly one action.
    throttle(db, "review-confirm:" + actor.account_id, 15, 600)
    throttle(db, "review-confirm-ip:" + source(request), 60, 600)
    account = db.get(models.ReviewerAccount, actor.account_id)
    if not password or not account or not verify_password(password.get_secret_value(), account.password_hash):
        raise HTTPException(403, "incorrect password; the assessment was not changed")


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
        account_auth = db.get(models.ReviewerAccountSession, digest(token))
        if account_auth:
            account, account_auth = account_session(request, db)
            if not db.query(models.Assessment.id).filter(
                models.Assessment.id == assessment_id, models.Assessment.provenance == "candidate-v1",
                models.Assessment.submitted_at.isnot(None), models.Assessment.status != "draft",
            ).first():
                raise HTTPException(404, "submitted assessment not found")
            if request.method not in ("GET", "HEAD"):
                db.execute(select(models.Assessment).where(models.Assessment.id == assessment_id)
                           .with_for_update().execution_options(populate_existing=True)).scalar_one()
                require_csrf(account_auth, request)
            return ReviewerActor(account.name, account.email, account_auth.token_hash, account_id=account.id)
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


class ReviewerWorkspaceOut(BaseModel):
    assessment: schemas.AssessmentOut
    review: list[schemas.CriterionReviewItemOut]
    profile: schemas.CompetencyProfileOut
    sync: schemas.SyncStatusOut


class ReviewerHistoryOut(BaseModel):
    revisions: list[schemas.AssessmentRevisionOut]
    requests: list[schemas.ReassessmentRequestOut]
    audit: list[schemas.AuditLogEntryOut]


@router.get("/assessments/{assessment_id}/workspace", response_model=ReviewerWorkspaceOut)
def workspace(assessment_id: int, response: Response, db: Session = Depends(get_db), actor=Depends(capability())):
    """One authorized read for the initial review, without seven auth/DB round trips."""
    response.headers["Cache-Control"] = "private, no-store"
    return ReviewerWorkspaceOut(
        assessment=assessments._assessment_out(db, db.get(models.Assessment, assessment_id)),
        review=scoring.get_review(assessment_id, db, actor),
        profile=scoring.get_competency_profile(assessment_id, db, actor),
        sync=assessments.get_sync_status(assessment_id, None, db, actor),
    )


@router.get("/assessments/{assessment_id}/history", response_model=ReviewerHistoryOut)
def review_history(assessment_id: int, response: Response, db: Session = Depends(get_db), actor=Depends(capability())):
    """History is loaded only when the assessor opens its tab."""
    response.headers["Cache-Control"] = "private, no-store"
    return ReviewerHistoryOut(
        revisions=reassessment.list_revisions(assessment_id, db, actor),
        requests=reassessment.list_reassessment_requests(assessment_id, db, actor),
        audit=assessments.get_audit_log(assessment_id, db, actor),
    )


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
def reject(assessment_id: int, body: schemas.ReviewerRejectIn, request: Request, db: Session = Depends(get_db), actor=Depends(capability("reject"))):
    confirm_account_password(actor, body.password, request, db, require_password=True)
    if not body.reason.strip():
        raise HTTPException(422, "reason is required")
    reports._finalize_authorized(assessment_id, schemas.ReviewerSignOffIn(
        final_recommendation="NOT_YET_COMPETENT", override_reason=body.reason.strip(), confirmed=True,
    ), db, actor, rejection_reason=body.reason)
    return assessments._assessment_out(db, db.get(models.Assessment, assessment_id))


class ConfirmedReassessment(schemas.ReassessmentRequestIn):
    confirmed: bool
    password: schemas.SecretStr | None = None


@router.post("/assessments/{assessment_id}/reassessment-requests", response_model=schemas.ReassessmentRequestOut, status_code=201)
def request_reassessment(assessment_id: int, body: ConfirmedReassessment, request: Request, db: Session = Depends(get_db),
                         actor=Depends(capability("reassessment"))):
    if not body.confirmed:
        raise HTTPException(422, "explicit confirmation is required")
    confirm_account_password(actor, body.password, request, db)
    return reassessment.create_reassessment_request(assessment_id, body, db, actor)


@router.post("/assessments/{assessment_id}/sign-off", response_model=schemas.SignedReportOut, status_code=201)
def sign(assessment_id: int, body: schemas.ReviewerSignOffIn, request: Request, db: Session = Depends(get_db), actor=Depends(capability("sign_off"))):
    confirm_account_password(actor, body.password, request, db, require_password=True)
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

import datetime

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, text

from .. import models, schemas
from ..auth import (
    ACCESS_TOKEN_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    _MUTATING_METHODS,
    decode_access_token,
    require_assessor,
)
from ..db import get_db
from ..worker_tokens import generate_worker_token, hash_worker_token
from ..abuse import enrollment_limits, enrollment_capacity
from ..reviewer_identity import identity

router = APIRouter(prefix="/assessments", tags=["assessments"])

_bearer = HTTPBearer(auto_error=False)


def _assessor_or_worker_token(
    assessment_id: int,
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
) -> models.Assessment:
    """GET /assessments/{id} (and the evidence/report endpoints that reuse
    this dependency) is read by both workers (their own progress, via the
    capability token issued at creation) and assessors (review, via JWT --
    Bearer header for API clients, or the dashboard's session cookie) --
    see docs/worker_capability_tokens.md."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    token = creds.credentials if creds is not None else access_token_cookie
    if token is not None:
        if creds is None and request.method in _MUTATING_METHODS:
            # Cookie path on a mutating request -- same CSRF double-submit
            # check as auth.get_current_user (Bearer requests skip this,
            # a cross-site page can't attach a custom header).
            if not csrf_cookie or not x_csrf_token or csrf_cookie != x_csrf_token:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or invalid CSRF token")
        claims = decode_access_token(token)
        user = db.get(models.User, int(claims["sub"]))
        # Re-verify against the live DB row, not just the JWT claim -- a
        # user deleted or demoted after the token was issued must lose
        # access immediately rather than whenever the token happens to
        # expire (see auth.get_current_user, same pattern).
        if user is not None and user.role == claims.get("role") and user.role in ("assessor", "admin"):
            return assessment

    if (
        assessment.worker_token_status == "active"
        and x_worker_token
        and hash_worker_token(x_worker_token) == assessment.worker_token_hash
    ):
        return assessment

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "requires an assessor/admin bearer token or this assessment's X-Worker-Token")


def _new_assessment(
    db: Session, worker_id: int, pack_id: int, actor_user_id: int | None, actor_role: str,
    reassessment_of_id: int | None = None,
) -> tuple[models.Assessment, str]:
    """Shared by create_assessment and decisions.reassess -- both produce a
    brand-new Assessment with the fixed five tasks (in pack order, never
    worker-chosen) and a fresh worker capability token."""
    raw_token, token_hash = generate_worker_token()
    assessment = models.Assessment(
        worker_id=worker_id, pack_id=pack_id, worker_token_hash=token_hash,
        reassessment_of_id=reassessment_of_id,
    )
    db.add(assessment)
    db.flush()

    templates = (
        db.query(models.TaskTemplate)
        .filter_by(pack_id=pack_id)
        .order_by(models.TaskTemplate.task_order)
        .all()
    )
    for t in templates:
        db.add(models.AssessmentTask(
            assessment_id=assessment.id,
            task_code=t.task_code,
            budget_bytes=t.budget_bytes,
        ))

    # P7: revision 1 always exists from the moment the assessment does --
    # see models.AssessmentRevision's docstring. reopened_task_codes=None
    # means "everything" (no task-specific restriction on the first pass).
    db.add(models.AssessmentRevision(
        assessment_id=assessment.id, revision_number=1, status="open",
    ))

    _audit(
        db, assessment.id, actor_user_id=actor_user_id, actor_role=actor_role, action="created",
        details={"reassessment_of_id": reassessment_of_id} if reassessment_of_id else {},
    )
    return assessment, raw_token


def _created_out(assessment: models.Assessment, raw_token: str) -> schemas.AssessmentCreatedOut:
    return schemas.AssessmentCreatedOut(
        id=assessment.id,
        worker_id=assessment.worker_id,
        pack_id=assessment.pack_id,
        status=assessment.status,
        worker_token=raw_token,
        tasks=[
            schemas.AssessmentTaskOut(task_code=t.task_code, budget_bytes=t.budget_bytes, bytes_used=t.bytes_used, status=t.status)
            for t in assessment.tasks
        ],
    )


@router.post("", response_model=schemas.AssessmentCreatedOut, status_code=201)
def create_assessment(body: schemas.AssessmentCreate, request: Request, db: Session = Depends(get_db)) -> schemas.AssessmentCreatedOut:
    """Open to any caller (the worker app has no login) -- the response
    carries a fresh, unguessable capability token that every subsequent
    worker-side call on this assessment must present. See
    docs/worker_capability_tokens.md."""
    enrollment_limits(db, request)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(72026017)"))
    enrollment_capacity(db)
    worker = db.get(models.User, body.worker_id)
    if worker is None or worker.role != "worker":
        raise HTTPException(404, "worker not found")
    if worker.enrollment_secret_hash:
        raise HTTPException(403, "use the protected candidate enrollment contract")
    pack = db.get(models.QualificationPack, body.pack_id)
    if pack is None:
        raise HTTPException(404, "pack not found")

    assessment, raw_token = _new_assessment(db, worker.id, pack.id, actor_user_id=None, actor_role="system")
    db.commit()
    db.refresh(assessment)
    return _created_out(assessment, raw_token)


def _audit(db: Session, assessment_id: int, actor_user_id: int | None, actor_role: str, action: str, details: dict | None = None) -> None:
    db.add(models.AuditLog(
        assessment_id=assessment_id, actor_user_id=actor_user_id, actor_role=actor_role,
        action=action, details=details or {},
    ))


def _evidence_currency(db: Session, assessment: models.Assessment) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """P7: (revision_id -> revision_number) and the set of (task_code,
    client_evidence_id) pairs declared in the assessment's latest COMPLETE
    manifest -- i.e. the active revision's full evidence snapshot, inherited
    items included. An item with no revision_id at all (pre-P6 direct
    upload protocol -- tests, the old docker_e2e_smoke script) is always
    "current": there is no versioning concept for it to be stale against."""
    revisions = db.query(models.AssessmentRevision).filter_by(assessment_id=assessment.id).all()
    revision_number_by_id = {r.revision_id: r.revision_number for r in revisions if r.revision_id}

    latest_complete = (
        db.query(models.DeviceManifest)
        .filter_by(assessment_id=assessment.id, status="complete")
        .order_by(models.DeviceManifest.id.desc())
        .first()
    )
    current_pairs: set[tuple[str, str]] = set()
    if latest_complete is not None:
        current_pairs = {(i["task_code"], i["evidence_id"]) for i in latest_complete.declared_items}
    return revision_number_by_id, current_pairs


def _assessment_out(db: Session, assessment: models.Assessment) -> schemas.AssessmentOut:
    assessment = db.get(
        models.Assessment, assessment.id,
        options=[joinedload(models.Assessment.tasks).joinedload(models.AssessmentTask.evidence_items)],
    )
    pack = db.get(models.QualificationPack, assessment.pack_id)
    worker_user = db.get(models.User, assessment.worker_id)
    revision_number_by_id, current_pairs = _evidence_currency(db, assessment)

    def _evidence_out(e: models.EvidenceItem, task_code: str) -> schemas.EvidenceReceiptOut:
        revision_number = revision_number_by_id.get(e.revision_id, 1) if e.revision_id else 1
        is_current = True if e.revision_id is None else (task_code, e.client_evidence_id) in current_pairs
        return schemas.EvidenceReceiptOut(
            id=e.id, kind=e.kind, mime=e.mime, declared_size_bytes=e.declared_size_bytes,
            sha256=e.sha256, created_at=e.created_at, thumbnail_status=e.thumbnail_status,
            metadata_status=e.metadata_status, duration_ms=e.duration_ms, width_px=e.width_px,
            height_px=e.height_px, revision_number=revision_number, is_current_revision=is_current,
            device_captured_at=e.device_captured_at,
            quality_check_status=e.quality_check_status, assistance=e.assistance,
        )

    return schemas.AssessmentOut(
        id=assessment.id,
        worker_id=assessment.worker_id,
        worker_name=worker_user.display_name,
        pack_id=assessment.pack_id,
        pack_code=pack.qp_code,
        pack_name=pack.qp_name,
        status=assessment.status,
        assessor_id=assessment.assessor_id,
        total_bytes_used=assessment.total_bytes_used,
        total_budget_bytes=pack.final_evidence_budget_bytes,
        created_at=assessment.created_at,
        submitted_at=assessment.submitted_at,
        decision=assessment.decision,
        decision_notes=assessment.decision_notes,
        reassessment_of_id=assessment.reassessment_of_id,
        declared_match_result=assessment.declared_match_result,
        declared_coverage_fraction=assessment.declared_coverage_fraction,
        declared_gap_task_codes=assessment.declared_gap_task_codes,
        declared_match_reasons=assessment.declared_match_reasons,
        current_revision_id=assessment.current_revision_id,
        revision_number=assessment.revision_number,
        tasks=[
            schemas.AssessmentTaskOut(
                task_code=t.task_code,
                budget_bytes=t.budget_bytes,
                bytes_used=t.bytes_used,
                status=t.status,
                evidence=[_evidence_out(e, t.task_code) for e in t.evidence_items],
            )
            for t in assessment.tasks
        ],
    )


@router.get("/{assessment_id}", response_model=schemas.AssessmentOut)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> schemas.AssessmentOut:
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    return _assessment_out(db, assessment)


@router.post("/{assessment_id}/submit", response_model=schemas.AssessmentOut)
def submit_assessment(
    assessment_id: int,
    x_worker_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.AssessmentOut:
    """The worker app calls this once it's done capturing evidence for all
    five tasks -- moves draft -> submitted and LOCKS further evidence
    uploads (see routers/uploads.py's require_draft checks). Worker-token
    authenticated, same as uploads -- there is no worker login."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if (
        assessment.worker_token_status != "active"
        or not x_worker_token
        or hash_worker_token(x_worker_token) != assessment.worker_token_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Worker-Token for this assessment")
    # P7: a targeted reassessment reopens the SAME assessment (status
    # 'needs_reassessment') rather than creating a new one -- resubmitting
    # that revision is accepted here too, moving back to 'submitted' so the
    # assessor's existing start-review flow picks it up unchanged. Anything
    # else (in_review, submitted, recommended) cannot be (re)submitted.
    is_resubmission = assessment.status == models.AssessmentStatus.needs_reassessment.value
    if assessment.status != models.AssessmentStatus.draft.value and not is_resubmission:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot submit: assessment is '{assessment.status}', not 'draft' or 'needs_reassessment'",
        )

    # P6: an assessment that has a sync revision in progress may only be
    # submitted once every item that revision's manifest declares has been
    # uploaded AND verified against it (see uploads._maybe_complete_manifest).
    # An assessment that never used the P6 sync path (current_revision_id is
    # never set) is unaffected -- submit behaves exactly as it did in P2.1/
    # P2.2, so the pre-P6 direct-upload tests/scripts keep working unchanged.
    active_revision = None
    if is_resubmission:
        active_revision = (
            db.query(models.AssessmentRevision)
            .filter_by(assessment_id=assessment.id, revision_number=assessment.revision_number, status="open")
            .one_or_none()
        )
        if active_revision is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "no open reassessment revision to resubmit")
        if not active_revision.revision_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "no sealed package has been received yet for this revision")
        manifest = (
            db.query(models.DeviceManifest)
            .filter_by(assessment_id=assessment.id, revision_id=active_revision.revision_id)
            .one_or_none()
        )
        if manifest is None or manifest.status != "complete":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "sealed package is not fully synced and verified yet -- cannot resubmit",
            )
    elif assessment.current_revision_id:
        manifest = (
            db.query(models.DeviceManifest)
            .filter_by(assessment_id=assessment.id, revision_id=assessment.current_revision_id)
            .one_or_none()
        )
        if manifest is None or manifest.status != "complete":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "sealed package is not fully synced and verified yet -- cannot submit",
            )

    now = datetime.datetime.now(datetime.timezone.utc)
    assessment.status = models.AssessmentStatus.submitted.value
    if is_resubmission:
        active_revision.status = "submitted"
        active_revision.submitted_at = now
        pending_request = (
            db.query(models.ReassessmentRequest)
            .filter_by(assessment_id=assessment.id, revision_id=active_revision.id, status="pending")
            .one_or_none()
        )
        if pending_request is not None:
            pending_request.status = "fulfilled"
            pending_request.fulfilled_at = now
        _audit(db, assessment.id, actor_user_id=None, actor_role="worker", action="resubmitted", details={
            "revision_number": active_revision.revision_number,
        })
    else:
        assessment.submitted_at = now
        current_revision = (
            db.query(models.AssessmentRevision)
            .filter_by(assessment_id=assessment.id, revision_number=assessment.revision_number)
            .one_or_none()
        )
        if current_revision is not None:
            current_revision.status = "submitted"
            current_revision.submitted_at = now
        _audit(db, assessment.id, actor_user_id=None, actor_role="worker", action="submitted")
    db.commit()
    db.refresh(assessment)
    return _assessment_out(db, assessment)


@router.post("/{assessment_id}/start-review", response_model=schemas.AssessmentOut)
def start_review(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assessor),
) -> schemas.AssessmentOut:
    """An assessor picks a submitted assessment off the queue -- moves
    submitted -> in_review and claims it (assessor_id)."""
    assessment = db.execute(select(models.Assessment).where(models.Assessment.id == assessment_id).with_for_update()).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if assessment.status != models.AssessmentStatus.submitted.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"cannot start review: assessment is '{assessment.status}', not 'submitted'"
        )

    assessment.status = models.AssessmentStatus.in_review.value
    assessment.assessor_id = user.id
    _audit(db, assessment.id, actor_user_id=user.id, actor_role=user.role, action="review_started", details={"reviewer_identity": identity(user)})
    db.commit()
    db.refresh(assessment)
    return _assessment_out(db, assessment)


@router.get("/{assessment_id}/rubric", response_model=list[schemas.RubricItemOut])
def get_assessment_rubric(
    assessment_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_assessor),
) -> list[schemas.RubricItemOut]:
    """Assessor/admin only -- the 0-3 anchors for this assessment's pack,
    for the dashboard's assessment-review page."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    rows = (
        db.query(models.RubricItem, models.PerformanceCriterion)
        .join(models.PerformanceCriterion, models.RubricItem.pc_id == models.PerformanceCriterion.id)
        .join(models.NOS, models.PerformanceCriterion.nos_id == models.NOS.id)
        .filter(models.NOS.pack_id == assessment.pack_id)
        .all()
    )
    return [
        schemas.RubricItemOut(
            pc_full_id=pc.full_id, rubric_version=item.rubric_version, marks=item.marks,
            critical=item.critical, anchors=item.anchors, disclaimer=item.disclaimer,
            evidence_hint=item.evidence_hint,
        )
        for item, pc in rows
    ]


@router.get("/{assessment_id}/sync-status", response_model=schemas.SyncStatusOut)
def get_sync_status(
    assessment_id: int,
    revision_id: str | None = None,
    db: Session = Depends(get_db),
    _auth: models.Assessment = Depends(_assessor_or_worker_token),
) -> schemas.SyncStatusOut:
    """P6: consolidated begin/recover + per-item status, so the phone's
    WorkManager worker (and the dashboard) can learn, in one call, exactly
    which declared items are missing/uploading/verified/rejected for a
    revision -- used to resolve a possibly-lost acknowledgement via server
    status rather than blindly re-uploading, and to decide which chunks (if
    any) are actually missing before resuming.

    `revision_id` is optional and defaults to the assessment's current
    (most recently ACCEPTED) revision -- but the phone always knows its own
    revision_id locally (from Room) and should pass it explicitly to check
    on a revision that was outright REJECTED (which never becomes
    "current"), e.g. right after a failed sync attempt."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    target_revision = revision_id or assessment.current_revision_id
    if not target_revision:
        return schemas.SyncStatusOut(
            assessment_id=assessment.id, assessment_status=assessment.status,
            revision_id=None, manifest_state="none", items=[], all_items_verified=False,
        )

    manifest = (
        db.query(models.DeviceManifest)
        .filter_by(assessment_id=assessment.id, revision_id=target_revision)
        .one_or_none()
    )
    if manifest is None:
        return schemas.SyncStatusOut(
            assessment_id=assessment.id, assessment_status=assessment.status,
            revision_id=target_revision, manifest_state="none", items=[], all_items_verified=False,
        )

    manifest_state = manifest.status if manifest.status in ("received", "complete", "rejected") else "none"

    items: list[schemas.SyncItemStatusOut] = []
    all_verified = manifest.status == "complete"
    for declared in manifest.declared_items:
        task = db.query(models.AssessmentTask).filter_by(
            assessment_id=assessment.id, task_code=declared["task_code"],
        ).one_or_none()
        evidence = None
        if task is not None:
            evidence = db.query(models.EvidenceItem).filter_by(
                assessment_task_id=task.id, client_evidence_id=declared["evidence_id"],
            ).one_or_none()
        session = (
            db.query(models.UploadSession)
            .filter_by(
                assessment_id=assessment.id, target="evidence",
                client_evidence_id=declared["evidence_id"], revision_id=target_revision,
            )
            .order_by(models.UploadSession.id.desc())
            .first()
        )

        if evidence is not None:
            state = "verified"
        elif session is not None and session.received_bytes > 0:
            state = "uploading"
        else:
            state = "pending"
        if state != "verified":
            all_verified = False

        items.append(schemas.SyncItemStatusOut(
            client_evidence_id=declared["evidence_id"], task_code=declared["task_code"],
            kind=declared["kind"], declared_bytes=declared["bytes"], state=state,
            received_bytes=session.received_bytes if session else None,
            upload_session_id=session.id if session else None,
            evidence_id=evidence.id if evidence else None,
            rejection_reason=session.last_rejection_reason if session else None,
        ))

    return schemas.SyncStatusOut(
        assessment_id=assessment.id, assessment_status=assessment.status,
        revision_id=target_revision, manifest_state=manifest_state,
        manifest_rejection_reason=manifest.rejection_reason, items=items,
        all_items_verified=all_verified,
    )


@router.get("/{assessment_id}/audit-log", response_model=list[schemas.AuditLogEntryOut])
def get_audit_log(
    assessment_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_assessor),
) -> list[schemas.AuditLogEntryOut]:
    """Assessor/admin only -- the full, append-only accountability trail for
    one assessment (who did what, when), including P6's sync-specific
    actions (manifest received/rejected, cross-check mismatches, package
    completion) alongside the P2.2 lifecycle/scoring/decision/report/token
    actions. Oldest first, matching the order things actually happened."""
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    rows = (
        db.query(models.AuditLog)
        .filter_by(assessment_id=assessment_id)
        .order_by(models.AuditLog.id)
        .all()
    )
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
    names = {
        u.id: u.display_name
        for u in db.query(models.User).filter(models.User.id.in_(actor_ids)).all()
    } if actor_ids else {}
    return [
        schemas.AuditLogEntryOut(
            id=r.id, actor_user_id=r.actor_user_id, actor_name=names.get(r.actor_user_id) or r.details.get("reviewer_identity", {}).get("name"),
            actor_role=r.actor_role, action=r.action, details=r.details, created_at=r.created_at,
        )
        for r in rows
    ]

import datetime
from decimal import Decimal
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceKind = Literal["photo", "video"]

# Small explicit MIME allow-list (section A.2) -- never pattern-matched/
# wildcarded, so a new MIME type requires a deliberate code change.
ALLOWED_MIME_BY_KIND: dict[str, set[str]] = {
    "photo": {"image/jpeg", "image/png", "image/webp"},
    "video": {"video/mp4", "video/webm"},
}


def _check_kind_mime(kind: str, mime: str) -> None:
    allowed = ALLOWED_MIME_BY_KIND.get(kind, set())
    if mime not in allowed:
        raise ValueError(f"mime '{mime}' is not allowed for kind '{kind}' (allowed: {sorted(allowed)})")


class HealthOut(BaseModel):
    status: str
    database: str
    storage: str


# ---- auth ----

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    display_name: str
    email: str | None


# ---- worker self-registration (P6 sync bootstrap) ----
#
# The worker app has no login (see docs/worker_capability_tokens.md) -- but it also, until P6,
# never needed a server-side identity at all (P3-P5 are fully offline). POST /workers/register
# is the one place a phone establishes that identity: idempotent on device_worker_id (the
# phone's own locally-generated "KP-XXXXXXXX" string from on-device registration), never a
# password/OTP. Deliberately public/unauthenticated, same trust model as POST /assessments
# (there is no account to authenticate against yet).

class WorkerRegisterRequest(BaseModel):
    device_worker_id: str = Field(min_length=1, max_length=60)
    display_name: str = Field(min_length=1, max_length=120)


class WorkerRegisterOut(BaseModel):
    worker_id: int


# ---- pack lookup (P6 sync bootstrap: resolve the pinned QP code/version to a pack_id) ----

class PackLookupOut(BaseModel):
    pack_id: int
    qp_code: str
    qp_version: str
    pack_version: str


# ---- assessments ----

class AssessmentCreate(BaseModel):
    worker_id: int
    pack_id: int


class AssessmentCreatedOut(BaseModel):
    """Returned once, at creation -- carries the raw worker capability token.
    Never returned again by any other endpoint."""
    id: int
    worker_id: int
    pack_id: int
    status: str
    worker_token: str
    tasks: list["AssessmentTaskOut"]


class EvidenceReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    mime: str
    declared_size_bytes: int
    sha256: str
    created_at: datetime.datetime
    thumbnail_status: str = "not_applicable"
    metadata_status: str = "not_run"
    duration_ms: int | None = None
    width_px: int | None = None
    height_px: int | None = None


class AssessmentTaskOut(BaseModel):
    task_code: str
    budget_bytes: int
    bytes_used: int
    status: str
    evidence: list[EvidenceReceiptOut] = []


class AssessmentOut(BaseModel):
    id: int
    worker_id: int
    worker_name: str
    pack_id: int
    pack_code: str
    pack_name: str
    status: str
    assessor_id: int | None = None
    total_bytes_used: int
    total_budget_bytes: int
    created_at: datetime.datetime
    submitted_at: datetime.datetime | None = None
    decision: str | None = None
    decision_notes: str | None = None
    reassessment_of_id: int | None = None
    # P6: honest, bounded declaration/match snapshot -- see
    # Assessment.declared_match_result's docstring in models.py for exactly
    # why this is a summary, not the full declaration Q&A.
    declared_match_result: str | None = None
    declared_coverage_fraction: Decimal | None = None
    declared_gap_task_codes: list[str] | None = None
    current_revision_id: str | None = None
    tasks: list[AssessmentTaskOut]


# ---- resumable uploads ----
#
# P6 extends the P2.1 single-evidence-item protocol to also carry a P5
# SignedManifestPackage envelope through the exact same open/chunk/complete
# machinery (target="manifest"), and binds every evidence-item session to
# the P5 outbox row it came from (revision_id/client_evidence_id) so a lost
# acknowledgement can be resolved via server status instead of re-uploaded
# blindly. See server/app/manifest_verify.py and routers/uploads.py.

SyncTarget = Literal["evidence", "manifest"]


class UploadSessionCreate(BaseModel):
    assessment_id: int
    target: SyncTarget = "evidence"
    task_code: str | None = None  # required for target="evidence"
    kind: EvidenceKind | None = None  # required for target="evidence"
    mime: str | None = None  # required for target="evidence"
    claimed_size_bytes: int = Field(gt=0)
    # P6 sync binding -- omit both for the pre-P6 direct-upload path (tests,
    # the docker e2e smoke script), which behaves exactly as before.
    revision_id: str | None = None
    client_evidence_id: str | None = None  # required for target="evidence" when revision_id is set

    @model_validator(mode="after")
    def _validate(self) -> "UploadSessionCreate":
        if self.target == "evidence":
            if not self.task_code:
                raise ValueError("task_code is required when target is 'evidence'")
            if not self.kind or not self.mime:
                raise ValueError("kind and mime are required when target is 'evidence'")
            _check_kind_mime(self.kind, self.mime)
            if self.revision_id and not self.client_evidence_id:
                raise ValueError("client_evidence_id is required when revision_id is set")
        else:  # manifest
            if not self.revision_id:
                raise ValueError("revision_id is required when target is 'manifest'")
            if self.task_code or self.kind or self.mime:
                raise ValueError("task_code/kind/mime must not be set when target is 'manifest'")
        return self


class UploadSessionOut(BaseModel):
    id: int
    assessment_id: int
    assessment_task_id: int | None = None
    target: SyncTarget = "evidence"
    kind: str | None = None
    mime: str | None = None
    claimed_size_bytes: int
    received_bytes: int
    next_chunk_index: int
    status: str
    opened_at: datetime.datetime
    expires_at: datetime.datetime
    revision_id: str | None = None
    client_evidence_id: str | None = None
    task_bytes_remaining: int | None = None  # None for target="manifest" (not task-scoped)
    total_bytes_remaining: int


class ChunkAck(BaseModel):
    chunk_index: int
    received_bytes: int
    next_chunk_index: int
    status: str


class UploadCompleteRequest(BaseModel):
    client_sha256: str = Field(min_length=64, max_length=64)


class UploadReceipt(BaseModel):
    session_id: int
    evidence_id: int
    sha256: str
    byte_count: int
    mime: str
    kind: str
    storage_status: Literal["stored"]
    completed_at: datetime.datetime


class ManifestReceipt(BaseModel):
    session_id: int
    manifest_id: int
    assessment_id: int
    revision_id: str
    sha256: str
    item_count: int
    declared_total_bytes: int
    status: Literal["received", "rejected"]
    rejection_reason: str | None = None
    received_at: datetime.datetime


# ---- P6 sync status (worker resume + assessor-visible progress) ----

SyncItemState = Literal["pending", "uploading", "verified", "rejected"]


class SyncItemStatusOut(BaseModel):
    client_evidence_id: str
    task_code: str
    kind: str
    declared_bytes: int
    state: SyncItemState
    received_bytes: int | None = None
    upload_session_id: int | None = None
    evidence_id: int | None = None
    rejection_reason: str | None = None


ManifestSyncState = Literal["none", "received", "complete", "rejected"]


class SyncStatusOut(BaseModel):
    assessment_id: int
    assessment_status: str
    revision_id: str | None = None
    manifest_state: ManifestSyncState = "none"
    manifest_rejection_reason: str | None = None
    items: list[SyncItemStatusOut] = []
    all_items_verified: bool = False


# ---- queue ----

class QueueItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    worker_id: int
    worker_name: str
    pack_code: str
    status: str
    created_at: datetime.datetime


# ---- rubric (assessor review) ----

class RubricItemOut(BaseModel):
    pc_full_id: str
    rubric_version: str
    marks: Decimal
    critical: bool
    anchors: dict
    disclaimer: str
    evidence_hint: str


# ---- scoring (assessor review) ----

EvidenceStatus = Literal["DEMONSTRATED", "NOT_OBSERVABLE", "NOT_APPLICABLE_IN_MVP"]


class CriterionScoreIn(BaseModel):
    pc_full_id: str
    score_level: int = Field(ge=0, le=3)
    evidence_status: EvidenceStatus
    assessor_comment: str | None = None
    # Optimistic lock: 0 means "I believe this PC has never been scored
    # before"; otherwise must equal the version last read from GET /review.
    expected_version: int = Field(ge=0)

    @model_validator(mode="after")
    def _comment_required_when_not_demonstrated(self) -> "CriterionScoreIn":
        if self.evidence_status != "DEMONSTRATED" and not (self.assessor_comment and self.assessor_comment.strip()):
            raise ValueError(
                f"assessor_comment is required when evidence_status is '{self.evidence_status}'"
            )
        return self


class CriterionScoreOut(BaseModel):
    pc_full_id: str
    score_level: int
    evidence_status: str
    assessor_comment: str | None
    marks_awarded: Decimal
    rubric_version: str
    assessor_id: int | None
    scored_at: datetime.datetime | None
    version: int


class CriterionReviewItemOut(BaseModel):
    """One rubric item merged with its current score, if any -- the review
    screen's unit of work."""
    pc_full_id: str
    rubric_version: str
    marks: Decimal
    critical: bool
    anchors: dict
    disclaimer: str
    evidence_hint: str
    score: CriterionScoreOut | None = None


class NosProfileOut(BaseModel):
    nos_code: str
    nos_title: str
    marks_awarded: Decimal
    marks_possible: Decimal
    percent: float


COMPETENCY_PROFILE_DISCLAIMER = (
    "Decision support only — final certification/recommendation remains with the human assessor."
)


class CompetencyProfileOut(BaseModel):
    assessment_id: int
    overall_marks_awarded: Decimal
    overall_marks_possible: Decimal
    overall_percent: float
    minimum_aggregate_passing_percent: int
    meets_minimum_threshold: bool
    pcs_scored: int
    pcs_total: int
    nos_breakdown: list[NosProfileOut]
    disclaimer: str = COMPETENCY_PROFILE_DISCLAIMER


# ---- signed reports ----

class SignedReportOut(BaseModel):
    assessment_id: int
    sha256: str
    signature: str
    key_id: str
    signed_at: datetime.datetime


class ReportVerifyOut(BaseModel):
    assessment_id: int
    valid: bool
    key_id: str
    signed_at: datetime.datetime


# ---- audit log (P6 review workspace) ----

class AuditLogEntryOut(BaseModel):
    id: int
    actor_user_id: int | None
    actor_name: str | None  # resolved display_name, or None for actor_role="worker"/"system"
    actor_role: str
    action: str
    details: dict
    created_at: datetime.datetime


# ---- worker token rotation/revocation ----

class WorkerTokenOut(BaseModel):
    assessment_id: int
    worker_token: str | None  # None on revoke -- there is no longer a usable raw token
    status: str


# ---- admin ----

class PackImportOut(BaseModel):
    id: int
    qp_code: str
    qp_version: str
    pack_version: str
    nos_count: int
    pc_count: int
    task_count: int

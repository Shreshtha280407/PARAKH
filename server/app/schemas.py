import datetime
from decimal import Decimal
from typing import Literal

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
    tasks: list[AssessmentTaskOut]


# ---- resumable uploads ----

class UploadSessionCreate(BaseModel):
    assessment_id: int
    task_code: str
    kind: EvidenceKind
    mime: str
    claimed_size_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def _kind_mime_match(self) -> "UploadSessionCreate":
        _check_kind_mime(self.kind, self.mime)
        return self


class UploadSessionOut(BaseModel):
    id: int
    assessment_task_id: int
    kind: str
    mime: str
    claimed_size_bytes: int
    received_bytes: int
    next_chunk_index: int
    status: str
    opened_at: datetime.datetime
    expires_at: datetime.datetime
    task_bytes_remaining: int
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

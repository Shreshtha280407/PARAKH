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
    total_bytes_used: int
    total_budget_bytes: int
    created_at: datetime.datetime
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


# ---- admin ----

class PackImportOut(BaseModel):
    id: int
    qp_code: str
    qp_version: str
    pack_version: str
    nos_count: int
    pc_count: int
    task_count: int

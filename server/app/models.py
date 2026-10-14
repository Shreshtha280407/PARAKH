"""SQLAlchemy models for the backend.

P2.1 added: Numeric rubric marks, assessor/admin auth fields, worker
capability tokens, a real resumable-upload protocol (UploadSession +
UploadChunk), and a durable jobs table. P2.2 added: lifecycle/audit,
human scoring, decisions/reassessment, signed reports, evidence serving.
P6 adds: DeviceManifest (P5 sealed-package signature/manifest verification),
revision/idempotency-key binding on UploadSession/EvidenceItem, a TOFU-pinned
device public key + declared-match snapshot on Assessment, and real
server-verified evidence metadata (width/height/duration). Still out of
scope: CV/AI quality inference -- see docs/evidence_quality_result.md.
"""
import datetime
import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class UserRole(str, enum.Enum):
    worker = "worker"
    assessor = "assessor"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    # Assessor/admin only -- workers have no login, see docs/worker_capability_tokens.md
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # P6: the worker app's own locally-generated stable identifier (e.g. "KP-A1B2C3D4",
    # generated once at on-device registration -- see apps/android's RegistrationScreen/
    # AppViewModel). Lets POST /workers/register be idempotent: the same device always
    # resolves to the same worker User row, created on first sync rather than requiring any
    # pre-provisioning. Not a credential -- no password, no OTP (see
    # docs/worker_capability_tokens.md's "no worker login" design).
    device_worker_id: Mapped[str | None] = mapped_column(String(60), unique=True, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualificationPack(Base):
    """One row per imported pack version (e.g. ae-con-q0602 v4.0-r1)."""

    __tablename__ = "qualification_packs"
    __table_args__ = (UniqueConstraint("qp_code", "qp_version", "pack_version", name="uq_pack_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    qp_code: Mapped[str] = mapped_column(String(40))
    qp_version: Mapped[str] = mapped_column(String(20))
    pack_version: Mapped[str] = mapped_column(String(40))  # rubric_id, e.g. ae-con-q0602@v4.0-r1
    qp_name: Mapped[str] = mapped_column(String(200))
    source_pdf_sha256: Mapped[str] = mapped_column(String(64))
    source_pdf_path: Mapped[str] = mapped_column(String(300))
    minimum_aggregate_passing_percent: Mapped[int] = mapped_column(Integer)
    final_evidence_budget_bytes: Mapped[int] = mapped_column(Integer)
    imported_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    nos: Mapped[list["NOS"]] = relationship(back_populates="pack", cascade="all, delete-orphan")
    tasks: Mapped[list["TaskTemplate"]] = relationship(back_populates="pack", cascade="all, delete-orphan")


class NOS(Base):
    __tablename__ = "nos"
    __table_args__ = (UniqueConstraint("pack_id", "code", name="uq_nos_pack_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("qualification_packs.id"))
    code: Mapped[str] = mapped_column(String(40))  # e.g. CON/N0602
    title: Mapped[str] = mapped_column(String(300))
    credits: Mapped[int] = mapped_column(Integer)
    theory_marks: Mapped[int] = mapped_column(Integer)
    practical_marks: Mapped[int] = mapped_column(Integer)
    weightage: Mapped[int] = mapped_column(Integer)
    practical: Mapped[bool] = mapped_column(Boolean)
    assessed_via: Mapped[str] = mapped_column(String(40))
    task_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_page: Mapped[int] = mapped_column(Integer)
    source_reference: Mapped[str] = mapped_column(Text)

    pack: Mapped[QualificationPack] = relationship(back_populates="nos")
    performance_criteria: Mapped[list["PerformanceCriterion"]] = relationship(
        back_populates="nos", cascade="all, delete-orphan"
    )


class PerformanceCriterion(Base):
    __tablename__ = "performance_criteria"
    __table_args__ = (UniqueConstraint("nos_id", "pc_code", name="uq_pc_nos_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nos_id: Mapped[int] = mapped_column(ForeignKey("nos.id"))
    pc_code: Mapped[str] = mapped_column(String(10))  # e.g. PC1
    full_id: Mapped[str] = mapped_column(String(60), index=True)  # e.g. CON/N0602.PC1
    text: Mapped[str] = mapped_column(Text)
    source_page: Mapped[int] = mapped_column(Integer)
    source_reference: Mapped[str] = mapped_column(Text)
    # see docs/evidence_status_model.md -- pack-design-time pathway, NOT proof of demonstration
    evidence_pathway: Mapped[str] = mapped_column(String(40))
    mvp_applicability: Mapped[str] = mapped_column(String(30), default="ASSESSABLE")

    nos: Mapped[NOS] = relationship(back_populates="performance_criteria")
    rubric_item: Mapped["RubricItem | None"] = relationship(back_populates="pc", uselist=False)


class RubricItem(Base):
    """0-3 anchors for a single PC. Only exists for TASK_EVIDENCE_PATHWAY PCs.

    marks is Numeric(8,2), not Integer/float: rubric.json's equal-split marks
    (e.g. 70/11 = 6.36) must survive import/read/API round-trips exactly,
    not get silently truncated to whole numbers.
    """

    __tablename__ = "rubric_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pc_id: Mapped[int] = mapped_column(ForeignKey("performance_criteria.id"), unique=True)
    rubric_version: Mapped[str] = mapped_column(String(60))
    marks: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    critical: Mapped[bool] = mapped_column(Boolean)
    anchors: Mapped[dict] = mapped_column(JSON)  # {"0": "...", "1": "...", "2": "...", "3": "..."}
    disclaimer: Mapped[str] = mapped_column(Text)
    evidence_hint: Mapped[str] = mapped_column(Text)

    pc: Mapped[PerformanceCriterion] = relationship(back_populates="rubric_item")


class TaskTemplate(Base):
    """T1-T5. Fixed five-task structure -- never extended with worker choice."""

    __tablename__ = "task_templates"
    __table_args__ = (UniqueConstraint("pack_id", "task_code", name="uq_task_pack_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("qualification_packs.id"))
    task_code: Mapped[str] = mapped_column(String(10))  # T1..T5
    title: Mapped[str] = mapped_column(String(120))
    nos_code: Mapped[str] = mapped_column(String(40))
    budget_bytes: Mapped[int] = mapped_column(Integer)
    evidence_hint: Mapped[str] = mapped_column(Text)
    step_guide: Mapped[list] = mapped_column(JSON)
    linked_pcs: Mapped[list] = mapped_column(JSON)
    task_order: Mapped[int] = mapped_column(Integer)  # 1..5, fixed, never reordered

    pack: Mapped[QualificationPack] = relationship(back_populates="tasks")


class AssessmentStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    in_review = "in_review"
    needs_reassessment = "needs_reassessment"
    recommended = "recommended"


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pack_id: Mapped[int] = mapped_column(ForeignKey("qualification_packs.id"))
    assessor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=AssessmentStatus.draft.value)
    total_bytes_used: Mapped[int] = mapped_column(Integer, default=0)
    # Opaque capability token (see docs/worker_capability_tokens.md) -- only
    # its SHA-256 is stored; the raw token is returned once, at creation.
    worker_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    # "active" | "revoked" -- a rotated/revoked token's hash still sits in
    # worker_token_hash (overwritten on rotation) but a revoked one must
    # never authorize anything again even if somehow still matched.
    worker_token_status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Decision support only -- never an official certificate (see
    # docs/evidence_status_model.md / the competency-profile disclaimer).
    # "recommended" | "needs_reassessment", set once by decide_assessment.
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set on the NEW assessment created by POST /assessments/{id}/reassess --
    # points back at the original. The original is left untouched (all its
    # data, scores, and report are preserved, never overwritten in place).
    reassessment_of_id: Mapped[int | None] = mapped_column(ForeignKey("assessments.id"), nullable=True)

    # --- P6: resumable sync (see DeviceManifest below) ---
    # Trust-on-first-use pin: the Android Keystore ECDSA public key embedded
    # in the FIRST successfully-verified manifest for this assessment is
    # pinned here. Every later manifest (a resync after discard/reopen, a
    # retried sync, etc.) must carry the exact same public key, or it is
    # rejected -- this stops a different device/key from masquerading as a
    # continuation of this assessment's evidence history even though it
    # holds a valid worker capability token (defense in depth; the token
    # already gates access, this binds *content provenance*).
    device_public_key_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Trust-on-first-use pin for the OTHER identifier space in play here: the
    # Android app's own locally-generated draft/assessment UUID, baked into
    # the manifest's signed bytes at offline seal time -- entirely unrelated
    # to this row's own integer primary key, which the server only assigns
    # once the client bootstraps (POST /assessments) at sync time, long
    # after the manifest was already signed. The FIRST successfully-verified
    # manifest's own assessmentId is pinned here; a later manifest for this
    # same server-side row carrying a different client id is rejected (see
    # manifest_verify.ParsedManifest.manifest_assessment_id).
    client_assessment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The revision_id of the manifest currently being synced/most recently
    # verified -- lets the server recognise which revision a resumed upload
    # belongs to and detect a stale/superseded one.
    current_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Honest, bounded declaration/match snapshot synced from the phone's
    # durable AssessmentDraftEntity (matchResult/overallCoverage/
    # gapTaskIdsCsv -- see apps/android DraftModels.kt). The full declaration
    # Q&A and the on-device "because" reason text are NOT persisted on the
    # phone past the live session (see docs/gates/P4.md), so they cannot be
    # synced either -- this is a known, stated P3/P4 boundary, not a P6
    # regression (see docs/gates/P6.md).
    declared_match_result: Mapped[str | None] = mapped_column(String(40), nullable=True)
    declared_coverage_fraction: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    declared_gap_task_codes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    worker: Mapped[User] = relationship(foreign_keys=[worker_id])
    assessor: Mapped[User | None] = relationship(foreign_keys=[assessor_id])
    pack: Mapped[QualificationPack] = relationship()
    tasks: Mapped[list["AssessmentTask"]] = relationship(back_populates="assessment", cascade="all, delete-orphan")


class AssessmentTask(Base):
    """One row per T1-T5 per assessment. Fixed five tasks, never substituted."""

    __tablename__ = "assessment_tasks"
    __table_args__ = (UniqueConstraint("assessment_id", "task_code", name="uq_assessment_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    task_code: Mapped[str] = mapped_column(String(10))  # T1..T5
    budget_bytes: Mapped[int] = mapped_column(Integer)
    bytes_used: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending")

    assessment: Mapped[Assessment] = relationship(back_populates="tasks")
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="assessment_task", cascade="all, delete-orphan"
    )


class EvidenceItem(Base):
    """Created ONLY after a resumable upload session successfully completes
    (exact byte count + server-computed SHA-256 verified) -- see
    UploadSession.complete flow in server/app/routers/uploads.py. Never
    created from client-declared metadata alone."""

    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("assessment_task_id", "client_evidence_id", name="uq_evidence_task_client_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_task_id: Mapped[int] = mapped_column(ForeignKey("assessment_tasks.id"))
    kind: Mapped[str] = mapped_column(String(10))  # photo | video
    mime: Mapped[str] = mapped_column(String(60))
    declared_size_bytes: Mapped[int] = mapped_column(Integer)  # == server-verified byte count
    storage_key: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))  # server-computed, never trusted from client alone
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Video only -- a background job extracts one ffmpeg frame. Photos serve
    # their own bytes directly as their thumbnail, no job needed.
    # not_applicable (photo) | queued | completed | unavailable (ffmpeg
    # missing or extraction failed -- never blocks serving the original).
    thumbnail_status: Mapped[str] = mapped_column(String(20), default="not_applicable")
    thumbnail_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Stable contract for a future CV/AI quality-check integration -- no
    # model exists or runs in this phase, see docs/evidence_quality_result.md.
    # not_run | queued | completed | unavailable.
    quality_check_status: Mapped[str] = mapped_column(String(20), default="not_run")

    # --- P6: real server-extracted metadata (ffprobe, never trusted from
    # the client manifest alone) + sealed-package binding. ---
    # not_run | queued | completed | unavailable -- same pattern as
    # thumbnail_status; a failed extraction never blocks serving the item.
    metadata_status: Mapped[str] = mapped_column(String(20), default="not_run")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # P5's revisionId and the manifest's opaque per-item evidenceId -- null
    # for evidence uploaded via the pre-P6 direct protocol (tests, old
    # clients). Set together; used to bind this row back to the exact
    # DeviceManifest entry it was verified against (see routers/uploads.py).
    revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    assessment_task: Mapped[AssessmentTask] = relationship(back_populates="evidence_items")


class UploadSession(Base):
    """Resumable upload session. Ordered-chunk protocol (see
    server/app/routers/uploads.py module docstring for the exact contract):
    chunks must be PUT in order starting at index 0; the server tracks
    next_chunk_index and received_bytes so a client can resume after a
    disconnect via GET /uploads/{id}.

    claimed_size_bytes reserves task + total quota for the lifetime of the
    session (see server/app/quota.py) -- released when the session leaves
    'open' status (completed/aborted/expired).

    P6 adds `target` ("evidence" | "manifest") so the exact same
    open/chunk/complete machinery also carries a P5 SignedManifestPackage
    envelope, and `assessment_id` (now the direct FK; assessment_task_id is
    only set for target="evidence", since a manifest session is not scoped
    to one task). `revision_id`/`client_evidence_id` bind the session back
    to the exact P5 outbox row it came from, for idempotent resume/recover.
    """

    __tablename__ = "upload_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    assessment_task_id: Mapped[int | None] = mapped_column(ForeignKey("assessment_tasks.id"), nullable=True)
    target: Mapped[str] = mapped_column(String(20), default="evidence")  # evidence | manifest
    kind: Mapped[str | None] = mapped_column(String(10), nullable=True)  # photo | video (null for target=manifest)
    mime: Mapped[str | None] = mapped_column(String(60), nullable=True)
    claimed_size_bytes: Mapped[int] = mapped_column(Integer)  # declared total, reserved at open
    received_bytes: Mapped[int] = mapped_column(Integer, default=0)
    next_chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(300))
    client_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    server_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | completed | aborted | expired
    evidence_item_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_items.id"), nullable=True)
    manifest_id: Mapped[int | None] = mapped_column(ForeignKey("device_manifests.id"), nullable=True)
    opened_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_evidence_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Set whenever a complete() cross-check against the verified manifest
    # fails (wrong hash/bytes/task binding for this evidenceId) -- cleared
    # on the next successful chunk append. Surfaced via GET
    # /assessments/{id}/sync-status so the phone (and the dashboard) can see
    # *why* an item is stuck without needing a separate audit-log read.
    last_rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessment: Mapped["Assessment"] = relationship()
    assessment_task: Mapped[AssessmentTask | None] = relationship()
    evidence_item: Mapped[EvidenceItem | None] = relationship()
    chunks: Mapped[list["UploadChunk"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class UploadChunk(Base):
    """One row per successfully received chunk -- lets GET /uploads/{id}
    report resume state without re-deriving it from the storage file."""

    __tablename__ = "upload_chunks"
    __table_args__ = (UniqueConstraint("upload_session_id", "chunk_index", name="uq_chunk_session_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_session_id: Mapped[int] = mapped_column(ForeignKey("upload_sessions.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[UploadSession] = relationship(back_populates="chunks")


class Job(Base):
    """Durable job queue, backed by PostgreSQL (SELECT ... FOR UPDATE SKIP
    LOCKED -- see server/app/jobs.py claim_job). No Redis/Celery: a few jobs
    a minute at MVP scale don't need it."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    locked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Lease/heartbeat for crash recovery (P2.2 section 9): a job stuck in
    # "running" past lease_expires_at is assumed to belong to a dead worker
    # and gets swept back to "queued" -- see jobs.recover_stale_jobs.
    lease_expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only. No code anywhere updates or deletes a row -- see
    docs/gates/P2_2.md section 1. One row per lifecycle-affecting action on
    an assessment (submit, review start, score, decision, reassessment,
    token rotation/revocation)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(20))  # worker | assessor | admin | system
    action: Mapped[str] = mapped_column(String(60))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssessmentCriterionScore(Base):
    """One row per (assessment, PC) that has a TASK_EVIDENCE_PATHWAY rubric
    item -- see docs/evidence_status_model.md. score_level is a human
    assessor's 0-3 judgement against the rubric anchors; evidence_status is
    axis 2 of that doc (DEMONSTRATED / NOT_OBSERVABLE /
    NOT_APPLICABLE_IN_MVP), never auto-derived from uploaded bytes alone.
    version is an optimistic-lock counter: a PUT must send back the version
    it last read, or it's rejected (409) -- two assessors scoring the same
    assessment at once must not silently clobber each other."""

    __tablename__ = "assessment_criterion_scores"
    __table_args__ = (UniqueConstraint("assessment_id", "pc_id", name="uq_score_assessment_pc"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    pc_id: Mapped[int] = mapped_column(ForeignKey("performance_criteria.id"))
    rubric_version: Mapped[str] = mapped_column(String(60))  # snapshot at scoring time
    score_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-3, None until scored
    evidence_status: Mapped[str] = mapped_column(String(30), default="NOT_OBSERVABLE")
    # Mandatory whenever evidence_status is NOT_OBSERVABLE or
    # NOT_APPLICABLE_IN_MVP -- enforced in schemas/routers, not the DB.
    assessor_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    marks_awarded: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    assessor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scored_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    pc: Mapped[PerformanceCriterion] = relationship()


class SignedReport(Base):
    """Tamper-evident competency profile + assessor recommendation (never an
    official NCVET/MSDE certificate). canonical_json is the exact byte
    sequence that was hashed and signed -- re-serializing the same data
    differently must never be mistaken for the signed artifact, so we store
    the literal signed bytes rather than re-deriving them from live rows."""

    __tablename__ = "signed_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), unique=True)
    canonical_json: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str] = mapped_column(Text)  # hex-encoded Ed25519 signature
    key_id: Mapped[str] = mapped_column(String(60))
    signed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceManifest(Base):
    """One row per P5 sealed-package manifest the phone has uploaded for
    this assessment -- at most one per (assessment_id, revision_id). Holds
    the exact signed envelope as received (never re-derived) so the
    recorded sha256/signature always describe literal bytes, the same
    "store the literal signed bytes" principle SignedReport already uses.

    status:
      received   -- ECDSA signature verified against the embedded public
                     key, structurally valid, TOFU key pin checked/set; the
                     declared evidence items are now known, but not all have
                     arrived/matched yet.
      complete   -- every declared evidence item has a matching, verified
                     EvidenceItem (same sha256, byte count, task binding).
                     This is the ONLY state from which the assessment may
                     move out of 'draft' via POST /assessments/{id}/submit
                     for an assessment that is using the P6 sync path (see
                     routers/assessments.py::submit_assessment).
      rejected   -- signature/structure/key-pin check failed; see
                     rejection_reason. The phone must not delete its local
                     encrypted outbox row for a rejected manifest.
      superseded -- a newer revision for the same assessment reached
                     'received' or 'complete' before this one did (e.g. the
                     worker discarded/resealed on-device after a partial
                     sync). Only possible while the assessment is still
                     'draft' -- once 'complete', no other revision can ever
                     reach 'received' for the same assessment (submit_assessment
                     requires 'draft', and uploads require 'draft' too).
    """

    __tablename__ = "device_manifests"
    __table_args__ = (
        UniqueConstraint("assessment_id", "revision_id", name="uq_manifest_assessment_revision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    revision_id: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    canonical_json: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    signature_b64: Mapped[str] = mapped_column(Text)
    algorithm: Mapped[str] = mapped_column(String(40))
    signer_key_id: Mapped[str] = mapped_column(String(100))
    signer_public_key_b64: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="received")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    declared_total_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # Parsed [{evidence_id, task_code, kind, bytes, sha256, mime, processing}, ...]
    # from canonical_json -- a cached projection for fast sync-status lookups,
    # never the source of truth (canonical_json + its verified signature is).
    declared_items: Mapped[list] = mapped_column(JSON, default=list)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

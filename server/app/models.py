"""SQLAlchemy models for the P2 backend.

Scope is deliberately narrow (master plan P2: "Backend + basic dashboard" --
pack storage, assessments/evidence metadata, upload sessions, a seeded
queue). No evidence bytes, no background jobs, no scoring/report tables yet
-- those land when the features that need them do (P2 exit test / P6-P7).
"""
import datetime
import enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
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
    """0-3 anchors for a single PC. Only exists for TASK_EVIDENCE_PATHWAY PCs."""

    __tablename__ = "rubric_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pc_id: Mapped[int] = mapped_column(ForeignKey("performance_criteria.id"), unique=True)
    rubric_version: Mapped[str] = mapped_column(String(60))
    marks: Mapped[float] = mapped_column(Integer)
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
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    """Metadata only -- no bytes. See server/app/storage.py for where bytes
    would eventually live; the upload-bytes path is explicitly out of P2
    scope."""

    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_task_id: Mapped[int] = mapped_column(ForeignKey("assessment_tasks.id"))
    kind: Mapped[str] = mapped_column(String(10))  # photo | video
    mime: Mapped[str] = mapped_column(String(60))
    declared_size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessment_task: Mapped[AssessmentTask] = relationship(back_populates="evidence_items")


class UploadSession(Base):
    """POST /uploads: opens a session and checks task budget + the 120 MB
    total quota BEFORE any bytes are accepted. Chunk PUT / complete
    endpoints are out of P2 scope (see master plan p.12 for the full
    contract this is a slice of)."""

    __tablename__ = "upload_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_task_id: Mapped[int] = mapped_column(ForeignKey("assessment_tasks.id"))
    claimed_size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | completed | aborted
    opened_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessment_task: Mapped[AssessmentTask] = relationship()

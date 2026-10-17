"""Add consent, enrollment, reviewer capabilities and identity audit snapshots.

Revision ID: d42e17a98c01
Revises: b89e72c4d010
No historical record is published, deleted or relabelled by this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "d42e17a98c01"
down_revision = "b89e72c4d010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("candidate_phone", sa.String(16), nullable=True))
    op.add_column("users", sa.Column("enrollment_secret_hash", sa.String(64), nullable=True))
    op.add_column("assessments", sa.Column("provenance", sa.String(30), nullable=False, server_default="legacy"))
    op.create_index("ix_assessments_provenance", "assessments", ["provenance"])
    op.add_column("assessments", sa.Column("enrollment_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_assessments_enrollment_id", "assessments", ["enrollment_id"])
    op.add_column("assessments", sa.Column("public_name_consent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("assessments", sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assessments", sa.Column("decision_reviewer_identity", sa.JSON(), nullable=True))
    for table in ("assessment_criterion_scores", "reassessment_requests", "signed_reports"):
        op.add_column(table, sa.Column("reviewer_identity", sa.JSON(), nullable=True))
    op.alter_column("reassessment_requests", "requested_by_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("signed_reports", "signed_by_id", existing_type=sa.Integer(), nullable=True)
    op.create_table("abuse_counters", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("count", sa.Integer(), nullable=False),
                    sa.Column("resets_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("worker_heartbeats", sa.Column("service", sa.String(30), primary_key=True),
                    sa.Column("source_sha", sa.String(40), nullable=False),
                    sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("reviewer_challenges",
                    sa.Column("id", sa.String(64), primary_key=True),
                    sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id"), nullable=False),
                    sa.Column("revision_number", sa.Integer(), nullable=False),
                    sa.Column("name", sa.String(120), nullable=False),
                    sa.Column("email", sa.String(254), nullable=False),
                    sa.Column("action", sa.String(20), nullable=False),
                    sa.Column("code_hash", sa.String(64), nullable=False),
                    sa.Column("attempts", sa.Integer(), nullable=False),
                    sa.Column("used", sa.Boolean(), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_reviewer_challenges_assessment_id", "reviewer_challenges", ["assessment_id"])
    op.create_table("reviewer_sessions",
                    sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("challenge_id", sa.String(64), sa.ForeignKey("reviewer_challenges.id"), nullable=False),
                    sa.Column("csrf_hash", sa.String(64), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    # Capability/audit records must not be silently destroyed by an application rollback.
    raise RuntimeError("Restore the previous application; retain the additive schema and audit history")

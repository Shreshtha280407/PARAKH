"""p7 versioned reassessment, computed outcome, pdf-first signed reports

Revision ID: af3b2cddce3e
Revises: 31f43e2b42be
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af3b2cddce3e'
down_revision: Union[str, Sequence[str], None] = '31f43e2b42be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'assessment_revisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('revision_id', sa.String(length=64), nullable=True),
        sa.Column('reopened_task_codes', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_assessment_revisions_assessment_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assessment_id', 'revision_number', name='uq_revision_assessment_number'),
    )
    op.create_index(
        op.f('ix_assessment_revisions_assessment_id'), 'assessment_revisions', ['assessment_id'], unique=False
    )

    op.create_table(
        'reassessment_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('revision_id', sa.Integer(), nullable=False),
        sa.Column('task_codes', sa.JSON(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('capture_instructions', sa.Text(), nullable=False),
        sa.Column('requested_by_id', sa.Integer(), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('fulfilled_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_reassessment_requests_assessment_id'),
        sa.ForeignKeyConstraint(['revision_id'], ['assessment_revisions.id'], name='fk_reassessment_requests_revision_id'),
        sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], name='fk_reassessment_requests_requested_by_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_reassessment_requests_assessment_id'), 'reassessment_requests', ['assessment_id'], unique=False
    )

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('revision_number', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('declared_match_reasons', sa.JSON(), nullable=True))
    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.alter_column('revision_number', server_default=None)

    with op.batch_alter_table('assessment_criterion_scores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('revision_number', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('assessment_criterion_scores', schema=None) as batch_op:
        batch_op.alter_column('revision_number', server_default=None)
        batch_op.alter_column('needs_review', server_default=None)

    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('device_captured_at', sa.DateTime(timezone=True), nullable=True))

    # Backfill one AssessmentRevision(revision_number=1, status derived from
    # the assessment's own current status) row per existing assessment, so
    # every assessment -- old or new -- has a revision-1 row to anchor
    # reopened-task/budget logic against. draft/submitted assessments keep
    # revision 1 "open" (still accepting evidence or already fully
    # declared); anything further along is "submitted" (its revision-1
    # manifest, if any, already completed).
    op.execute(
        "INSERT INTO assessment_revisions (assessment_id, revision_number, revision_id, reopened_task_codes, status, created_at, submitted_at) "
        "SELECT id, 1, current_revision_id, NULL, "
        "CASE WHEN status = 'draft' THEN 'open' ELSE 'submitted' END, "
        "created_at, submitted_at "
        "FROM assessments"
    )

    # signed_reports: redesigned to sign rendered PDF bytes (pdf_sha256),
    # not a JSON snapshot -- see models.SignedReport's docstring. No real
    # signed report has ever been issued outside local dev/CI demo runs (the
    # MVP has not reached a pilot deployment), so existing rows are dropped
    # rather than migrated -- they were signed under a scheme this code no
    # longer implements and could never verify under the new one anyway.
    op.execute("DELETE FROM signed_reports")

    with op.batch_alter_table('signed_reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('report_uid', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('revision_number', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('pdf_storage_key', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('pdf_sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('computed_recommendation', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('final_recommendation', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('override_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('signed_by_id', sa.Integer(), nullable=True))
        batch_op.drop_column('sha256')
    with op.batch_alter_table('signed_reports', schema=None) as batch_op:
        batch_op.alter_column('report_uid', existing_type=sa.String(length=40), nullable=False)
        batch_op.alter_column('revision_number', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('pdf_storage_key', existing_type=sa.String(length=300), nullable=False)
        batch_op.alter_column('pdf_sha256', existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column('computed_recommendation', existing_type=sa.String(length=40), nullable=False)
        batch_op.alter_column('final_recommendation', existing_type=sa.String(length=40), nullable=False)
        batch_op.alter_column('signed_by_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint('uq_signed_reports_report_uid', ['report_uid'])
        batch_op.create_foreign_key('fk_signed_reports_signed_by_id', 'users', ['signed_by_id'], ['id'])
    op.create_index(op.f('ix_signed_reports_report_uid'), 'signed_reports', ['report_uid'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_signed_reports_report_uid'), table_name='signed_reports')
    with op.batch_alter_table('signed_reports', schema=None) as batch_op:
        batch_op.drop_constraint('fk_signed_reports_signed_by_id', type_='foreignkey')
        batch_op.drop_constraint('uq_signed_reports_report_uid', type_='unique')
        batch_op.add_column(sa.Column('sha256', sa.String(length=64), nullable=True))
    op.execute("DELETE FROM signed_reports")
    with op.batch_alter_table('signed_reports', schema=None) as batch_op:
        batch_op.alter_column('sha256', existing_type=sa.String(length=64), nullable=False)
        batch_op.drop_column('signed_by_id')
        batch_op.drop_column('override_reason')
        batch_op.drop_column('final_recommendation')
        batch_op.drop_column('computed_recommendation')
        batch_op.drop_column('pdf_sha256')
        batch_op.drop_column('pdf_storage_key')
        batch_op.drop_column('revision_number')
        batch_op.drop_column('report_uid')

    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.drop_column('device_captured_at')

    with op.batch_alter_table('assessment_criterion_scores', schema=None) as batch_op:
        batch_op.drop_column('needs_review')
        batch_op.drop_column('revision_number')

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.drop_column('declared_match_reasons')
        batch_op.drop_column('revision_number')

    op.drop_index(op.f('ix_reassessment_requests_assessment_id'), table_name='reassessment_requests')
    op.drop_table('reassessment_requests')
    op.drop_index(op.f('ix_assessment_revisions_assessment_id'), table_name='assessment_revisions')
    op.drop_table('assessment_revisions')

"""p2_2 lifecycle audit scoring reports tokens

Revision ID: c1f9c6d7d164
Revises: a3f9b4e90208
Create Date: 2026-10-10 01:05:48.983141

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f9c6d7d164'
down_revision: Union[str, Sequence[str], None] = 'a3f9b4e90208'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('actor_role', sa.String(length=20), nullable=False),
        sa.Column('action', sa.String(length=60), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name='fk_audit_log_actor_user_id'),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_audit_log_assessment_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_log_assessment_id'), 'audit_log', ['assessment_id'], unique=False)

    op.create_table(
        'signed_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('canonical_json', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('signature', sa.Text(), nullable=False),
        sa.Column('key_id', sa.String(length=60), nullable=False),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_signed_reports_assessment_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assessment_id', name='uq_signed_reports_assessment_id'),
    )

    op.create_table(
        'assessment_criterion_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('pc_id', sa.Integer(), nullable=False),
        sa.Column('rubric_version', sa.String(length=60), nullable=False),
        sa.Column('score_level', sa.Integer(), nullable=True),
        sa.Column('evidence_status', sa.String(length=30), nullable=False),
        sa.Column('assessor_comment', sa.Text(), nullable=True),
        sa.Column('marks_awarded', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('assessor_id', sa.Integer(), nullable=True),
        sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_acs_assessment_id'),
        sa.ForeignKeyConstraint(['assessor_id'], ['users.id'], name='fk_acs_assessor_id'),
        sa.ForeignKeyConstraint(['pc_id'], ['performance_criteria.id'], name='fk_acs_pc_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assessment_id', 'pc_id', name='uq_score_assessment_pc'),
    )
    op.create_index(
        op.f('ix_assessment_criterion_scores_assessment_id'), 'assessment_criterion_scores', ['assessment_id'], unique=False
    )

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('worker_token_status', sa.String(length=20), nullable=False, server_default='active'))
        batch_op.add_column(sa.Column('decision', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('decision_notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('decided_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('reassessment_of_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_assessments_decided_by_id', 'users', ['decided_by_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_assessments_reassessment_of_id', 'assessments', ['reassessment_of_id'], ['id']
        )
    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.alter_column('worker_token_status', server_default=None)

    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thumbnail_status', sa.String(length=20), nullable=False, server_default='not_applicable'))
        batch_op.add_column(sa.Column('thumbnail_key', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('quality_check_status', sa.String(length=20), nullable=False, server_default='not_run'))
    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.alter_column('thumbnail_status', server_default=None)
        batch_op.alter_column('quality_check_status', server_default=None)

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('lease_expires_at')

    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.drop_column('quality_check_status')
        batch_op.drop_column('thumbnail_key')
        batch_op.drop_column('thumbnail_status')

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_assessments_reassessment_of_id', type_='foreignkey')
        batch_op.drop_constraint('fk_assessments_decided_by_id', type_='foreignkey')
        batch_op.drop_column('reassessment_of_id')
        batch_op.drop_column('decided_at')
        batch_op.drop_column('decided_by_id')
        batch_op.drop_column('decision_notes')
        batch_op.drop_column('decision')
        batch_op.drop_column('worker_token_status')

    op.drop_index(op.f('ix_assessment_criterion_scores_assessment_id'), table_name='assessment_criterion_scores')
    op.drop_table('assessment_criterion_scores')
    op.drop_table('signed_reports')
    op.drop_index(op.f('ix_audit_log_assessment_id'), table_name='audit_log')
    op.drop_table('audit_log')

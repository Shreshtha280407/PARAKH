"""p6 resumable sync device manifest

Revision ID: 8bba80863fec
Revises: c1f9c6d7d164
Create Date: 2026-10-12 20:10:06.731197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bba80863fec'
down_revision: Union[str, Sequence[str], None] = 'c1f9c6d7d164'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Batch mode throughout for any ALTER on an existing table (SQLite recreates
# the table under the hood; harmless no-op wrapping on Postgres) -- same
# convention as a3f9b4e90208/c1f9c6d7d164.


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'device_manifests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assessment_id', sa.Integer(), nullable=False),
        sa.Column('revision_id', sa.String(length=64), nullable=False),
        sa.Column('idempotency_key', sa.String(length=140), nullable=False),
        sa.Column('canonical_json', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('signature_b64', sa.Text(), nullable=False),
        sa.Column('algorithm', sa.String(length=40), nullable=False),
        sa.Column('signer_key_id', sa.String(length=100), nullable=False),
        sa.Column('signer_public_key_b64', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('item_count', sa.Integer(), nullable=False),
        sa.Column('declared_total_bytes', sa.Integer(), nullable=False),
        sa.Column('declared_items', sa.JSON(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_device_manifests_assessment_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assessment_id', 'revision_id', name='uq_manifest_assessment_revision'),
        sa.UniqueConstraint('idempotency_key', name='uq_device_manifests_idempotency_key'),
    )
    op.create_index(op.f('ix_device_manifests_assessment_id'), 'device_manifests', ['assessment_id'], unique=False)
    op.create_index(op.f('ix_device_manifests_idempotency_key'), 'device_manifests', ['idempotency_key'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('device_worker_id', sa.String(length=60), nullable=True))
        batch_op.create_unique_constraint('uq_users_device_worker_id', ['device_worker_id'])

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('device_public_key_b64', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('current_revision_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('declared_match_result', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('declared_coverage_fraction', sa.Numeric(precision=5, scale=4), nullable=True))
        batch_op.add_column(sa.Column('declared_gap_task_codes', sa.JSON(), nullable=True))

    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('metadata_status', sa.String(length=20), nullable=False, server_default='not_run'))
        batch_op.add_column(sa.Column('duration_ms', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('width_px', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('height_px', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('revision_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('client_evidence_id', sa.String(length=64), nullable=True))
    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.alter_column('metadata_status', server_default=None)
        batch_op.create_unique_constraint(
            'uq_evidence_task_client_id', ['assessment_task_id', 'client_evidence_id']
        )

    # upload_sessions gains a direct assessment_id FK (previously only
    # reachable via assessment_task_id) so a "manifest" target session,
    # which has no task, can still be scoped to an assessment. Add it
    # nullable, backfill from the existing task relationship, then tighten
    # to NOT NULL -- the same backfill-then-constrain dance the
    # worker_token_hash column used in a3f9b4e90208.
    with op.batch_alter_table('upload_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assessment_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('target', sa.String(length=20), nullable=False, server_default='evidence'))
        batch_op.add_column(sa.Column('manifest_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('revision_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('client_evidence_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('last_rejection_reason', sa.Text(), nullable=True))
        batch_op.alter_column('kind', existing_type=sa.VARCHAR(length=10), nullable=True)
        batch_op.alter_column('mime', existing_type=sa.VARCHAR(length=60), nullable=True)
        batch_op.alter_column('assessment_task_id', existing_type=sa.INTEGER(), nullable=True)

    op.execute(
        "UPDATE upload_sessions SET assessment_id = ("
        "  SELECT assessment_tasks.assessment_id FROM assessment_tasks"
        "  WHERE assessment_tasks.id = upload_sessions.assessment_task_id"
        ")"
        " WHERE assessment_task_id IS NOT NULL"
    )

    with op.batch_alter_table('upload_sessions', schema=None) as batch_op:
        batch_op.alter_column('assessment_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('target', server_default=None)
        batch_op.create_foreign_key(
            'fk_upload_sessions_assessment_id', 'assessments', ['assessment_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_upload_sessions_manifest_id', 'device_manifests', ['manifest_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('upload_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_upload_sessions_manifest_id', type_='foreignkey')
        batch_op.drop_constraint('fk_upload_sessions_assessment_id', type_='foreignkey')
        batch_op.alter_column('assessment_task_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.alter_column('mime', existing_type=sa.VARCHAR(length=60), nullable=False)
        batch_op.alter_column('kind', existing_type=sa.VARCHAR(length=10), nullable=False)
        batch_op.drop_column('last_rejection_reason')
        batch_op.drop_column('client_evidence_id')
        batch_op.drop_column('revision_id')
        batch_op.drop_column('manifest_id')
        batch_op.drop_column('target')
        batch_op.drop_column('assessment_id')

    with op.batch_alter_table('evidence_items', schema=None) as batch_op:
        batch_op.drop_constraint('uq_evidence_task_client_id', type_='unique')
        batch_op.drop_column('client_evidence_id')
        batch_op.drop_column('revision_id')
        batch_op.drop_column('height_px')
        batch_op.drop_column('width_px')
        batch_op.drop_column('duration_ms')
        batch_op.drop_column('metadata_status')

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.drop_column('declared_gap_task_codes')
        batch_op.drop_column('declared_coverage_fraction')
        batch_op.drop_column('declared_match_result')
        batch_op.drop_column('current_revision_id')
        batch_op.drop_column('device_public_key_b64')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_device_worker_id', type_='unique')
        batch_op.drop_column('device_worker_id')

    op.drop_index(op.f('ix_device_manifests_idempotency_key'), table_name='device_manifests')
    op.drop_index(op.f('ix_device_manifests_assessment_id'), table_name='device_manifests')
    op.drop_table('device_manifests')

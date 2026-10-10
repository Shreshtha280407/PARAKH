"""p2_1 auth, resumable uploads, jobs, numeric marks

Revision ID: a3f9b4e90208
Revises: ef0c3dd21d2a
Create Date: 2026-10-09 23:19:04.729455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9b4e90208'
down_revision: Union[str, Sequence[str], None] = 'ef0c3dd21d2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Batch mode throughout: SQLite can't ALTER COLUMN TYPE, SET NOT NULL, or
# ADD a FOREIGN KEY constraint to an existing table in place -- it recreates
# the table under the hood instead. Harmless on Postgres, which just runs
# the direct ALTER statements within the same "batch".


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=60), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('locked_by', sa.String(length=100), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.String(length=200), nullable=True))

    with op.batch_alter_table('assessments') as batch_op:
        batch_op.add_column(sa.Column('worker_token_hash', sa.String(length=64), nullable=False, server_default=''))
    with op.batch_alter_table('assessments') as batch_op:
        batch_op.alter_column('worker_token_hash', server_default=None)
    op.create_index(op.f('ix_assessments_worker_token_hash'), 'assessments', ['worker_token_hash'], unique=False)

    with op.batch_alter_table('evidence_items') as batch_op:
        batch_op.alter_column('storage_key', existing_type=sa.VARCHAR(length=300), nullable=False)
        batch_op.alter_column('sha256', existing_type=sa.VARCHAR(length=64), nullable=False)

    with op.batch_alter_table('rubric_items') as batch_op:
        batch_op.alter_column(
            'marks', existing_type=sa.INTEGER(), type_=sa.Numeric(precision=8, scale=2), existing_nullable=False
        )

    with op.batch_alter_table('upload_sessions') as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=10), nullable=False, server_default='photo'))
        batch_op.add_column(sa.Column('mime', sa.String(length=60), nullable=False, server_default='image/jpeg'))
        batch_op.add_column(sa.Column('received_bytes', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('next_chunk_index', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('storage_key', sa.String(length=300), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('client_sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('server_sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('evidence_item_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column(
            'expires_at', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            'fk_upload_sessions_evidence_item_id', 'evidence_items', ['evidence_item_id'], ['id']
        )
    # Drop the placeholder server_defaults used only to satisfy NOT NULL
    # while the columns were empty -- the ORM always supplies real values
    # going forward.
    with op.batch_alter_table('upload_sessions') as batch_op:
        batch_op.alter_column('kind', server_default=None)
        batch_op.alter_column('mime', server_default=None)
        batch_op.alter_column('received_bytes', server_default=None)
        batch_op.alter_column('next_chunk_index', server_default=None)
        batch_op.alter_column('storage_key', server_default=None)
        batch_op.alter_column('expires_at', server_default=None)

    op.create_table('upload_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('upload_session_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['upload_session_id'], ['upload_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('upload_session_id', 'chunk_index', name='uq_chunk_session_index'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('upload_chunks')

    with op.batch_alter_table('upload_sessions') as batch_op:
        batch_op.drop_constraint('fk_upload_sessions_evidence_item_id', type_='foreignkey')
        batch_op.drop_column('completed_at')
        batch_op.drop_column('expires_at')
        batch_op.drop_column('evidence_item_id')
        batch_op.drop_column('server_sha256')
        batch_op.drop_column('client_sha256')
        batch_op.drop_column('storage_key')
        batch_op.drop_column('next_chunk_index')
        batch_op.drop_column('received_bytes')
        batch_op.drop_column('mime')
        batch_op.drop_column('kind')

    with op.batch_alter_table('rubric_items') as batch_op:
        batch_op.alter_column(
            'marks', existing_type=sa.Numeric(precision=8, scale=2), type_=sa.INTEGER(), existing_nullable=False
        )

    with op.batch_alter_table('evidence_items') as batch_op:
        batch_op.alter_column('sha256', existing_type=sa.VARCHAR(length=64), nullable=True)
        batch_op.alter_column('storage_key', existing_type=sa.VARCHAR(length=300), nullable=True)

    op.drop_index(op.f('ix_assessments_worker_token_hash'), table_name='assessments')
    with op.batch_alter_table('assessments') as batch_op:
        batch_op.drop_column('worker_token_hash')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('password_hash')

    op.drop_table('jobs')

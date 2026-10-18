"""Add self-registered assessor accounts and server-side password sessions.

Revision ID: e53a28c09b12
Revises: d42e17a98c01
"""
from alembic import op
import sqlalchemy as sa

revision = "e53a28c09b12"
down_revision = "d42e17a98c01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("reviewer_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("phone", sa.String(16), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("reviewer_account_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("reviewer_accounts.id"), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_reviewer_account_sessions_account_id", "reviewer_account_sessions", ["account_id"])


def downgrade():
    raise RuntimeError("Retain assessor accounts and audit history when rolling back the application")

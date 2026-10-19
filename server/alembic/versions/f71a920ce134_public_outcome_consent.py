"""Explicit, default-off consent for public final-outcome publication.

Revision ID: f71a920ce134
Revises: e53a28c09b12
No historical reports, decisions or names are rewritten or backfilled.
"""
from alembic import op
import sqlalchemy as sa

revision = "f71a920ce134"
down_revision = "e53a28c09b12"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assessments", sa.Column("public_outcome_consent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("assessments", sa.Column("public_outcome_consent_version", sa.String(30), nullable=True))
    op.add_column("assessments", sa.Column("public_outcome_consent_recorded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError("Retain candidate consent records; roll back application code without deleting consent history")

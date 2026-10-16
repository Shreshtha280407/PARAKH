"""P8 signed per-evidence assistance snapshot (additive).

Revision ID: b89e72c4d010
Revises: af3b2cddce3e
"""
from alembic import op
import sqlalchemy as sa

revision = "b89e72c4d010"
down_revision = "af3b2cddce3e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("evidence_items", sa.Column("assistance", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("evidence_items", "assistance")

"""p6 client assessment id pin

Revision ID: 31f43e2b42be
Revises: 8bba80863fec
Create Date: 2026-10-13 19:11:36.921261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31f43e2b42be'
down_revision: Union[str, Sequence[str], None] = '8bba80863fec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.add_column(sa.Column("client_assessment_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.drop_column("client_assessment_id")

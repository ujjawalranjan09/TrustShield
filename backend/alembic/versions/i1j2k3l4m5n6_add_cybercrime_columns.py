"""Add cybercrime columns to recovery_cases

Revision ID: i1j2k3l4m5n6
Revises: h1i2j3k4l5m6
Create Date: 2026-06-19 22:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recovery_cases",
        sa.Column("cybercrime_ref_number", sa.String(50), nullable=True),
    )
    op.add_column(
        "recovery_cases",
        sa.Column("cybercrime_submitted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "recovery_cases",
        sa.Column("cybercrime_submission_receipt", sa.Text(), nullable=True),
    )
    op.add_column(
        "recovery_cases",
        sa.Column("cybercrime_status", sa.String(20), server_default="not_submitted"),
    )


def downgrade() -> None:
    op.drop_column("recovery_cases", "cybercrime_status")
    op.drop_column("recovery_cases", "cybercrime_submission_receipt")
    op.drop_column("recovery_cases", "cybercrime_submitted_at")
    op.drop_column("recovery_cases", "cybercrime_ref_number")
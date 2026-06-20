"""add missing columns to flagged_entities

Revision ID: d1f44ae5a7b8
Revises: e1f2a3b4c5d6
Create Date: 2026-06-19 17:42:50.493197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1f44ae5a7b8'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: the source/region/pincode/latitude/longitude columns on
    # flagged_entities were already added by revision b1c2d3e4f5a6.
    # Re-adding them here would raise "column already exists" on a fresh DB.
    # This migration now only recreates the feedback_labels table to match
    # the FeedbackLabel model (the old schema used boolean analyst_label).

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "feedback_labels" in inspector.get_table_names():
        op.drop_table("feedback_labels")
    op.create_table(
        "feedback_labels",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.String(100), index=True, nullable=False),
        sa.Column("original_risk_score", sa.Integer()),
        sa.Column("original_risk_level", sa.String(20)),
        sa.Column("original_action", sa.String(30)),
        sa.Column("analyst_label", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("analyst_email", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Restore the legacy feedback_labels schema
    op.drop_table("feedback_labels")
    op.create_table(
        "feedback_labels",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.String(100), index=True, nullable=False),
        sa.Column("original_text", sa.Text()),
        sa.Column("predicted_scam", sa.Boolean()),
        sa.Column("predicted_confidence", sa.Integer()),
        sa.Column("predicted_scam_type", sa.String(50)),
        sa.Column("analyst_label", sa.Boolean(), nullable=False),
        sa.Column("analyst_scam_type", sa.String(50)),
        sa.Column("analyst_notes", sa.Text()),
        sa.Column("analyst_user_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

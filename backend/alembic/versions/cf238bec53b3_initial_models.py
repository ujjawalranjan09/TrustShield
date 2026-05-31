"""initial models

Revision ID: cf238bec53b3
Revises:
Create Date: 2026-05-30 23:45:07.718420

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cf238bec53b3"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # fraud_sessions table
    op.create_table(
        "fraud_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("session_id", sa.String(), unique=True, index=True),
        sa.Column("risk_score", sa.Integer()),
        sa.Column("risk_level", sa.String()),
        sa.Column("action_taken", sa.String()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # risk_events table
    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("fraud_sessions.session_id"),
            index=True,
        ),
        sa.Column("event_type", sa.String()),
        sa.Column("details", sa.String()),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.func.now()),
    )

    # flagged_entities table (community scammer database)
    op.create_table(
        "flagged_entities",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "entity_value", sa.String(255), unique=True, index=True, nullable=False
        ),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("scam_type", sa.String(100)),
        sa.Column("description", sa.Text()),
        sa.Column("report_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_confirmed", sa.Integer(), server_default="0"),
        sa.Column("first_reported", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(), server_default=sa.func.now()),
    )

    # entity_reports table (individual report submissions)
    op.create_table(
        "entity_reports",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("report_id", sa.String(36), unique=True, index=True, nullable=False),
        sa.Column(
            "entity_id", sa.Integer(), sa.ForeignKey("flagged_entities.id"), index=True
        ),
        sa.Column("reporter_contact", sa.String(255)),
        sa.Column("scam_type", sa.String(100)),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("entity_reports")
    op.drop_table("flagged_entities")
    op.drop_table("risk_events")
    op.drop_table("fraud_sessions")

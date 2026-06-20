"""add model_params and drift_log tables

Revision ID: a1b2c3d4e5f6
Revises: cf238bec53b3
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "cf238bec53b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_params",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("model_version", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("transformer_weight", sa.Float(), server_default="0.6"),
        sa.Column("gbm_weight", sa.Float(), server_default="0.4"),
        sa.Column("ensemble_weights", sa.String(500), server_default="{}"),
        sa.Column("feature_weights", sa.String(1000), server_default="{}"),
        sa.Column("transformer_f1", sa.Float(), nullable=True),
        sa.Column("gbm_f1", sa.Float(), nullable=True),
        sa.Column("ensemble_f1", sa.Float(), nullable=True),
        sa.Column("gold_set_f1", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "drift_log",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("model_version", sa.String(50), nullable=False, index=True),
        sa.Column("feature_name", sa.String(100), nullable=False, index=True),
        sa.Column("psi_value", sa.Float(), nullable=False),
        sa.Column("alert_triggered", sa.Boolean(), server_default="false"),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_drift_log_feature_timestamp", "drift_log", ["feature_name", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_drift_log_feature_timestamp", "drift_log")
    op.drop_table("drift_log")
    op.drop_table("model_params")

"""add refresh token rotation and session revocation

Revision ID: f1a2b3c4d5e6
Revises: d1f44ae5a7b8
Create Date: 2026-06-19 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d1f44ae5a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Refresh tokens table for rotation and reuse detection
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("token_jti", sa.String(36), unique=True, index=True, nullable=False),
        sa.Column("family_id", sa.String(36), nullable=False, index=True),
        sa.Column("is_rotated", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_revoked", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )

    # Revoked sessions table for token revocation
    op.create_table(
        "revoked_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("token_jti", sa.String(36), unique=True, index=True, nullable=False),
        sa.Column("token_type", sa.String(20), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("revoked_sessions")
    op.drop_table("refresh_tokens")

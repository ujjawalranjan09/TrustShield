"""add fraud_rings, investigation_cases, geo columns

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # fraud_rings table
    op.create_table(
        "fraud_rings",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("ring_id", sa.String(36), unique=True, nullable=False, index=True),
        sa.Column("entity_count", sa.Integer(), server_default="0"),
        sa.Column("total_reports", sa.Integer(), server_default="0"),
        sa.Column("top_scam_type", sa.String(100), nullable=True),
        sa.Column("risk_level", sa.String(20), server_default="low"),
        sa.Column("avg_pagerank", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(20), server_default="new"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # investigation_cases table
    op.create_table(
        "investigation_cases",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("case_id", sa.String(36), unique=True, nullable=False, index=True),
        sa.Column("ring_id", sa.String(36), nullable=True, index=True),
        sa.Column("source", sa.String(20), server_default="ring_detection"),
        sa.Column("assigned_analyst_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("priority", sa.String(20), server_default="high"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Geo columns on flagged_entities
    op.add_column("flagged_entities", sa.Column("source", sa.String(50), server_default="user_report"))
    op.add_column("flagged_entities", sa.Column("region", sa.String(100), nullable=True))
    op.add_column("flagged_entities", sa.Column("pincode", sa.String(10), nullable=True))
    op.add_column("flagged_entities", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("flagged_entities", sa.Column("longitude", sa.Float(), nullable=True))
    op.create_index("ix_flagged_entities_region", "flagged_entities", ["region"])


def downgrade() -> None:
    op.drop_index("ix_flagged_entities_region", "flagged_entities")
    op.drop_column("flagged_entities", "longitude")
    op.drop_column("flagged_entities", "latitude")
    op.drop_column("flagged_entities", "pincode")
    op.drop_column("flagged_entities", "region")
    op.drop_column("flagged_entities", "source")
    op.drop_table("investigation_cases")
    op.drop_table("fraud_rings")

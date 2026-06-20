"""add tenants and tenant_id

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-06-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "j1k2l3m4n5o6"
down_revision = "i1j2k3l4m5n6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="bank"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("data_region", sa.String(20), nullable=False, server_default="ap-south-1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Tables that get tenant_id column
    tenant_scoped_tables = [
        "scan_events",
        "revoked_sessions",
        "feedback_labels",
        "billing_subscriptions",
        "billing_usage_ledger",
        "billing_usage_events",
        "recovery_cases",
        "intervention_logs",
        "shadow_predictions",
        "behavioral_signals",
        "intel_banks",
        "users",
    ]

    for table in tenant_scoped_tables:
        op.add_column(table, sa.Column("tenant_id", sa.String(36), nullable=True, index=True))

    # Backfill: Bank rows -> tenant_id = bank_id
    op.execute(
        "UPDATE intel_banks SET tenant_id = bank_id WHERE tenant_id IS NULL"
    )
    # Backfill: User rows -> tenant_id = 'platform'
    op.execute(
        "UPDATE users SET tenant_id = 'platform' WHERE tenant_id IS NULL"
    )
    # Backfill: scan_events via session -> leave NULL for now (no direct link)
    # Backfill: revoked_sessions -> use user's tenant_id
    op.execute(
        "UPDATE revoked_sessions SET tenant_id = (SELECT tenant_id FROM users WHERE users.id = revoked_sessions.user_id) "
        "WHERE tenant_id IS NULL"
    )
    # Backfill: feedback_labels -> leave NULL (no user FK)
    # Backfill: billing_subscriptions -> use bank's tenant_id
    op.execute(
        "UPDATE billing_subscriptions SET tenant_id = (SELECT tenant_id FROM intel_banks WHERE intel_banks.bank_id = billing_subscriptions.bank_id) "
        "WHERE tenant_id IS NULL AND bank_id IS NOT NULL"
    )

    # Composite unique constraint on scan_events
    op.create_unique_constraint(
        "uq_scan_events_tenant_session",
        "scan_events",
        ["tenant_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_scan_events_tenant_session", "scan_events", type_="unique")

    tenant_scoped_tables = [
        "users",
        "intel_banks",
        "behavioral_signals",
        "shadow_predictions",
        "intervention_logs",
        "recovery_cases",
        "billing_usage_events",
        "billing_usage_ledger",
        "billing_subscriptions",
        "feedback_labels",
        "revoked_sessions",
        "scan_events",
    ]

    for table in tenant_scoped_tables:
        op.drop_column(table, "tenant_id")

    op.drop_table("tenants")

"""add billing tables

Revision ID: g1h2i3j4k5l6
Revises: f2b3c4d5e6f7
Create Date: 2026-06-19 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Plans
    op.create_table(
        "billing_plans",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column(
            "monthly_scan_limit", sa.Integer(),
            nullable=False, server_default="1000",
        ),
        sa.Column(
            "monthly_webhook_limit", sa.Integer(),
            nullable=False, server_default="100",
        ),
        sa.Column("price_id_stripe", sa.String(100), nullable=True),
        sa.Column("sla_percent", sa.Float(), server_default="99.5"),
        sa.Column("features_json", sa.Text(), server_default="{}"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
    )

    # Subscriptions
    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("bank_id", sa.String(36), index=True, nullable=True),
        sa.Column("user_id", sa.Integer(), index=True, nullable=True),
        sa.Column("plan_code", sa.String(20), nullable=False),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Usage Ledger (monthly roll-up)
    op.create_table(
        "billing_usage_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False, index=True),
        sa.Column("bucket", sa.String(20), nullable=False),
        sa.Column("scan_calls", sa.Integer(), server_default="0"),
        sa.Column("webhook_calls", sa.Integer(), server_default="0"),
        sa.Column("last_call_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "subscription_id", "bucket",
            name="uq_usage_ledger_sub_bucket",
        ),
    )

    # Usage Events (raw, append-only)
    op.create_table(
        "billing_usage_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False, index=True),
        sa.Column("endpoint", sa.String(50), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Seed default plans
    plans_table = sa.table(
        "billing_plans",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("monthly_scan_limit", sa.Integer),
        sa.column("monthly_webhook_limit", sa.Integer),
        sa.column("sla_percent", sa.Float),
        sa.column("features_json", sa.Text),
    )
    op.bulk_insert(
        plans_table,
        [
            {
                "code": "free", "name": "Free",
                "monthly_scan_limit": 1000, "monthly_webhook_limit": 100,
                "sla_percent": 99.5,
                "features_json": '{"keyword_only": true}',
            },
            {
                "code": "pro", "name": "Pro",
                "monthly_scan_limit": 50000, "monthly_webhook_limit": 10000,
                "sla_percent": 99.5,
                "features_json": '{"ml_model": true}',
            },
            {
                "code": "bank", "name": "Bank",
                "monthly_scan_limit": 1000000, "monthly_webhook_limit": 500000,
                "sla_percent": 99.9,
                "features_json": '{"webhook": true, "sso": true}',
            },
            {
                "code": "enterprise", "name": "Enterprise",
                "monthly_scan_limit": -1, "monthly_webhook_limit": -1,
                "sla_percent": 99.95,
                "features_json": '{"on_prem": true}',
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("billing_usage_events")
    op.drop_table("billing_usage_ledger")
    op.drop_table("billing_subscriptions")
    op.drop_table("billing_plans")

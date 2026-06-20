"""Billing models — Plans, Subscriptions, Usage Ledger, Usage Events."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)

from app.database import Base


class Plan(Base):
    """Billing plan with tier limits."""

    __tablename__ = "billing_plans"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False)  # free|pro|bank|enterprise
    name = Column(String(50), nullable=False)
    monthly_scan_limit = Column(Integer, nullable=False, default=1000)  # -1 = unlimited
    monthly_webhook_limit = Column(Integer, nullable=False, default=100)
    price_id_stripe = Column(String(100), nullable=True)
    sla_percent = Column(Float, default=99.5)
    features_json = Column(Text, default="{}")
    is_active = Column(Boolean, default=True)


class Subscription(Base):
    """Active subscription for a bank or user."""

    __tablename__ = "billing_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    bank_id = Column(String(36), index=True, nullable=True)
    user_id = Column(Integer, index=True, nullable=True)
    plan_code = Column(String(20), nullable=False)
    stripe_customer_id = Column(String(100), nullable=True)
    stripe_subscription_id = Column(String(100), nullable=True)
    status = Column(String(20), default="active")  # trialing|active|past_due|canceled
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class UsageLedger(Base):
    """Monthly roll-up of API usage per subscription."""

    __tablename__ = "billing_usage_ledger"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    subscription_id = Column(Integer, nullable=False, index=True)
    bucket = Column(String(20), nullable=False)  # "YYYY-MM"
    scan_calls = Column(Integer, default=0)
    webhook_calls = Column(Integer, default=0)
    last_call_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "bucket", name="uq_usage_ledger_sub_bucket"
        ),
    )


class UsageEvent(Base):
    """Raw per-call event log for dispute resolution. Append-only."""

    __tablename__ = "billing_usage_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    subscription_id = Column(Integer, nullable=False, index=True)
    endpoint = Column(String(50), nullable=False)  # analyze|webhook
    session_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

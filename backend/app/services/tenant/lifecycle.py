"""Tenant lifecycle — provisioning and offboarding."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)


async def provision_tenant(
    slug: str,
    tier: str,
    display_name: str,
    region: str,
    db: AsyncSession,
) -> Tenant:
    """Create a new Tenant, default admin User, and seed built-in roles."""
    tenant = Tenant(
        slug=slug,
        display_name=display_name,
        tier=tier,
        data_region=region,
    )
    db.add(tenant)
    await db.flush()

    # Create default admin user
    admin_email = f"admin-{slug}@trustshield.local"
    admin_user = User(
        tenant_id=tenant.tenant_id,
        email=admin_email,
        hashed_password="!",  # Must be set via invite flow
        full_name=f"{display_name} Admin",
        role="org_admin",
    )
    db.add(admin_user)

    # Seed built-in roles
    from app.models.auth import Role
    builtin_roles = [
        ("tenant_admin", '["SCAN_READ","SCAN_ANALYZE","REPORT_CREATE","RECOVERY_READ","RECOVERY_WRITE","INTERVENTION_SEND","MODEL_PROMOTE","BILLING_MANAGE","AUDIT_READ","TENANT_ADMIN"]'),
        ("analyst", '["SCAN_READ","SCAN_ANALYZE","REPORT_CREATE","RECOVERY_READ","INTERVENTION_SEND"]'),
        ("viewer", '["SCAN_READ","REPORT_CREATE"]'),
        ("compliance_officer", '["AUDIT_READ","RECOVERY_READ"]'),
    ]
    for role_name, perms in builtin_roles:
        db.add(Role(
            tenant_id=tenant.tenant_id,
            name=role_name,
            permissions=perms,
            is_builtin=True,
        ))

    await db.commit()
    logger.info("Provisioned tenant %s (id=%s)", slug, tenant.tenant_id)
    return tenant


async def offboard_tenant(tenant_id: str, db: AsyncSession) -> None:
    """Mark tenant as offboarding, then delete rows (except recovery_cases)."""
    result = await db.execute(select(Tenant).filter(Tenant.tenant_id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise ValueError(f"Tenant {tenant_id} not found")

    tenant.status = "offboarding"
    await db.flush()
    logger.info("Tenant %s marked offboarding", tenant_id)

    # Delete tenant-scoped rows (except recovery_cases which have 7yr retention)
    from app.models.scan_event import ScanEvent
    from app.models.session import RevokedSession
    from app.models.feedback import FeedbackLabel
    from app.models.billing import Subscription, UsageLedger, UsageEvent
    from app.models.intervention import InterventionLog
    from app.models.shadow_prediction import ShadowPrediction
    from app.models.behavioral_signal import BehavioralSignal
    from app.models.intel import Bank
    from app.models.user import User
    from app.models.auth import Role, UserRole

    for model in [ScanEvent, RevokedSession, FeedbackLabel, Subscription,
                  UsageLedger, UsageEvent, InterventionLog, ShadowPrediction,
                  BehavioralSignal, Bank, User, Role, UserRole]:
        from sqlalchemy import delete
        await db.execute(delete(model).where(model.tenant_id == tenant_id))

    # Delete tenant itself (recovery_cases preserved for 7yr retention)
    await db.execute(
        __import__("sqlalchemy").delete(Tenant).where(Tenant.tenant_id == tenant_id)
    )
    await db.commit()
    logger.info("Offboarded tenant %s (recovery_cases retained)", tenant_id)

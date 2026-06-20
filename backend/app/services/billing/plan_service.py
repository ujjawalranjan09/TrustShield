"""Plan lookup and subscription resolution."""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Plan, Subscription

logger = logging.getLogger(__name__)


async def get_plan_by_code(db: AsyncSession, code: str) -> Optional[Plan]:
    """Look up a plan by its code (free, pro, bank, enterprise)."""
    result = await db.execute(select(Plan).filter(Plan.code == code, Plan.is_active))
    return result.scalars().first()


async def resolve_subscription(
    db: AsyncSession, *, bank_id: Optional[str] = None, user_id: Optional[int] = None
) -> Optional[Subscription]:
    """Resolve the active subscription for a bank or user."""
    query = select(Subscription).filter(Subscription.status.in_(["active", "trialing"]))
    if bank_id:
        query = query.filter(Subscription.bank_id == bank_id)
    elif user_id:
        query = query.filter(Subscription.user_id == user_id)
    else:
        return None
    query = query.order_by(Subscription.created_at.desc())
    result = await db.execute(query)
    return result.scalars().first()


async def get_effective_limits(
    db: AsyncSession, *, bank_id: Optional[str] = None, user_id: Optional[int] = None
) -> dict:
    """Return the effective plan limits for a caller."""
    sub = await resolve_subscription(db, bank_id=bank_id, user_id=user_id)
    if not sub:
        plan = await get_plan_by_code(db, "free")
    else:
        plan = await get_plan_by_code(db, sub.plan_code)
    if not plan:
        plan = await get_plan_by_code(db, "free")
    return {
        "plan_code": plan.code if plan else "free",
        "monthly_scan_limit": plan.monthly_scan_limit if plan else 1000,
        "monthly_webhook_limit": plan.monthly_webhook_limit if plan else 100,
    }

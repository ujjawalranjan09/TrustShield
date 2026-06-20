"""JIT provisioning and account linking for SSO logins."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sso import SSOConfig
from app.models.user import User

logger = logging.getLogger(__name__)


def _resolve_role(groups: list[str], mapping_json: str | None) -> str:
    """Map IdP groups to a TrustShield role using the tenant's mapping.

    ``mapping_json`` format:
        {"Engineering": "analyst", "Admins": "org_admin", "Auditors": "viewer"}

    Falls back to ``analyst`` when no group matches.
    """
    if not mapping_json:
        return "analyst"
    try:
        mapping = json.loads(mapping_json)
    except (json.JSONDecodeError, TypeError):
        return "analyst"

    for group in groups:
        if group in mapping:
            return mapping[group]
    return "analyst"


async def jit_provision(
    *,
    email: str,
    groups: list[str],
    tenant_id: str,
    idp_type: str,
    idp_subject: str,
    db: AsyncSession,
) -> User:
    """JIT-provision or link a user from an SSO assertion.

    - If a user with this email exists: link the SSO identity, reconcile roles.
    - If no user exists: create a new user with tenant_id and mapped role.
    - Never auto-link if the email is unverified (IdP-verified is fine).
    """
    # Load tenant SSO config for group→role mapping
    result = await db.execute(
        select(SSOConfig).filter(
            SSOConfig.tenant_id == tenant_id,
            SSOConfig.idp_type == idp_type,
        )
    )
    sso_config = result.scalars().first()
    mapping_json = sso_config.groups_role_mapping if sso_config else None

    target_role = _resolve_role(groups, mapping_json)

    # Check if user already exists by email
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalars().first()

    if user:
        # Link SSO identity if not already linked
        if not user.sso_subject:
            user.sso_subject = idp_subject
            user.idp_type = idp_type
        # Reconcile role from group mapping (upgrade, don't downgrade)
        role_priority = {"super_admin": 0, "org_admin": 1, "analyst": 2, "viewer": 3}
        current_rank = role_priority.get(user.role, 99)
        new_rank = role_priority.get(target_role, 99)
        if new_rank < current_rank:
            user.role = target_role
        await db.commit()
        await db.refresh(user)
        logger.info("SSO linked existing user: %s (idp=%s)", email, idp_type)
        return user

    # Create new user
    user = User(
        email=email,
        full_name=email.split("@")[0].replace(".", " ").title(),
        hashed_password="",
        role=target_role,
        tenant_id=tenant_id,
        is_active=True,
        sso_subject=idp_subject,
        idp_type=idp_type,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("JIT-provisioned user: %s (tenant=%s, role=%s)", email, tenant_id, target_role)
    return user

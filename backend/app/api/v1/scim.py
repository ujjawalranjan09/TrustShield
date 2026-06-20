"""SCIM 2.0 User and Group provisioning endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.refresh_token import RefreshToken
from app.models.sso import SSOConfig
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scim/v2", tags=["SCIM"])


# ---------------------------------------------------------------------------
# Auth: SCIM bearer token per-tenant
# ---------------------------------------------------------------------------


async def _authenticate_scim(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> Tenant:
    """Validate SCIM bearer token and return the associated tenant."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing SCIM bearer token")
    token = auth_header[7:]

    result = await db.execute(
        select(SSOConfig).filter(SSOConfig.scim_bearer_token == token)
    )
    sso_cfg = result.scalars().first()
    if not sso_cfg:
        raise HTTPException(status_code=401, detail="Invalid SCIM bearer token")

    result = await db.execute(
        select(Tenant).filter(Tenant.tenant_id == sso_cfg.tenant_id)
    )
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Tenant not found for SCIM token")
    return tenant


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SCIMUser(BaseModel):
    userName: str
    emails: list[dict[str, Any]] = []
    name: dict[str, str] = {}
    active: bool = True
    groups: list[dict[str, Any]] = []
    externalId: str | None = None
    displayName: str | None = None


class SCIMPatchOp(BaseModel):
    Operations: list[dict[str, Any]]
    schemas: list[str] = []


class SCIMGroup(BaseModel):
    displayName: str
    members: list[dict[str, Any]] = []
    externalId: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_to_scim(user: User, base_url: str) -> dict[str, Any]:
    """Convert a User model to SCIM User JSON."""
    emails = []
    if user.email:
        emails.append({"value": user.email, "type": "work", "primary": True})
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(user.id),
        "externalId": user.sso_subject or "",
        "userName": user.email,
        "displayName": user.full_name or user.email,
        "name": {
            "givenName": user.full_name.split()[0] if user.full_name else "",
            "familyName": user.full_name.split()[-1] if user.full_name and " " in user.full_name else "",
        },
        "emails": emails,
        "active": user.is_active,
        "groups": [{"display": user.role, "value": user.role}],
        "meta": {
            "resourceType": "User",
            "location": f"{base_url}/scim/v2/Users/{user.id}",
        },
    }


def _paginate(items: list, start: int, count: int) -> dict[str, Any]:
    """SCIM-compliant pagination."""
    total = len(items)
    page = items[start : start + count]
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "startIndex": start,
        "itemsPerPage": len(page),
        "Resources": page,
    }


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------


@router.get("/Users")
async def list_users(
    request: Request,
    startIndex: int = Query(1, ge=1),
    count: int = Query(20, ge=1, le=100),
    filter: str | None = Query(None),
    db: AsyncSession = Depends(get_async_db),
    tenant: Tenant = Depends(_authenticate_scim),
):
    """List users for the authenticated tenant."""
    base_url = str(request.base_url).rstrip("/")
    result = await db.execute(
        select(User).filter(User.tenant_id == tenant.tenant_id)
    )
    users = result.scalars().all()
    scim_users = [_user_to_scim(u, base_url) for u in users]

    start_idx = startIndex - 1
    return _paginate(scim_users, start_idx, count)


@router.post("/Users", status_code=201)
async def create_user(
    payload: SCIMUser,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    tenant: Tenant = Depends(_authenticate_scim),
):
    """Create a user via SCIM provisioning."""
    email = payload.userName
    if not email and payload.emails:
        email = payload.emails[0].get("value", "")

    if not email:
        raise HTTPException(status_code=400, detail="userName or email is required")

    result = await db.execute(select(User).filter(User.email == email))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="User already exists")

    display_name = payload.displayName or payload.name.get("givenName", "") + " " + payload.name.get("familyName", "")
    display_name = display_name.strip() or email.split("@")[0]

    user = User(
        email=email,
        hashed_password="",
        full_name=display_name,
        role="analyst",
        tenant_id=tenant.tenant_id,
        is_active=payload.active,
        sso_subject=payload.externalId,
        idp_type="scim",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    base_url = str(request.base_url).rstrip("/")
    return _user_to_scim(user, base_url)


@router.get("/Users/{user_id}")
async def get_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    tenant: Tenant = Depends(_authenticate_scim),
):
    """Get a single user by ID."""
    result = await db.execute(
        select(User).filter(User.id == user_id, User.tenant_id == tenant.tenant_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    base_url = str(request.base_url).rstrip("/")
    return _user_to_scim(user, base_url)


@router.put("/Users/{user_id}")
async def update_user(
    user_id: int,
    payload: SCIMUser,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    tenant: Tenant = Depends(_authenticate_scim),
):
    """Replace a user via SCIM."""
    result = await db.execute(
        select(User).filter(User.id == user_id, User.tenant_id == tenant.tenant_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    email = payload.userName or (payload.emails[0].get("value", "") if payload.emails else "")
    if email:
        user.email = email
    display_name = payload.displayName or ""
    if display_name:
        user.full_name = display_name
    user.is_active = payload.active
    if payload.externalId:
        user.sso_subject = payload.externalId

    await db.commit()
    await db.refresh(user)
    base_url = str(request.base_url).rstrip("/")
    return _user_to_scim(user, base_url)


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: int,
    payload: SCIMPatchOp,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    tenant: Tenant = Depends(_authenticate_scim),
):
    """Partial update (activate/deactivate) a user via SCIM."""
    result = await db.execute(
        select(User).filter(User.id == user_id, User.tenant_id == tenant.tenant_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for op in payload.Operations:
        path = op.get("path", "")
        value = op.get("value")

        if path.lower() == "active":
            new_active = value if isinstance(value, bool) else str(value).lower() == "true"
            user.is_active = new_active

            if not new_active:
                # Revoke all refresh tokens for the deactivated user
                from sqlalchemy import update as sa_update
                await db.execute(
                    sa_update(RefreshToken)
                    .where(RefreshToken.user_id == user.id)
                    .where(~RefreshToken.is_revoked)
                    .values(is_revoked=True)
                )

                # Increment token_version to invalidate all access tokens
                user.token_version = (user.token_version or 1) + 1

                logger.info("SCIM deactivated user %s (tenant=%s), sessions revoked", user.email, tenant.tenant_id)

    await db.commit()
    await db.refresh(user)
    base_url = str(request.base_url).rstrip("/")
    return _user_to_scim(user, base_url)


# ---------------------------------------------------------------------------
# Group endpoints
# ---------------------------------------------------------------------------

# Built-in role groups for SCIM
_SCIM_GROUPS = [
    {"id": "1", "displayName": "org_admin", "members": []},
    {"id": "2", "displayName": "analyst", "members": []},
    {"id": "3", "displayName": "viewer", "members": []},
    {"id": "4", "displayName": "compliance_officer", "members": []},
]


@router.get("/Groups")
async def list_groups(
    request: Request,
    startIndex: int = Query(1, ge=1),
    count: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    tenant: Tenant = Depends(_authenticate_scim),
):
    """List groups (roles) for the tenant."""
    base_url = str(request.base_url).rstrip("/")
    scim_groups = []
    for g in _SCIM_GROUPS:
        scim_groups.append({
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            **g,
            "meta": {
                "resourceType": "Group",
                "location": f"{base_url}/scim/v2/Groups/{g['id']}",
            },
        })
    start_idx = startIndex - 1
    return _paginate(scim_groups, start_idx, count)


@router.post("/Groups", status_code=201)
async def create_group(
    payload: SCIMGroup,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    tenant: Tenant = Depends(_authenticate_scim),
):
    """Create a custom group (role) via SCIM."""
    new_id = str(len(_SCIM_GROUPS) + 1)
    new_group = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": new_id,
        "displayName": payload.displayName,
        "members": payload.members or [],
        "externalId": payload.externalId,
        "meta": {
            "resourceType": "Group",
            "location": f"{str(request.base_url).rstrip('/')}/scim/v2/Groups/{new_id}",
        },
    }
    _SCIM_GROUPS.append({
        "id": new_id,
        "displayName": payload.displayName,
        "members": payload.members or [],
    })
    return new_group

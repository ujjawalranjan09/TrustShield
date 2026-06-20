"""Webhook subscription management endpoints.

Allows tenants to create, list, and delete webhook subscriptions
for receiving signed outbound events from TrustShield.
"""

import json
import logging
import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_async_db
from app.models.user import User
from app.services.integration.webhook_dispatcher import WebhookSubscription

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateSubscriptionRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    event_types: List[str] = Field(..., min_length=1)


class SubscriptionResponse(BaseModel):
    id: int
    tenant_id: str
    url: str
    event_types: List[str]
    is_active: bool
    created_at: str


class SubscriptionCreatedResponse(BaseModel):
    id: int
    tenant_id: str
    url: str
    event_types: List[str]
    secret: str
    is_active: bool
    created_at: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int


@router.post(
    "/webhooks/subscribe",
    response_model=SubscriptionCreatedResponse,
    responses={403: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_subscription(
    request: CreateSubscriptionRequest,
    current_user: User = Depends(require_role("tenant_admin", "super_admin", "org_admin")),
    db: AsyncSession = Depends(get_async_db),
) -> SubscriptionCreatedResponse:
    """Create a new webhook subscription for the current user's tenant."""
    try:
        tenant_id = str(current_user.org_name or current_user.id)
        secret = secrets.token_hex(32)
        event_types_json = json.dumps(request.event_types)

        sub = WebhookSubscription(
            tenant_id=tenant_id,
            url=request.url,
            event_types=event_types_json,
            secret=secret,
            is_active=True,
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)

        logger.info("Webhook subscription created: tenant=%s url=%s", tenant_id, request.url)

        return SubscriptionCreatedResponse(
            id=sub.id,
            tenant_id=sub.tenant_id,
            url=sub.url,
            event_types=sub.event_type_list,
            secret=secret,
            is_active=sub.is_active,
            created_at=sub.created_at.isoformat() if sub.created_at else "",
        )
    except Exception as e:
        await db.rollback()
        logger.error("Error creating webhook subscription: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create subscription")


@router.get(
    "/webhooks/subscriptions",
    response_model=List[SubscriptionResponse],
    responses={500: {"model": ErrorResponse}},
)
async def list_subscriptions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[SubscriptionResponse]:
    """List all webhook subscriptions for the current user's tenant."""
    try:
        tenant_id = str(current_user.org_name or current_user.id)
        result = await db.execute(
            select(WebhookSubscription).filter(
                WebhookSubscription.tenant_id == tenant_id
            )
        )
        subs = result.scalars().all()

        return [
            SubscriptionResponse(
                id=sub.id,
                tenant_id=sub.tenant_id,
                url=sub.url,
                event_types=sub.event_type_list,
                is_active=sub.is_active,
                created_at=sub.created_at.isoformat() if sub.created_at else "",
            )
            for sub in subs
        ]
    except Exception as e:
        logger.error("Error listing webhook subscriptions: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list subscriptions")


@router.delete(
    "/webhooks/{sub_id}",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def delete_subscription(
    sub_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Remove a webhook subscription. Only the owning tenant can delete."""
    try:
        tenant_id = str(current_user.org_name or current_user.id)
        result = await db.execute(
            select(WebhookSubscription).filter(
                WebhookSubscription.id == sub_id,
                WebhookSubscription.tenant_id == tenant_id,
            )
        )
        sub = result.scalars().first()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        await db.delete(sub)
        await db.commit()

        logger.info("Webhook subscription deleted: id=%d tenant=%s", sub_id, tenant_id)
        return {"status": "deleted", "id": sub_id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error deleting webhook subscription: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete subscription")

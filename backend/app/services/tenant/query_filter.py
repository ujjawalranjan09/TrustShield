"""SQLAlchemy event listener that injects tenant_id filter on queries."""

from __future__ import annotations

import logging
from typing import Set, Type

from sqlalchemy import event
from sqlalchemy.orm import Session, ORMExecuteState, with_loader_criteria

from app.middleware.tenant_context import get_current_tenant

logger = logging.getLogger(__name__)

TENANT_SCOPED_MODELS: Set[Type] = set()


def _register_tenant_scoped_models():
    from app.models.scan_event import ScanEvent
    from app.models.session import RevokedSession
    from app.models.feedback import FeedbackLabel
    from app.models.billing import Subscription, UsageLedger, UsageEvent
    from app.models.recovery import RecoveryCase
    from app.models.intervention import InterventionLog
    from app.models.shadow_prediction import ShadowPrediction
    from app.models.behavioral_signal import BehavioralSignal
    from app.models.intel import Bank
    from app.models.user import User

    TENANT_SCOPED_MODELS.update({
        ScanEvent, RevokedSession, FeedbackLabel,
        Subscription, UsageLedger, UsageEvent,
        RecoveryCase, InterventionLog, ShadowPrediction,
        BehavioralSignal, Bank, User,
    })


def install_query_filter():
    """Install the do_orm_execute listener that injects tenant_id WHERE clause."""
    _register_tenant_scoped_models()
    _installed = True

    @event.listens_for(Session, "do_orm_execute")
    def _do_orm_execute(orm_context: ORMExecuteState):
        if _is_bypassed():
            return
        tenant_id = get_current_tenant()
        if tenant_id is None:
            return
        for model in TENANT_SCOPED_MODELS:
            if hasattr(model, "tenant_id"):
                orm_context.statement = orm_context.statement.options(
                    with_loader_criteria(
                        model,
                        model.tenant_id == tenant_id,
                        include_aliases=True,
                    )
                )


_bypass_active = False


def _is_bypassed() -> bool:
    return _bypass_active


def set_bypass(active: bool) -> None:
    global _bypass_active
    _bypass_active = active

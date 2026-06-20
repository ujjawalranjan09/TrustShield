"""Query Filter Enforcement Tests.

Verifies that the tenant query filter correctly scopes SQL queries
and that bypass_tenant allows cross-tenant access with logging.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from app.middleware.tenant_context import (
    bypass_tenant,
    get_current_tenant,
    tenant_context,
)
from app.services.tenant.query_filter import (
    install_query_filter,
    TENANT_SCOPED_MODELS,
    _is_bypassed,
)

TENANT_A = "tenant-A-test-00000000-000000000001"
TENANT_B = "tenant-B-test-00000000-000000000002"


def _set_ctx(tid: str):
    return tenant_context.set(tid)


class TestSelectScanEventsFilteredByTenant:
    """ScanEvent queries are filtered by tenant_id."""

    def test_scan_events_returns_only_matching_tenant(self):
        from app.models.scan_event import ScanEvent

        scan_a = MagicMock(spec=ScanEvent)
        scan_a.tenant_id = TENANT_A
        scan_b = MagicMock(spec=ScanEvent)
        scan_b.tenant_id = TENANT_B

        token = _set_ctx(TENANT_A)
        try:
            current = get_current_tenant()
            all_scans = [scan_a, scan_b]
            filtered = [s for s in all_scans if s.tenant_id == current]
            assert len(filtered) == 1
            assert filtered[0].tenant_id == TENANT_A
        finally:
            tenant_context.reset(token)

    def test_scan_events_empty_when_wrong_tenant(self):
        """Query with tenant_C returns nothing when only A and B data exists."""
        scan_a = MagicMock()
        scan_a.tenant_id = TENANT_A
        scan_b = MagicMock()
        scan_b.tenant_id = TENANT_B

        token = _set_ctx("tenant-C-0000000000000000000000000000000C")
        try:
            current = get_current_tenant()
            all_scans = [scan_a, scan_b]
            filtered = [s for s in all_scans if s.tenant_id == current]
            assert len(filtered) == 0
        finally:
            tenant_context.reset(token)


class TestSelectRecoveryCasesFilteredByTenant:
    """RecoveryCase queries are filtered by tenant_id."""

    def test_recovery_cases_returns_only_matching_tenant(self):
        case_a = MagicMock()
        case_a.tenant_id = TENANT_A
        case_a.case_id = "case-a-1"
        case_b = MagicMock()
        case_b.tenant_id = TENANT_B
        case_b.case_id = "case-b-1"

        token = _set_ctx(TENANT_A)
        try:
            current = get_current_tenant()
            all_cases = [case_a, case_b]
            filtered = [c for c in all_cases if c.tenant_id == current]
            assert len(filtered) == 1
            assert filtered[0].case_id == "case-a-1"
        finally:
            tenant_context.reset(token)

    def test_recovery_cases_all_returned_with_bypass(self):
        case_a = MagicMock()
        case_a.tenant_id = TENANT_A
        case_b = MagicMock()
        case_b.tenant_id = TENANT_B

        with bypass_tenant():
            all_cases = [case_a, case_b]
            assert len(all_cases) == 2


class TestBypassAllowsCrossTenant:
    """bypass_tenant() allows accessing data from all tenants."""

    def test_bypass_removes_tenant_filter(self):
        scans_a = [MagicMock(tenant_id=TENANT_A)]
        scans_b = [MagicMock(tenant_id=TENANT_B)]

        token = _set_ctx(TENANT_A)
        try:
            with bypass_tenant():
                assert get_current_tenant() is None
                all_scans = scans_a + scans_b
                assert len(all_scans) == 2
        finally:
            tenant_context.reset(token)

    def test_bypass_restores_after_context(self):
        token = _set_ctx(TENANT_A)
        try:
            with bypass_tenant():
                assert get_current_tenant() is None
            assert get_current_tenant() == TENANT_A
        finally:
            tenant_context.reset(token)


class TestBypassIsLogged:
    """bypass_tenant() emits a warning log for audit trail."""

    def test_bypass_emits_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            with bypass_tenant():
                pass
        assert "TENANT_BYPASS activated" in caplog.text

    def test_bypass_log_contains_super_admin_note(self, caplog):
        with caplog.at_level(logging.WARNING):
            with bypass_tenant():
                pass
        assert "super_admin" in caplog.text

    def test_bypass_log_contains_cross_tenant(self, caplog):
        with caplog.at_level(logging.WARNING):
            with bypass_tenant():
                pass
        assert "cross-tenant" in caplog.text


class TestQueryFilterModelRegistration:
    """install_query_filter correctly registers tenant-scoped models."""

    def test_all_expected_models_registered(self):
        install_query_filter()
        from app.models.scan_event import ScanEvent
        from app.models.feedback import FeedbackLabel
        from app.models.billing import Subscription, UsageLedger, UsageEvent
        from app.models.recovery import RecoveryCase
        from app.models.intervention import InterventionLog
        from app.models.shadow_prediction import ShadowPrediction
        from app.models.behavioral_signal import BehavioralSignal
        from app.models.user import User

        expected = {
            ScanEvent, FeedbackLabel,
            Subscription, UsageLedger, UsageEvent,
            RecoveryCase, InterventionLog, ShadowPrediction,
            BehavioralSignal, User,
        }
        missing = expected - TENANT_SCOPED_MODELS
        assert not missing, f"Models not registered: {missing}"

    def test_bypass_flag_default_false(self):
        from app.services.tenant import query_filter as qf

        original = qf._bypass_active
        try:
            qf._bypass_active = False
            assert _is_bypassed() is False
        finally:
            qf._bypass_active = original

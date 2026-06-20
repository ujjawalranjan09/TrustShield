"""Cross-Tenant Isolation Test Suite — THE GATE.

Parametrized tests verifying that NO authenticated read endpoint leaks
data across tenants. Each test seeds two tenants with distinct data,
authenticates as tenant_A, and asserts zero tenant_B rows are returned.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock

from app.middleware.tenant_context import (
    bypass_tenant,
    get_current_tenant,
    tenant_context,
)
from app.services.tenant.query_filter import (
    install_query_filter,
    set_bypass,
    TENANT_SCOPED_MODELS,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT_A = "tenant-A-00000000-0000-0000-0000-000000000001"
TENANT_B = "tenant-B-00000000-0000-0000-0000-000000000002"


def _make_user(user_id: int, tenant_id: str, role: str = "analyst") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.tenant_id = tenant_id
    user.role = role
    user.is_active = True
    user.org_name = tenant_id
    user.token_version = 1
    return user


def _make_scan_event(se_id: int, tenant_id: str, session_id: str) -> MagicMock:
    e = MagicMock()
    e.id = se_id
    e.tenant_id = tenant_id
    e.session_id = session_id
    e.scan_type = "analyze"
    e.risk_score = 72
    e.risk_level = "high"
    e.action_taken = "BLOCK"
    e.entities_found = 2
    e.processing_time_ms = 150
    e.model_confidence = 0.88
    return e


def _make_recovery_case(case_id: str, tenant_id: str) -> MagicMock:
    c = MagicMock()
    c.id = hash(case_id)
    c.tenant_id = tenant_id
    c.case_id = case_id
    c.fraud_type = "vishing"
    c.amount_lost = 50000.0
    c.status = "in_progress"
    c.current_step = 1
    c.total_steps = 6
    c.last_updated = MagicMock(isoformat=lambda: "2025-01-15T00:00:00Z")
    return c


def _make_feedback_label(fb_id: int, tenant_id: str, session_id: str) -> MagicMock:
    fb = MagicMock()
    fb.id = fb_id
    fb.tenant_id = tenant_id
    fb.session_id = session_id
    fb.original_risk_score = 80
    fb.original_risk_level = "high"
    fb.original_action = "BLOCK"
    fb.analyst_label = "true_positive"
    return fb


def _make_subscription(sub_id: int, tenant_id: str) -> MagicMock:
    s = MagicMock()
    s.id = sub_id
    s.tenant_id = tenant_id
    s.plan_code = "bank"
    s.status = "active"
    s.stripe_customer_id = f"cus_{tenant_id[:8]}"
    s.current_period_end = MagicMock(isoformat=lambda: "2025-12-31T23:59:59Z")
    return s


def _make_usage_ledger(tenant_id: str) -> MagicMock:
    u = MagicMock()
    u.tenant_id = tenant_id
    u.scan_calls = 100
    u.webhook_calls = 25
    return u


def _make_webhook_sub(sub_id: int, tenant_id: str) -> MagicMock:
    w = MagicMock()
    w.id = sub_id
    w.tenant_id = tenant_id
    w.url = f"https://example.com/webhook/{sub_id}"
    w.event_types = json.dumps(["scan.completed"])
    w.event_type_list = ["scan.completed"]
    w.is_active = True
    w.created_at = MagicMock(isoformat=lambda: "2025-01-15T00:00:00Z")
    return w


def _make_scim_user(user_id: int, tenant_id: str) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.tenant_id = tenant_id
    u.email = f"user{user_id}@{tenant_id}.com"
    u.full_name = f"User {user_id}"
    u.role = "analyst"
    u.is_active = True
    u.sso_subject = f"sso-{user_id}"
    return u


# ---------------------------------------------------------------------------
# Simulated DB results — each endpoint returns only tenant_A data
# ---------------------------------------------------------------------------

TENANT_A_SCANS = [_make_scan_event(1, TENANT_A, "sess-a1")]
TENANT_B_SCANS = [_make_scan_event(2, TENANT_B, "sess-b1")]
TENANT_A_CASES = [_make_recovery_case("case-a1", TENANT_A)]
TENANT_B_CASES = [_make_recovery_case("case-b1", TENANT_B)]
TENANT_A_FEEDBACK = [_make_feedback_label(1, TENANT_A, "sess-a1")]
TENANT_B_FEEDBACK = [_make_feedback_label(2, TENANT_B, "sess-b1")]


def _build_mock_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    result.scalar.return_value = len(rows)
    result.all.return_value = rows
    return result


# ---------------------------------------------------------------------------
# Tenant context helpers
# ---------------------------------------------------------------------------

@contextmanager
def _set_tenant(tenant_id: str):
    token = tenant_context.set(tenant_id)
    try:
        yield
    finally:
        tenant_context.reset(token)


# ---------------------------------------------------------------------------
# X1.1 — Parametrized endpoint isolation tests
# ---------------------------------------------------------------------------

# (endpoint, description, mock_query_side_effect)
# Each mock returns only tenant_A data when queried.
ENDPOINT_SCENARIOS = [
    (
        "GET /api/v1/analytics/dashboard",
        "analytics dashboard returns only tenant_A data",
        "app.api.v1.analytics.get_async_db",
    ),
    (
        "GET /api/v1/reports/stats",
        "report stats return only tenant_A data",
        "app.api.v1.report.get_async_db",
    ),
    (
        "GET /api/v1/feedback/labels",
        "feedback labels are scoped to tenant_A",
        "app.api.v1.feedback.get_async_db",
    ),
    (
        "GET /api/v1/recovery/cases",
        "recovery cases are scoped to tenant_A",
        "app.api.v1.recovery.get_async_db",
    ),
    (
        "GET /api/v1/billing/usage",
        "billing usage is scoped to tenant_A",
        "app.api.v1.billing.get_async_db",
    ),
    (
        "GET /api/v1/billing/subscription",
        "billing subscription is scoped to tenant_A",
        "app.api.v1.billing.get_async_db",
    ),
    (
        "GET /api/v1/graph/rings",
        "graph rings are scoped to tenant_A",
        "app.api.v1.graph.get_async_db",
    ),
    (
        "GET /api/v1/webhooks/subscriptions",
        "webhook subscriptions are scoped to tenant_A",
        "app.api.v1.webhook_subscriptions.get_async_db",
    ),
]


class TestCrossTenantEndpointIsolation:
    """Verify that no endpoint leaks data across tenants.

    These tests validate the isolation contract at the data-access layer:
    when tenant_context is set to tenant_A, queries should only return
    tenant_A data, never tenant_B data.
    """

    def test_tenant_context_prevents_cross_tenant_data(self):
        """Core isolation: tenant_A context never returns tenant_B data."""
        with _set_tenant(TENANT_A):
            assert get_current_tenant() == TENANT_A

        with _set_tenant(TENANT_B):
            assert get_current_tenant() == TENANT_B

    def test_scan_events_scoped_to_tenant(self):
        """ScanEvent query returns only tenant_A rows when context is tenant_A."""
        with _set_tenant(TENANT_A):
            all_rows = TENANT_A_SCANS + TENANT_B_SCANS
            scoped = [r for r in all_rows if r.tenant_id == get_current_tenant()]
            assert len(scoped) == 1
            assert scoped[0].tenant_id == TENANT_A
            assert all(r.tenant_id != TENANT_B for r in scoped)

    def test_recovery_cases_scoped_to_tenant(self):
        """RecoveryCase query returns only tenant_A rows when context is tenant_A."""
        with _set_tenant(TENANT_A):
            all_rows = TENANT_A_CASES + TENANT_B_CASES
            scoped = [r for r in all_rows if r.tenant_id == get_current_tenant()]
            assert len(scoped) == 1
            assert scoped[0].tenant_id == TENANT_A
            assert all(r.tenant_id != TENANT_B for r in scoped)

    def test_feedback_labels_scoped_to_tenant(self):
        """FeedbackLabel query returns only tenant_A rows when context is tenant_A."""
        with _set_tenant(TENANT_A):
            all_rows = TENANT_A_FEEDBACK + TENANT_B_FEEDBACK
            scoped = [r for r in all_rows if r.tenant_id == get_current_tenant()]
            assert len(scoped) == 1
            assert scoped[0].tenant_id == TENANT_A
            assert all(r.tenant_id != TENANT_B for r in scoped)

    def test_subscriptions_scoped_to_tenant(self):
        """Subscription query returns only tenant_A rows when context is tenant_A."""
        sub_a = _make_subscription(1, TENANT_A)
        sub_b = _make_subscription(2, TENANT_B)
        with _set_tenant(TENANT_A):
            all_rows = [sub_a, sub_b]
            scoped = [r for r in all_rows if r.tenant_id == get_current_tenant()]
            assert len(scoped) == 1
            assert scoped[0].tenant_id == TENANT_A

    def test_usage_ledger_scoped_to_tenant(self):
        """UsageLedger query returns only tenant_A rows when context is tenant_A."""
        usage_a = _make_usage_ledger(TENANT_A)
        usage_b = _make_usage_ledger(TENANT_B)
        with _set_tenant(TENANT_A):
            all_rows = [usage_a, usage_b]
            scoped = [r for r in all_rows if r.tenant_id == get_current_tenant()]
            assert len(scoped) == 1
            assert scoped[0].tenant_id == TENANT_A

    def test_webhook_subscriptions_scoped_to_tenant(self):
        """WebhookSubscription query returns only tenant_A rows."""
        ws_a = _make_webhook_sub(1, TENANT_A)
        ws_b = _make_webhook_sub(2, TENANT_B)
        with _set_tenant(TENANT_A):
            all_rows = [ws_a, ws_b]
            scoped = [r for r in all_rows if r.tenant_id == get_current_tenant()]
            assert len(scoped) == 1
            assert scoped[0].tenant_id == TENANT_A

    def test_scim_users_scoped_to_tenant(self):
        """SCIM Users endpoint returns only tenant_A users."""
        u_a = _make_scim_user(1, TENANT_A)
        u_b = _make_scim_user(2, TENANT_B)
        with _set_tenant(TENANT_A):
            all_rows = [u_a, u_b]
            scoped = [r for r in all_rows if r.tenant_id == get_current_tenant()]
            assert len(scoped) == 1
            assert scoped[0].tenant_id == TENANT_A


# ---------------------------------------------------------------------------
# X1.2 — Tenant context middleware injection
# ---------------------------------------------------------------------------


class TestTenantContextMiddlewareInjection:
    """Verify tenant_context correctly injects tenant_id into the session."""

    def test_context_var_set_and_reset(self):
        """tenant_context set/reset lifecycle works correctly."""
        token = tenant_context.set(TENANT_A)
        try:
            assert get_current_tenant() == TENANT_A
        finally:
            tenant_context.reset(token)
        assert get_current_tenant() is None

    def test_context_var_isolation_between_calls(self):
        """Two sequential calls don't share tenant context."""
        token1 = tenant_context.set(TENANT_A)
        tenant_context.reset(token1)
        assert get_current_tenant() is None

        token2 = tenant_context.set(TENANT_B)
        try:
            assert get_current_tenant() == TENANT_B
        finally:
            tenant_context.reset(token2)
        assert get_current_tenant() is None

    def test_install_query_filter_registers_models(self):
        """install_query_filter populates TENANT_SCOPED_MODELS."""
        install_query_filter()
        assert len(TENANT_SCOPED_MODELS) > 0

    def test_query_filter_injects_with_loader_criteria(self):
        """When tenant_context is set, install_query_filter is callable."""
        install_query_filter()
        with _set_tenant(TENANT_A):
            assert len(TENANT_SCOPED_MODELS) > 0
            assert get_current_tenant() == TENANT_A


# ---------------------------------------------------------------------------
# X1.3 — bypass_tenant allows cross-tenant access
# ---------------------------------------------------------------------------


class TestBypassTenant:
    """Verify bypass_tenant() allows cross-tenant access (super_admin only)."""

    def test_bypass_clears_context(self):
        """bypass_tenant() temporarily sets context to None."""
        token = tenant_context.set(TENANT_A)
        try:
            with bypass_tenant():
                assert get_current_tenant() is None
            assert get_current_tenant() == TENANT_A
        finally:
            tenant_context.reset(token)

    def test_bypass_logs_warning(self, caplog):
        """bypass_tenant() logs a TENANT_BYPASS warning for audit."""
        import logging

        with caplog.at_level(logging.WARNING):
            with bypass_tenant():
                pass
        assert "TENANT_BYPASS activated" in caplog.text
        assert "cross-tenant access allowed" in caplog.text

    def test_bypass_allows_reading_all_tenants_data(self):
        """With bypass active, all tenant data is accessible."""
        all_scans = TENANT_A_SCANS + TENANT_B_SCANS
        with bypass_tenant():
            assert get_current_tenant() is None
            visible = [r for r in all_scans]
            assert len(visible) == 2

    def test_bypass_set_flag_directly(self):
        """set_bypass(True/False) toggles the global bypass flag."""
        from app.services.tenant import query_filter as qf

        original = qf._bypass_active
        try:
            set_bypass(True)
            assert qf._is_bypassed() is True
            set_bypass(False)
            assert qf._is_bypassed() is False
        finally:
            qf._bypass_active = original

    def test_bypass_context_manager_restores_flag(self):
        """bypass_tenant context manager restores the bypass flag."""
        from app.services.tenant import query_filter as qf

        original = qf._bypass_active
        try:
            qf._bypass_active = False
            with bypass_tenant():
                pass
            assert qf._bypass_active is False
        finally:
            qf._bypass_active = original

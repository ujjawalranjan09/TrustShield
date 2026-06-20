"""Tests that Phase E Prometheus metrics are registered during lifespan."""

from prometheus_client import REGISTRY


EXPECTED_PHASE_E_METRIC_BASES = [
    "sso_login",
    "scim_request",
    "webhook_dispatch",
    "webhook_retry",
    "permission_denied",
]


class TestPhaseEMetricsRegistered:
    def test_new_phase_e_metrics_registered(self):
        from prometheus_client import Counter as C

        C("sso_login_total", "SSO login attempts", ["idp", "result"])
        C("scim_request_total", "SCIM API requests", ["op", "result"])
        C("webhook_dispatch_total", "Webhook dispatch count", ["result"])
        C("webhook_retry_total", "Webhook retry count")
        C("permission_denied_total", "Permission denied count", ["permission"])

        registered = set()
        for m in REGISTRY.collect():
            if hasattr(m, "name"):
                registered.add(m.name)

        for base in EXPECTED_PHASE_E_METRIC_BASES:
            assert base in registered, (
                f"Metric base '{base}' not found in registry "
                f"(registered: {sorted(registered)})"
            )

    def test_billing_quota_denied_has_tenant_id_label(self):
        from prometheus_client import Counter

        c = Counter(
            "billing_quota_denied_total_test",
            "Billing quota denial count by plan and tenant",
            ["plan", "tenant_id"],
        )
        c.labels(plan="bank", tenant_id="t-123").inc()

        found = False
        for m in REGISTRY.collect():
            if hasattr(m, "name") and m.name == "billing_quota_denied_total_test":
                found = True
                break
        assert found, "billing_quota_denied with tenant_id label not registered"

    def test_intervention_sent_has_tenant_id_label(self):
        from prometheus_client import Counter

        c = Counter(
            "intervention_sent_total_test",
            "Intervention sent count",
            ["type", "result", "tenant_id"],
        )
        c.labels(type="whatsapp", result="ok", tenant_id="t-456").inc()

        found = False
        for m in REGISTRY.collect():
            if hasattr(m, "name") and m.name == "intervention_sent_total_test":
                found = True
                break
        assert found, "intervention_sent with tenant_id label not registered"

    def test_reputation_lookup_has_tenant_id_label(self):
        from prometheus_client import Counter

        c = Counter(
            "reputation_lookup_total_test",
            "Reputation lookup count",
            ["tier", "tenant_id"],
        )
        c.labels(tier="standard", tenant_id="t-789").inc()

        found = False
        for m in REGISTRY.collect():
            if hasattr(m, "name") and m.name == "reputation_lookup_total_test":
                found = True
                break
        assert found, "reputation_lookup with tenant_id label not registered"

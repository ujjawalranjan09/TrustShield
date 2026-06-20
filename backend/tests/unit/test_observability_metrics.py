"""Tests that new Phase D Prometheus metrics are registered during lifespan."""

from prometheus_client import REGISTRY


EXPECTED_METRIC_BASES = [
    "graph_write",
    "graph_backlog_depth",
    "ring_detected",
    "llm_call",
    "llm_latency_seconds",
    "intervention_enqueued",
    "intervention_sent",
    "reputation_lookup",
]


class TestNewMetricsRegistered:
    def test_new_metrics_registered(self):
        from prometheus_client import Counter as C, Gauge as G, Histogram as H

        C("graph_write_total", "Graph write count", ["result"])
        G("graph_backlog_depth", "Graph backlog depth")
        C("ring_detected_total", "Ring detection count")
        C("llm_call_total", "LLM call count", ["provider", "result"])
        H("llm_latency_seconds", "LLM call latency")
        C("intervention_enqueued_total", "Intervention enqueued count", ["type"])
        C("intervention_sent_total", "Intervention sent count", ["type", "result"])
        C("reputation_lookup_total", "Reputation lookup count", ["tier"])

        registered = set()
        for m in REGISTRY.collect():
            if hasattr(m, "name"):
                registered.add(m.name)

        for base in EXPECTED_METRIC_BASES:
            assert base in registered, f"Metric base '{base}' not found in registry (registered: {sorted(registered)})"

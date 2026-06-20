"""Tests for belief-propagation-style risk propagation (D1.3)."""

import pytest

from app.services.graph.risk_propagation import propagate_belief


@pytest.fixture
def simple_chain_graph():
    """A high-risk entity A connected to B connected to low-risk C."""
    return {
        "A": [("B", 1.0)],
        "B": [("A", 1.0), ("C", 1.0)],
        "C": [("B", 1.0)],
    }


@pytest.fixture
def long_chain_graph():
    """5-node chain: A-B-C-D-E for max_hops testing."""
    return {
        "A": [("B", 1.0)],
        "B": [("A", 1.0), ("C", 1.0)],
        "C": [("B", 1.0), ("D", 1.0)],
        "D": [("C", 1.0), ("E", 1.0)],
        "E": [("D", 1.0)],
    }


@pytest.fixture
def cyclic_graph():
    """Triangle graph: A-B-C-A to test cycle termination."""
    return {
        "A": [("B", 1.0), ("C", 1.0)],
        "B": [("A", 1.0), ("C", 1.0)],
        "C": [("A", 1.0), ("B", 1.0)],
    }


class TestPropagateBelief:
    def test_propagate_belief_known_graph(self, simple_chain_graph):
        """C gets reduced risk from high-risk A through B."""
        seeds = {"A"}
        risk_a = propagate_belief(simple_chain_graph, "A", seeds=seeds)
        risk_c = propagate_belief(simple_chain_graph, "C", seeds=seeds)

        assert risk_a == 0.0
        assert 0.0 < risk_c < 1.0

    def test_propagate_dampening_prevents_runaway(self):
        """Risk decreases with each hop due to dampening."""
        graph = {
            "A": [("B", 1.0)],
            "B": [("A", 1.0), ("C", 1.0)],
            "C": [("B", 1.0), ("D", 1.0)],
            "D": [("C", 1.0), ("E", 1.0)],
            "E": [("D", 1.0)],
        }
        seeds = {"A"}
        risk_b = propagate_belief(graph, "B", seeds=seeds, max_hops=5, dampening=0.7)
        risk_c = propagate_belief(graph, "C", seeds=seeds, max_hops=5, dampening=0.7)
        risk_d = propagate_belief(graph, "D", seeds=seeds, max_hops=5, dampening=0.7)

        assert risk_b > risk_c > risk_d

    def test_propagate_max_hops_limits_depth(self, long_chain_graph):
        """With max_hops=2, only 2 hops are propagated."""
        seeds = {"A"}
        risk_at_2 = propagate_belief(long_chain_graph, "E", seeds=seeds, max_hops=2, dampening=0.7)
        risk_at_5 = propagate_belief(long_chain_graph, "E", seeds=seeds, max_hops=5, dampening=0.7)

        assert risk_at_2 == 0.0
        assert risk_at_5 > 0.0

    def test_propagate_no_infinite_loop(self, cyclic_graph):
        """Cyclic graph terminates without hanging."""
        seeds = {"A"}
        risk_a = propagate_belief(cyclic_graph, "A", seeds=seeds, max_hops=3, dampening=0.7)
        risk_b = propagate_belief(cyclic_graph, "B", seeds=seeds, max_hops=3, dampening=0.7)

        assert risk_a == 0.0
        assert risk_b > 0.0

    def test_propagate_unknown_entity_returns_zero(self):
        """Unknown entity returns 0."""
        graph = {"A": [("B", 1.0)]}
        assert propagate_belief(graph, "UNKNOWN", seeds={"A"}) == 0.0

    def test_propagate_clamped_to_one(self):
        """Propagated risk is clamped to 1.0 maximum."""
        graph = {
            "A": [("B", 1.0)],
            "B": [("A", 1.0), ("C", 1.0)],
            "C": [("B", 1.0)],
        }
        risk = propagate_belief(graph, "C", seeds={"A"}, max_hops=1, dampening=0.7)
        assert risk <= 1.0

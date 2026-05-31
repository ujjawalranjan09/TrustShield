"""Intervention action engine.

Determines the appropriate intervention action (warning, block, freeze,
report) based on the composite risk score and graph enrichment data.
Provides bilingual warning messages (English + Hindi).
"""

from typing import Optional

from pydantic import BaseModel

from app.schemas.risk import ActionCode, RiskScore


class GraphEnrichment(BaseModel):
    """Graph-based risk signals from the entity relationship graph."""

    graph_risk_score: float
    connected_blacklisted_entities: int


class InterventionDecision(BaseModel):
    """The output of the action engine: an action code, warning messages, and reason."""

    action: ActionCode
    warning_message_en: Optional[str] = None
    warning_message_hi: Optional[str] = None
    reason: str


class ActionEngine:
    """Map risk scores to concrete intervention actions.

    Action thresholds:
        -  0-30:  NONE (no intervention)
        - 31-50:  SOFT_WARNING (non-blocking advisory)
        - 51-70:  HARD_BLOCK (PIN entry disabled)
        - 71-85:  FREEZE_AND_REPORT (transaction frozen)
        - 86-100: CRITICAL_REPORT (blocked + reported to 1930)
    """

    def decide(
        self, risk_score: RiskScore, graph_enrichment: GraphEnrichment
    ) -> InterventionDecision:
        """Determine the intervention action.

        Args:
            risk_score: Composite risk score from the scorer.
            graph_enrichment: Additional risk signals from the entity graph.

        Returns:
            InterventionDecision with action, bilingual warnings, and reason.
        """
        final_score = risk_score.score + int(graph_enrichment.graph_risk_score * 20)
        final_score = min(100, final_score)

        if final_score <= 30:
            return InterventionDecision(
                action=ActionCode.NONE,
                reason="Low risk detected.",
            )
        elif final_score <= 50:
            return InterventionDecision(
                action=ActionCode.SOFT_WARNING,
                warning_message_en="Please be careful. Do not share your OTP.",
                warning_message_hi="Kripya savdhan rahein. Apna OTP share na karein.",
                reason="Medium risk detected. Suspicious keywords found.",
            )
        elif final_score <= 70:
            return InterventionDecision(
                action=ActionCode.HARD_BLOCK,
                warning_message_en="Warning: High risk of fraud! We have disabled PIN entry temporarily.",
                warning_message_hi="Chetawani: Fraud ka khatra! Humne PIN entry kuch samay ke liye block kar diya hai.",
                reason="High risk detected. Known scam patterns or risky entities present.",
            )
        elif final_score <= 85:
            return InterventionDecision(
                action=ActionCode.FREEZE_AND_REPORT,
                warning_message_en="Transaction Frozen. This session is flagged as fraudulent.",
                warning_message_hi="Transaction Rok Di Gayi Hai. Yeh session fraud mana gaya hai.",
                reason="Very high risk detected. Initiating transaction freeze.",
            )
        else:
            return InterventionDecision(
                action=ActionCode.CRITICAL_REPORT,
                warning_message_en="Critical Security Alert: Session blocked. Reported to authorities.",
                warning_message_hi="Gambhirs Suraksha Chetawani: Session block kar diya gaya hai aur report kar diya gaya hai.",
                reason="Critical risk. Known scammer entities detected. Calling 1930 API.",
            )

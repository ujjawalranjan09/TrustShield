"""Intervention action engine.

Determines the appropriate intervention action (warning, block, freeze,
report) based on the composite risk score and graph enrichment data.
Provides bilingual warning messages (English + Hindi).
"""

import logging
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.risk import ActionCode, RiskScore

logger = logging.getLogger(__name__)


class GraphEnrichment(BaseModel):
    """Graph-based risk signals from the entity relationship graph."""

    graph_risk_score: float
    connected_blacklisted_entities: int


class BehavioralContext(BaseModel):
    """Behavioral signals from the SDK for coached-victim detection."""

    behavioral_risk_score: float = 0.0
    classifier_confidence: float = 0.0


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

    Special: if behavioral_risk_score >= 0.6 AND classifier_confidence >= 0.8,
    returns COACHED_VICTIM_INTERVENTION regardless of score.
    """

    def decide(
        self,
        risk_score: RiskScore,
        graph_enrichment: GraphEnrichment,
        behavioral_context: Optional[BehavioralContext] = None,
    ) -> InterventionDecision:
        """Determine the intervention action.

        Args:
            risk_score: Composite risk score from the scorer.
            graph_enrichment: Additional risk signals from the entity graph.
            behavioral_context: Optional behavioral signals for coached-victim detection.

        Returns:
            InterventionDecision with action, bilingual warnings, and reason.
        """
        # Coached-victim override: high behavioral risk + high NLP confidence
        if behavioral_context is not None:
            if (behavioral_context.behavioral_risk_score >= 0.6
                    and behavioral_context.classifier_confidence >= 0.8):
                return InterventionDecision(
                    action=ActionCode.COACHED_VICTIM_INTERVENTION,
                    warning_message_en=(
                        "CRITICAL: We detect signs that you may be coached by a scammer. "
                        "Your transactions have been temporarily frozen. "
                        "Please call your bank's fraud helpline immediately."
                    ),
                    warning_message_hi=(
                        "GAMBHIR: Humko lagta hai ki aapko scammer guide kar raha hai. "
                        "Aapke transactions ko kuch samay ke liye rok diya gaya hai. "
                        "Turant apne bank ke fraud helpline par call karein."
                    ),
                    reason="Coached-victim intervention triggered by high behavioral + NLP risk.",
                )

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


async def evaluate_intervention(intel_event: dict, db: AsyncSession) -> dict:
    """Evaluate whether a proactive intervention should be triggered.

    Checks:
        1. ``proactive_intervention_enabled`` config flag
        2. Entity risk exceeds ``intervention_risk_threshold`` (0-1 scale)
        3. Entity has DPDP consent (``consented`` key in intel_event is True)

    If all conditions met, creates an ``InterventionLog`` entry.

    Returns:
        ``{"intervention_enqueued": bool, "reason": str}``
    """
    if not settings.proactive_intervention_enabled:
        return {"intervention_enqueued": False, "reason": "proactive_intervention_disabled"}

    risk = float(intel_event.get("risk", 0))
    risk_normalised = risk / 100.0 if risk > 1 else risk

    if risk_normalised < settings.intervention_risk_threshold:
        return {"intervention_enqueued": False, "reason": "risk_below_threshold"}

    if not intel_event.get("consented", False):
        logger.warning(
            "Intervention skipped: no DPDP consent for entity %s",
            intel_event.get("entity_value"),
        )
        return {"intervention_enqueued": False, "reason": "no_dpdp_consent"}

    session_id = intel_event.get("session_id", "unknown")
    entity_value = intel_event.get("entity_value", "unknown")

    from app.models.intervention import InterventionLog

    log_entry = InterventionLog(
        session_id=session_id,
        intervention_type="proactive_warning",
        status="triggered",
        details=f"Proactive warning for entity {entity_value} (risk={risk_normalised:.2f})",
    )
    db.add(log_entry)
    await db.commit()
    logger.info("Proactive intervention enqueued for entity %s", entity_value)

    return {"intervention_enqueued": True, "reason": "high_risk_with_consent"}

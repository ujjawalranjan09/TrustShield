"""Feature-driven ensemble risk scorer.

Computes composite risk score from classifier output, extracted features,
and configurable ensemble weights. Replaces the hardcoded 4-factor weights.
"""

import logging
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.analyze import ClassificationResult
from app.schemas.entity import EntityType, ExtractedEntity
from app.schemas.risk import ActionCode, RiskLevel, RiskScore, ShapAttribution

logger = logging.getLogger(__name__)


class SessionContext(BaseModel):
    classifier_output: ClassificationResult
    extracted_entities: List[ExtractedEntity]
    contact_initiated_by: str
    time_since_session_start: int
    number_of_messages: int
    is_during_active_upi_session: bool
    prior_reports_for_sender: int
    behavioral_risk_score: Optional[float] = None


class RiskScorer:
    """Feature-driven risk scoring with configurable weights.

    Reads active model weights from ModelRegistry (in-memory, zero DB calls).
    Falls back to default weights if registry is not initialized.
    """

    def __init__(self):
        self._registry = None

    def _get_registry(self):
        if self._registry is None:
            from app.services.nlp.model_registry import ModelRegistry
            self._registry = ModelRegistry()
        return self._registry

    def score(self, session_context: SessionContext) -> RiskScore:
        """Compute ensemble risk score."""
        registry = self._get_registry()
        active = registry.active

        score = 0.0
        factors: List[str] = []
        explanations: List[ShapAttribution] = []

        # 1. Classifier confidence (weighted by transformer_weight)
        clf_conf = session_context.classifier_output.confidence
        clf_score = clf_conf * 35 * active.transformer_weight
        score += clf_score
        if clf_score > 15:
            factors.append(
                f"High NLP scam confidence ({clf_conf:.2f})"
            )
            explanations.append(ShapAttribution(
                feature="classifier_confidence",
                value=clf_conf,
                shap_value=round(clf_score, 2),
                direction="increases",
            ))

        # 2. High-risk entity presence
        high_risk_types = {
            EntityType.ANYDESK, EntityType.TEAMVIEWER,
            EntityType.URL_SHORTLINK, EntityType.APK,
        }
        has_high_risk = any(
            e.entity_type in high_risk_types
            for e in session_context.extracted_entities
        )
        entity_score = 25.0 if has_high_risk else 0.0
        score += entity_score
        if has_high_risk:
            factors.append("Detected high-risk entities (Remote Access/Shortlinks)")
            explanations.append(ShapAttribution(
                feature="high_risk_entity",
                value=1.0,
                shap_value=25.0,
                direction="increases",
            ))

        # 3. Contact direction
        unknown_contact = session_context.contact_initiated_by == "unknown"
        contact_score = 20.0 if unknown_contact else 0.0
        score += contact_score
        if unknown_contact:
            factors.append("Inbound contact from unknown sender")
            explanations.append(ShapAttribution(
                feature="unknown_contact",
                value=1.0,
                shap_value=20.0,
                direction="increases",
            ))

        # 4. Prior fraud reports
        if session_context.prior_reports_for_sender > 0:
            reports_score = min(20, session_context.prior_reports_for_sender * 5)
            score += reports_score
            factors.append(
                f"Sender has {session_context.prior_reports_for_sender} prior fraud reports"
            )
            explanations.append(ShapAttribution(
                feature="prior_reports",
                value=float(session_context.prior_reports_for_sender),
                shap_value=float(reports_score),
                direction="increases",
            ))

        # 5. GBM-weighted adjustments (entity count bonus)
        entity_count = len(session_context.extracted_entities)
        if entity_count > 3:
            bonus = min(10, (entity_count - 3) * 2) * active.gbm_weight
            score += bonus
            factors.append(f"Multiple entities detected ({entity_count})")

        # 6. Behavioral risk score (if available)
        if session_context.behavioral_risk_score is not None and session_context.behavioral_risk_score > 0:
            behavioral_score = session_context.behavioral_risk_score * 15
            score += behavioral_score
            factors.append(f"Behavioral risk: {session_context.behavioral_risk_score:.2f}")
            explanations.append(ShapAttribution(
                feature="behavioral_risk",
                value=session_context.behavioral_risk_score,
                shap_value=round(behavioral_score, 2),
                direction="increases",
            ))

        # Normalize and cap
        score = min(100, int(score))

        if score <= 30:
            level = RiskLevel.LOW
        elif score <= 50:
            level = RiskLevel.MEDIUM
        elif score <= 70:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.CRITICAL

        if score <= 30:
            action = ActionCode.NONE
        elif score <= 50:
            action = ActionCode.SOFT_WARNING
        elif score <= 70:
            action = ActionCode.HARD_BLOCK
        elif score <= 85:
            action = ActionCode.FREEZE_AND_REPORT
        else:
            action = ActionCode.CRITICAL_REPORT

        return RiskScore(
            score=score,
            level=level,
            contributing_factors=factors,
            recommended_action=action,
            model_version=active.model_version,
            explanation=explanations if explanations else None,
        )

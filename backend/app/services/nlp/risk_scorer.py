"""Risk scorer module.

Computes a composite risk score (0-100) from classifier output, extracted
entities, session context, and prior fraud reports. The score is mapped
to a risk level (LOW / MEDIUM / HIGH / CRITICAL) and a recommended action.
"""

from typing import List

from pydantic import BaseModel

from app.schemas.analyze import ClassificationResult
from app.schemas.entity import EntityType, ExtractedEntity
from app.schemas.risk import ActionCode, RiskLevel, RiskScore


class SessionContext(BaseModel):
    """Contextual information for a single analysis session."""

    classifier_output: ClassificationResult
    extracted_entities: List[ExtractedEntity]
    contact_initiated_by: str
    time_since_session_start: int  # seconds
    number_of_messages: int
    is_during_active_upi_session: bool
    prior_reports_for_sender: int


class RiskScorer:
    """Compute composite risk score from session context.

    Scoring weights:
        - Classifier confidence: 35%
        - High-risk entities:    25%
        - Contact direction:     20%
        - Prior fraud reports:   20%
    """

    def score(self, session_context: SessionContext) -> RiskScore:
        """Compute the risk score for a session.

        Args:
            session_context: Full session context including classifier output,
                extracted entities, and metadata.

        Returns:
            RiskScore with numeric score, level, contributing factors, and
            recommended action.
        """
        score = 0.0
        contributing_factors: List[str] = []

        # 1. Classifier Confidence (Weight 35%)
        classifier_score = session_context.classifier_output.confidence * 35
        score += classifier_score
        if classifier_score > 20:
            contributing_factors.append(
                f"High NLP scam confidence ({session_context.classifier_output.confidence:.2f})"
            )

        # 2. Presence of High-Risk Entities (Weight 25%)
        high_risk_types = {
            EntityType.ANYDESK,
            EntityType.TEAMVIEWER,
            EntityType.URL_SHORTLINK,
            EntityType.APK,
        }
        has_high_risk_entity = any(
            e.entity_type in high_risk_types for e in session_context.extracted_entities
        )
        if has_high_risk_entity:
            score += 25
            contributing_factors.append(
                "Detected high-risk entities (Remote Access/Shortlinks)"
            )

        # 3. Contact Initiation Direction (Weight 20%)
        if session_context.contact_initiated_by == "unknown":
            score += 20
            contributing_factors.append("Inbound contact from unknown sender")

        # 4. Prior Fraud Reports (Weight 20%)
        if session_context.prior_reports_for_sender > 0:
            reports_score = min(20, session_context.prior_reports_for_sender * 5)
            score += reports_score
            contributing_factors.append(
                f"Sender has {session_context.prior_reports_for_sender} prior fraud reports"
            )

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
            contributing_factors=contributing_factors,
            recommended_action=action,
        )

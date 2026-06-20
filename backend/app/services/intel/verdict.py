from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.analyze import ScamType
from app.schemas.entity import ExtractedEntity
from app.schemas.risk import ActionCode, RiskLevel, ShapAttribution


class Modality(str, Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    IMAGE = "IMAGE"


class Verdict(BaseModel):
    session_id: str
    is_scam: bool
    scam_type: ScamType
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    confidence: float
    recommended_action: ActionCode
    entities: List[ExtractedEntity]
    modality: Modality
    attributions: List[ShapAttribution] = []
    model_tier: str = "unknown"
    created_at: datetime


def build_verdict(
    *,
    session_id: str,
    is_scam: bool,
    scam_type: ScamType,
    risk_score: float,
    risk_level: RiskLevel,
    confidence: float,
    recommended_action: ActionCode,
    entities: List[ExtractedEntity],
    modality: Modality,
    attributions: Optional[List[ShapAttribution]] = None,
    model_tier: str = "unknown",
    created_at: Optional[datetime] = None,
) -> Verdict:
    return Verdict(
        session_id=session_id,
        is_scam=is_scam,
        scam_type=scam_type,
        risk_score=risk_score,
        risk_level=risk_level,
        confidence=confidence,
        recommended_action=recommended_action,
        entities=entities,
        modality=modality,
        attributions=attributions or [],
        model_tier=model_tier,
        created_at=created_at or datetime.now(timezone.utc),
    )

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ActionCode(str, Enum):
    NONE = "NONE"
    SOFT_WARNING = "SOFT_WARNING"
    HARD_BLOCK = "HARD_BLOCK"
    FREEZE_AND_REPORT = "FREEZE_AND_REPORT"
    CRITICAL_REPORT = "CRITICAL_REPORT"
    COACHED_VICTIM_INTERVENTION = "COACHED_VICTIM_INTERVENTION"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ShapAttribution(BaseModel):
    feature: str
    value: float
    shap_value: float
    direction: str  # "increases" or "decreases" risk


class RiskScore(BaseModel):
    score: int
    level: RiskLevel
    contributing_factors: List[str]
    recommended_action: ActionCode
    model_version: str = "unknown"
    explanation: Optional[List[ShapAttribution]] = None

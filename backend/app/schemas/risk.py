from enum import Enum
from pydantic import BaseModel
from typing import List

class ActionCode(str, Enum):
    NONE = "NONE"
    SOFT_WARNING = "SOFT_WARNING"
    HARD_BLOCK = "HARD_BLOCK"
    FREEZE_AND_REPORT = "FREEZE_AND_REPORT"
    CRITICAL_REPORT = "CRITICAL_REPORT"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class RiskScore(BaseModel):
    score: int
    level: RiskLevel
    contributing_factors: List[str]
    recommended_action: ActionCode

"""Behavioral Biometrics endpoint.

Collects and analyzes behavioral signals from the Android SDK:
- Typing speed changes during conversation
- Copy-paste of OTPs or sensitive data
- App switching patterns (payment app <-> messaging app)
- Screen recording / accessibility service detection
- Hesitation patterns (long pauses before action)

These signals are combined into a behavioral risk score that
supplements the NLP-based risk assessment.
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BehavioralSignal(BaseModel):
    """A single behavioral signal from the client SDK."""

    signal_type: str = Field(
        ...,
        description="Type of signal: typing_speed_change, otp_copy_paste, "
        "app_switch, screen_recording, accessibility_service, hesitation, "
        "rapid_tapping, overlay_detected",
    )
    value: float = Field(
        ...,
        description="Numeric value (e.g., speed ratio, count, boolean as 0/1)",
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp of when the signal was captured",
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Additional context for the signal",
    )


class BehavioralAnalysisRequest(BaseModel):
    """Request containing behavioral signals from a session."""

    session_id: str = Field(..., min_length=1, max_length=100)
    signals: List[BehavioralSignal] = Field(..., min_length=1)
    device_fingerprint: Optional[str] = None


class BehavioralRiskResult(BaseModel):
    """Result of behavioral analysis."""

    behavioral_risk_score: float = Field(
        ..., ge=0.0, le=1.0, description="Risk score 0.0 (safe) to 1.0 (suspicious)"
    )
    signals_analyzed: int
    high_risk_signals: List[str]
    recommendation: str


class BehavioralAnalysisResponse(BaseModel):
    """Full behavioral analysis response."""

    session_id: str
    result: BehavioralRiskResult
    processing_time_ms: int


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# Signal weights and thresholds
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS = {
    "typing_speed_change": 0.15,  # Sudden speed change = coached victim
    "otp_copy_paste": 0.25,  # Copying OTP = victim being directed
    "app_switch": 0.10,  # Switching between payment/messaging
    "screen_recording": 0.20,  # Screen recording during payment
    "accessibility_service": 0.15,  # Accessibility service = overlay attack risk
    "hesitation": 0.05,  # Long pauses before action
    "rapid_tapping": 0.05,  # Rapid tapping = bot or coached
    "overlay_detected": 0.30,  # Screen overlay = active attack
}


def _compute_behavioral_risk(
    signals: List[BehavioralSignal],
) -> tuple[float, List[str]]:
    """Compute behavioral risk score from signals.

    Args:
        signals: List of behavioral signals from the SDK.

    Returns:
        Tuple of (risk_score, high_risk_signal_types).
    """
    total_score = 0.0
    high_risk_signals: List[str] = []

    for signal in signals:
        weight = SIGNAL_WEIGHTS.get(signal.signal_type, 0.05)

        # Normalize signal value to 0-1 range
        if signal.signal_type == "otp_copy_paste":
            # Any OTP copy-paste is high risk
            normalized = min(1.0, signal.value)
        elif signal.signal_type == "typing_speed_change":
            # Speed change ratio: 1.0 = normal, >2.0 = suspicious
            normalized = min(1.0, max(0, (signal.value - 1.0) / 3.0))
        elif signal.signal_type in (
            "screen_recording",
            "accessibility_service",
            "overlay_detected",
        ):
            # Binary: any detection is full risk
            normalized = min(1.0, signal.value)
        elif signal.signal_type == "app_switch":
            # More switches = higher risk
            normalized = min(1.0, signal.value / 10.0)
        elif signal.signal_type == "hesitation":
            # Longer hesitation = more coached
            normalized = min(1.0, signal.value / 30.0)
        else:
            normalized = min(1.0, signal.value)

        contribution = weight * normalized
        total_score += contribution

        if normalized > 0.5:
            high_risk_signals.append(signal.signal_type)

    return min(1.0, total_score), high_risk_signals


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/behavioral-signal",
    response_model=BehavioralAnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def analyze_behavioral_signals(
    request: BehavioralAnalysisRequest,
    _: bool = Depends(verify_api_key),
) -> BehavioralAnalysisResponse:
    """Analyze behavioral signals from the Android SDK.

    Collects signals like typing speed changes, OTP copy-paste events,
    app switching patterns, and overlay detection. Returns a behavioral
    risk score that supplements the NLP-based assessment.
    """
    start_time = time.time()

    try:
        risk_score, high_risk = _compute_behavioral_risk(request.signals)

        # Generate recommendation
        if risk_score >= 0.7:
            recommendation = (
                "High behavioral risk detected. Possible signs of a coached victim "
                "or active screen overlay attack. Consider immediate intervention."
            )
        elif risk_score >= 0.4:
            recommendation = (
                "Moderate behavioral risk. Unusual interaction patterns detected. "
                "Monitor session closely and consider showing a warning."
            )
        elif risk_score >= 0.2:
            recommendation = (
                "Low behavioral risk. Some minor anomalies detected but within "
                "normal range."
            )
        else:
            recommendation = (
                "Behavioral patterns appear normal. No intervention needed."
            )

        processing_time_ms = max(1, int((time.time() - start_time) * 1000))

        logger.info(
            "Behavioral analysis: session=%s risk=%.2f signals=%d high_risk=%s",
            request.session_id,
            risk_score,
            len(request.signals),
            high_risk,
        )

        return BehavioralAnalysisResponse(
            session_id=request.session_id,
            result=BehavioralRiskResult(
                behavioral_risk_score=risk_score,
                signals_analyzed=len(request.signals),
                high_risk_signals=high_risk,
                recommendation=recommendation,
            ),
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        logger.error("Error analyzing behavioral signals: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze behavioral signals",
        )

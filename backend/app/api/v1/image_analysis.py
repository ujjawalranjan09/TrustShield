"""QR Code and Image Analysis endpoint.

Analyzes uploaded images for:
- QR code content (detects payment request QR codes vs receipt QR codes)
- Fake payment screenshot detection (metadata analysis)
- Suspicious URL extraction from images

Uses pyzbar for QR decoding and Pillow for image metadata analysis.
Falls back gracefully if optional dependencies are not installed.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.auth import verify_api_key
from app.config import settings
from app.services.intel.verdict import Modality, build_verdict
from app.services.intel.ingest_normalizer import normalize_and_emit

logger = logging.getLogger(__name__)

router = APIRouter()

# Try to import optional dependencies
try:
    from pyzbar.pyzbar import decode as qr_decode
    from PIL import Image
    import io

    _image_deps_available = True
except ImportError:
    _image_deps_available = False
    logger.warning("pyzbar/Pillow not installed — image analysis disabled")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class QRCodeResult(BaseModel):
    """Result of QR code analysis."""

    content: str
    content_type: str  # 'upi_payment', 'url', 'text', 'unknown'
    is_suspicious: bool
    risk_reasons: List[str]


class ImageAnalysisResult(BaseModel):
    """Full image analysis result."""

    has_qr_code: bool
    qr_codes: List[QRCodeResult]
    has_suspicious_content: bool
    image_hash: str
    analysis_notes: List[str]
    risk_level: str


class AnalyzeImageResponse(BaseModel):
    """Response for image analysis endpoint."""

    result: ImageAnalysisResult
    processing_time_ms: int
    verdict: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

SUSPICIOUS_URL_PATTERNS = [
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "is.gd",
    "rb.gy",
    "cutt.ly",
    ".apk",
    "anydesk",
    "teamviewer",
]

UPI_PAYMENT_INDICATORS = [
    "upi://",
    "upi://pay",
    "pn=",  # payee name
    "pa=",  # payee address
    "am=",  # amount
    "tn=",  # transaction note
]


def _classify_qr_content(content: str) -> tuple[str, bool, List[str]]:
    """Classify QR code content and assess risk.

    Args:
        content: Decoded QR code string.

    Returns:
        Tuple of (content_type, is_suspicious, risk_reasons).
    """
    content_lower = content.lower().strip()
    reasons: List[str] = []

    # Check for UPI payment QR
    if any(ind in content_lower for ind in UPI_PAYMENT_INDICATORS):
        # UPI QR that requests money (payment request) is suspicious
        if "am=" in content_lower:
            reasons.append("QR code contains a payment request with preset amount")
        return "upi_payment", len(reasons) > 0, reasons

    # Check for URLs
    if content_lower.startswith("http://") or content_lower.startswith("https://"):
        for pattern in SUSPICIOUS_URL_PATTERNS:
            if pattern in content_lower:
                reasons.append(f"URL contains suspicious domain: {pattern}")
                return "url", True, reasons
        return "url", False, reasons

    # Check for AnyDesk/TeamViewer IDs
    if content_lower.isdigit() and 9 <= len(content_lower) <= 10:
        reasons.append("QR code contains what appears to be a remote access ID")
        return "unknown", True, reasons

    # General text
    return "text", False, reasons


def _analyze_image_metadata(image_bytes: bytes) -> List[str]:
    """Analyze image metadata for signs of tampering.

    Args:
        image_bytes: Raw image bytes.

    Returns:
        List of analysis notes.
    """
    notes: List[str] = []

    if not _image_deps_available:
        notes.append("Image metadata analysis unavailable (Pillow not installed)")
        return notes

    try:
        img = Image.open(io.BytesIO(image_bytes))

        # Check for EXIF data (screenshots typically have minimal EXIF)
        exif_data = img.getexif() if hasattr(img, "getexif") else {}
        if len(exif_data) > 10:
            notes.append("Image has extensive EXIF data — may not be a screenshot")

        # Check image dimensions
        width, height = img.size
        if width > 3000 or height > 3000:
            notes.append("Unusually high resolution for a screenshot")

        # Check for common screenshot dimensions
        common_screenshot_widths = [1080, 1170, 1242, 1284, 1290, 1440, 2560]
        if width in common_screenshot_widths:
            notes.append("Dimensions match common mobile screenshot")

        # Check format
        notes.append(f"Image format: {img.format or 'unknown'}")
        notes.append(f"Dimensions: {width}x{height}")

    except Exception as e:
        notes.append(f"Could not analyze image metadata: {e}")

    return notes


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/analyze-image",
    response_model=AnalyzeImageResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def analyze_image(
    file: UploadFile = File(..., description="Image file to analyze"),
    _: bool = Depends(verify_api_key),
) -> AnalyzeImageResponse:
    """Analyze an uploaded image for fraud indicators.

    Detects QR codes and classifies them (UPI payment request vs receipt),
    extracts suspicious URLs, and checks image metadata for signs of
    fake payment screenshots.
    """
    start_time = time.time()

    try:
        # Read file
        image_bytes = await file.read()

        if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")

        # Compute hash
        image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]

        qr_results: List[QRCodeResult] = []
        has_qr = False
        analysis_notes: List[str] = []

        # QR code analysis
        if settings.image_qr_decode_enabled and _image_deps_available:
            try:
                img = Image.open(io.BytesIO(image_bytes))
                decoded_objects = qr_decode(img)

                for obj in decoded_objects:
                    has_qr = True
                    content = obj.data.decode("utf-8", errors="replace")
                    content_type, is_suspicious, reasons = _classify_qr_content(content)
                    qr_results.append(
                        QRCodeResult(
                            content=content[:500],  # Truncate long content
                            content_type=content_type,
                            is_suspicious=is_suspicious,
                            risk_reasons=reasons,
                        )
                    )
            except Exception as e:
                analysis_notes.append(f"QR decode error: {e}")
        else:
            analysis_notes.append("QR analysis unavailable (pyzbar not installed)")

        # Image metadata analysis
        metadata_notes = _analyze_image_metadata(image_bytes)
        analysis_notes.extend(metadata_notes)

        # Determine overall risk
        has_suspicious = any(qr.is_suspicious for qr in qr_results)
        suspicious_count = sum(1 for qr in qr_results if qr.is_suspicious)

        if suspicious_count >= 2:
            risk_level = "critical"
        elif suspicious_count == 1:
            risk_level = "high"
        elif has_qr:
            risk_level = "medium"
        else:
            risk_level = "low"

        processing_time_ms = max(1, int((time.time() - start_time) * 1000))

        logger.info(
            "Image analysis: hash=%s qr=%d suspicious=%d (%dms)",
            image_hash,
            len(qr_results),
            suspicious_count,
            processing_time_ms,
        )

        # Build entities from QR codes and analysis
        from app.schemas.entity import EntityType, ExtractedEntity
        from app.schemas.risk import RiskLevel, ActionCode

        entities = []
        for qr in qr_results:
            if qr.content_type == "upi_payment":
                etype = EntityType.UPI
            elif qr.content_type == "url":
                etype = EntityType.URL_SHORTLINK
            else:
                etype = EntityType.APK
            entities.append(ExtractedEntity(
                entity_type=etype,
                value=qr.content,
                start_char=0,
                end_char=len(qr.content),
                confidence_score=1.0 if qr.is_suspicious else 0.5,
            ))

        risk_level_enum = {
            "critical": RiskLevel.CRITICAL,
            "high": RiskLevel.HIGH,
            "medium": RiskLevel.MEDIUM,
            "low": RiskLevel.LOW,
        }.get(risk_level, RiskLevel.LOW)

        risk_score_map = {
            "critical": 90.0,
            "high": 70.0,
            "medium": 45.0,
            "low": 15.0,
        }
        risk_score = risk_score_map.get(risk_level, 15.0)

        action_map = {
            "critical": ActionCode.CRITICAL_REPORT,
            "high": ActionCode.HARD_BLOCK,
            "medium": ActionCode.SOFT_WARNING,
            "low": ActionCode.NONE,
        }
        recommended_action = action_map.get(risk_level, ActionCode.NONE)

        session_id = str(uuid.uuid4())

        verdict = build_verdict(
            session_id=session_id,
            is_scam=has_suspicious,
            scam_type=__import__("app.schemas.analyze", fromlist=["ScamType"]).ScamType.PHISHING if has_suspicious else __import__("app.schemas.analyze", fromlist=["ScamType"]).ScamType.UNKNOWN,
            risk_score=risk_score,
            risk_level=risk_level_enum,
            confidence=1.0 if has_qr else 0.3,
            recommended_action=recommended_action,
            entities=entities,
            modality=Modality.IMAGE,
        )

        # Fire-and-forget: normalize and emit to sinks
        try:
            asyncio.create_task(normalize_and_emit(
                event_type="image",
                payload={
                    "session_id": session_id,
                    "image_hash": image_hash,
                    "qr_codes": [qr.model_dump() for qr in qr_results],
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "is_scam": has_suspicious,
                    "flagged_entities": [e.model_dump() for e in entities],
                },
                db=None,
            ))
        except Exception as emit_err:
            logger.warning("Failed to emit image ingest event: %s", emit_err)

        return AnalyzeImageResponse(
            result=ImageAnalysisResult(
                has_qr_code=has_qr,
                qr_codes=qr_results,
                has_suspicious_content=has_suspicious,
                image_hash=image_hash,
                analysis_notes=analysis_notes,
                risk_level=risk_level,
            ),
            processing_time_ms=processing_time_ms,
            verdict=verdict.model_dump(mode="json"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing image: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze image",
        )

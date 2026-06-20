"""WhatsApp Business API webhook handler."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import require_role
from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class WhatsAppMessage(BaseModel):
    object: str
    entry: list


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """Handle WhatsApp Business API webhook messages."""
    body = await request.json()

    # Verify webhook (for setup)
    if "hub.mode" in body:
        if body.get("hub.mode") == "subscribe" and body.get("hub.verify_token") == settings.whatsapp_verify_token:
            return {"hub.challenge": body.get("hub.challenge")}
        raise HTTPException(status_code=403, detail="Verification failed")

    # Process incoming messages
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    await _process_message(msg)
    except Exception as e:
        logger.error("WhatsApp webhook error: %s", e)

    return {"status": "ok"}


async def _process_message(msg: dict):
    """Process a single WhatsApp message."""
    msg_type = msg.get("type")
    if msg_type != "text":
        return

    text = msg.get("text", {}).get("body", "")
    from_number = msg.get("from", "")

    if not text or not from_number:
        return

    # Run through NLP pipeline
    services = _get_consumer_services()
    cleaned = services["preprocessor"].clean(text)
    entities = services["extractor"].extract(cleaned)
    classification = await services["classifier"].classify(cleaned)

    from app.services.nlp.risk_scorer import SessionContext
    context = SessionContext(
        classifier_output=classification,
        extracted_entities=entities,
        contact_initiated_by="unknown",
        time_since_session_start=0,
        number_of_messages=1,
        is_during_active_upi_session=False,
        prior_reports_for_sender=0,
    )
    risk = services["scorer"].score(context)

    # Generate reply
    from app.services.nlp.warning_generator import WarningGenerator
    gen = WarningGenerator()
    warnings = gen.generate(
        scam_type=classification.scam_type.value,
        risk_score=risk.score,
        entities=entities,
        locale="hi",
    )

    reply = warnings["warning_hi"] or "This message appears safe. Stay vigilant."

    logger.info("WhatsApp scan: from=%s score=%d reply_length=%d", from_number, risk.score, len(reply))

    # In production: send reply via WhatsApp Business API
    # await _send_whatsapp_reply(from_number, reply)


def _get_consumer_services():
    from app.services.nlp.preprocessor import TextPreprocessor
    from app.services.nlp.entity_extractor import EntityExtractor
    from app.services.nlp.classifier import ScamClassifier
    from app.services.nlp.risk_scorer import RiskScorer
    return {
        "preprocessor": TextPreprocessor(),
        "extractor": EntityExtractor(),
        "classifier": ScamClassifier(),
        "scorer": RiskScorer(),
    }


class SendWarningRequest(BaseModel):
    to: str
    summary: str


async def _get_db_dep():
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session


@router.post("/whatsapp/send-warning")
async def send_warning(
    req: SendWarningRequest,
    db=Depends(_get_db_dep),
    _user: User = Depends(require_role("analyst")),
):
    """Send a WhatsApp scam warning. Requires analyst role."""
    from app.services.intervention.whatsapp_sender import send_whatsapp_warning

    result = await send_whatsapp_warning(req.to, req.summary, db)
    if not result["sent"]:
        raise HTTPException(status_code=502, detail=f"WhatsApp send failed: {result['status']}")
    return result

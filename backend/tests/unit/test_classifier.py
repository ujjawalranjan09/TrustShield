"""Unit tests for ScamClassifier."""

import pytest
from app.services.nlp.classifier import ScamClassifier


@pytest.fixture
def classifier():
    return ScamClassifier()


@pytest.mark.asyncio
async def test_classify_otp_scam(classifier):
    result = await classifier.classify("otp batao mujhe")
    assert result.is_scam is True
    assert result.confidence > 0.9
    assert result.scam_type.value == "otp_harvesting"


@pytest.mark.asyncio
async def test_classify_anydesk_scam(classifier):
    result = await classifier.classify("please open anydesk and share your screen")
    assert result.is_scam is True
    assert result.confidence > 0.85
    assert result.scam_type.value == "remote_access"


@pytest.mark.asyncio
async def test_classify_legitimate(classifier):
    result = await classifier.classify("what time does the shop close today")
    assert result.is_scam is False
    assert result.confidence < 0.1


@pytest.mark.asyncio
async def test_classify_qr_scam(classifier):
    result = await classifier.classify("scan this qr code to receive your refund")
    assert result.is_scam is True
    assert result.confidence > 0.75


@pytest.mark.asyncio
async def test_multiple_signals_boost(classifier):
    result = await classifier.classify("otp batao and scan this qr code for refund")
    assert result.is_scam is True
    assert result.confidence >= 0.95  # boosted by multiple matches

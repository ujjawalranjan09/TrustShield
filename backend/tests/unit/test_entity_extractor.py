"""Unit tests for EntityExtractor."""

from app.services.nlp.entity_extractor import EntityExtractor


def test_extract_upi():
    ext = EntityExtractor()
    entities = ext.extract("send money to user@ybl")
    types = [e.entity_type.value for e in entities]
    assert "UPI" in types


def test_extract_phone():
    ext = EntityExtractor()
    entities = ext.extract("call me at 9876543210")
    types = [e.entity_type.value for e in entities]
    assert "PHONE" in types


def test_extract_anydesk():
    ext = EntityExtractor()
    entities = ext.extract("open anydesk my id is 123456789")
    types = [e.entity_type.value for e in entities]
    assert "ANYDESK" in types


def test_extract_ifsc():
    ext = EntityExtractor()
    entities = ext.extract("my IFSC code is SBIN0001234")
    types = [e.entity_type.value for e in entities]
    assert "IFSC" in types


def test_extract_no_entities():
    ext = EntityExtractor()
    entities = ext.extract("hello how are you today")
    assert len(entities) == 0

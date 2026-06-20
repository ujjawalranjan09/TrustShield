"""Unit tests for PII masking utility."""

from app.utils.pii import mask_vpa, mask_phone, mask_email, mask_text


def test_mask_vpa():
    assert mask_vpa("user@ybl") == "u***r@ybl"
    assert mask_vpa("ab@paytm") == "***@paytm"


def test_mask_phone():
    assert mask_phone("9876543210") == "98****3210"
    assert mask_phone("+91 9876543210") == "98****3210"


def test_mask_email():
    assert mask_email("john@example.com") == "j***n@example.com"
    assert mask_email("ab@test.org") == "***@test.org"


def test_mask_text():
    text = "call 9876543210 or send to user@ybl"
    masked = mask_text(text)
    assert "9876543210" not in masked
    assert "user@ybl" not in masked
    assert "98****3210" in masked

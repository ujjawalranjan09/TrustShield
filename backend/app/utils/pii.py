"""PII masking and redaction utilities.

Masking: safe display (for logs, dashboards).
Redaction: removes PII entirely (for external boundaries — LLM calls, alerts).
"""

import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# PII Patterns
# ---------------------------------------------------------------------------

# Phone numbers (Indian: 91XXXXXXXXXX, 0XXXXXXXXXX, just 10 digits starting 7-9)
PHONE_PATTERN = re.compile(r"(?:\+?91[\s-]?)?[789]\d{9}")

# UPI VPAs: user@upi or user@bankhandle
VPA_PATTERN = re.compile(r"[\w.-]+@(?:ybl|okaxis|oksbi|okhdfcbank|paytm|ibl|upi|axl|icici|sbi|hdfc|yesbank|kotak|freecharge|phonepe|googlepay|amazonpay)")

# Generic email
EMAIL_PATTERN = re.compile(r"[\w.-]+@[\w.-]+\.\w+")

# IFSC codes (4 letters + 7 alphanumeric)
IFSC_PATTERN = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")

# Aadhaar-like (12 digits, optionally spaced)
AADHAAR_PATTERN = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")

# PAN (10 characters: AAAAA9999A)
PAN_PATTERN = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]{1}")

# Account numbers (9-18 digits, common pattern)
ACCOUNT_PATTERN = re.compile(r"\b\d{9,18}\b")


# ---------------------------------------------------------------------------
# Masking functions (for logs / safe display)
# ---------------------------------------------------------------------------


def mask_vpa(vpa: str) -> str:
    """Mask a UPI VPA: user@provider -> u***r@provider."""
    if "@" not in vpa:
        return "***"
    local, domain = vpa.split("@", 1)
    if len(local) <= 2:
        return f"***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def mask_phone(phone: str) -> str:
    """Mask a phone number: 9876543210 -> 98****3210.

    Strips the Indian country code (+91 / 91 / leading 0) so the masked
    prefix reflects the subscriber number, not the dialing prefix.
    """
    digits = re.sub(r"\D", "", phone)
    # Strip Indian country code / trunk prefix so masking is stable
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) > 10:
        digits = digits[1:]
    if len(digits) < 6:
        return "***"
    return f"{digits[:2]}****{digits[-4:]}"


def mask_email(email: str) -> str:
    """Mask an email: user@domain -> u***r@domain."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def mask_text(text: str) -> str:
    """Mask all PII patterns found in arbitrary text (for logs/exports)."""
    # Mask phone numbers
    text = PHONE_PATTERN.sub(lambda m: mask_phone(m.group()), text)
    # Mask VPAs
    text = VPA_PATTERN.sub(lambda m: mask_vpa(m.group()), text)
    # Mask emails
    text = EMAIL_PATTERN.sub(lambda m: mask_email(m.group()), text)
    return text


# ---------------------------------------------------------------------------
# Redaction functions (for external boundaries — LLM calls, alerts, webhooks)
# ---------------------------------------------------------------------------


def redact(text: str) -> str:
    """Redact ALL PII from text before it leaves the system.

    This is the single chokepoint through which all data destined for
    external services (LLM API, Whisper, alert webhooks, Sentry) must pass.

    Redaction removes PII entirely (replaces with '[REDACTED]') rather
    than masking, because external services should never see even masked
    PII patterns.

    Args:
        text: The input text that may contain PII.

    Returns:
        Text with all PII replaced by '[REDACTED]'.
    """
    text = PHONE_PATTERN.sub("[REDACTED]", text)
    text = VPA_PATTERN.sub("[REDACTED]", text)
    text = EMAIL_PATTERN.sub("[REDACTED]", text)
    text = IFSC_PATTERN.sub("[REDACTED]", text)
    text = AADHAAR_PATTERN.sub("[REDACTED]", text)
    text = PAN_PATTERN.sub("[REDACTED]", text)
    return text


def redact_dict(data: dict, keys_to_redact: List[str] = None) -> dict:
    """Redact PII from specified keys in a dict.

    If keys_to_redact is None, redacts all string values recursively.

    Args:
        data: The dict to redact.
        keys_to_redact: List of keys whose values should be redacted.
                        If None, redacts all string values.

    Returns:
        A new dict with PII redacted from the specified values.
    """
    if keys_to_redact:
        result = dict(data)
        for key in keys_to_redact:
            if key in result and isinstance(result[key], str):
                result[key] = redact(result[key])
        return result
    else:
        return _redact_dict_recursive(data)


def _redact_dict_recursive(data) -> object:
    """Recursively redact all string values in a data structure."""
    if isinstance(data, str):
        return redact(data)
    elif isinstance(data, dict):
        return {k: _redact_dict_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_redact_dict_recursive(item) for item in data]
    else:
        return data


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def contains_pii(text: str) -> bool:
    """Check if text contains any PII patterns.

    Useful as a guard assertion in tests.
    """
    return bool(
        PHONE_PATTERN.search(text)
        or VPA_PATTERN.search(text)
        or EMAIL_PATTERN.search(text)
        or IFSC_PATTERN.search(text)
        or AADHAAR_PATTERN.search(text)
        or PAN_PATTERN.search(text)
    )


def get_pii_spans(text: str) -> List[Tuple[int, int, str]]:
    """Return (start, end, type) spans for all PII found in text."""
    spans = []
    for pattern, name in [
        (PHONE_PATTERN, "phone"),
        (VPA_PATTERN, "vpa"),
        (EMAIL_PATTERN, "email"),
        (IFSC_PATTERN, "ifsc"),
        (AADHAAR_PATTERN, "aadhaar"),
        (PAN_PATTERN, "pan"),
    ]:
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end(), name))
    # Sort by start position
    spans.sort(key=lambda s: s[0])
    return spans
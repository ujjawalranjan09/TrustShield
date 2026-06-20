"""Feature engineering pipeline for GBM model.

Extracts text, entity, conversation, and pattern features from
labeled conversations. Used for both training and inference.
"""

import re
from typing import Any, Dict, List

import numpy as np

# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

URGENCY_WORDS = {
    "urgent", "immediately", "jaldi", "turant", "abhi", "warning", "block",
    "freeze", "fir", "deactivate", "expire", "last chance", "final warning",
    "24 hours", "permanently", "suspend", "emergency",
}

FINANCIAL_WORDS = {
    "account", "otp", "pin", "upi", "refund", "payment", "transaction",
    "bank", "card", "balance", "amount", "transfer", "credit", "debit",
    "atm", "kyc", "ifsc", "vpa", "micr",
}

REMOTE_ACCESS_WORDS = {
    "anydesk", "teamviewer", "screen share", "remote access", "quick support",
    "remote desktop", "install app", "download app",
}

PHISHING_INDICATORS = {
    "http", "https", ".com", ".in", ".net", "click here", "verify",
    "link", "portal", "update",
}

HINDI_WORDS = {
    "aapka", "karo", "karna", "hai", "hoga", "ho", "bhejo", "batao",
    "share", "kar", "raha", "hu", "main", "ye", "wo", "aur", "phir",
    "ok", "haan", "nahi", "theek",
}


def _text_length(text: str) -> int:
    return len(text)


def _word_count(text: str) -> int:
    return len(text.split())


def _caps_ratio(text: str) -> float:
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return 0.0
    return sum(1 for c in alpha if c.isupper()) / len(alpha)


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for c in text if c.isdigit()) / len(text)


def _hindi_ratio(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 0.0
    return sum(1 for w in words if w in HINDI_WORDS) / len(words)


def _entity_counts(messages: List[Dict]) -> Dict[str, int]:
    full_text = " ".join(m["text"] for m in messages).lower()
    return {
        "phone_count": len(re.findall(r'\b[6-9]\d{9}\b', full_text)),
        "upi_count": len(re.findall(r'\b\w+@\w+\b', full_text)),
        "url_count": len(re.findall(r'https?://\S+', full_text)),
        "anydesk_count": full_text.count("anydesk"),
        "teamviewer_count": full_text.count("teamviewer"),
        "apk_count": full_text.count(".apk"),
        "ifsc_count": len(re.findall(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', full_text.upper())),
    }


def _conversation_features(messages: List[Dict]) -> Dict[str, float]:
    texts = [m["text"] for m in messages]
    senders = [m["sender"] for m in messages]
    return {
        "message_count": len(messages),
        "avg_msg_length": np.mean([len(t) for t in texts]) if texts else 0,
        "total_text_length": sum(len(t) for t in texts),
        "sender_diversity": len(set(senders)),
        "scammer_msg_ratio": sum(1 for s in senders if s == "scammer") / max(len(senders), 1),
    }


def _pattern_features(text: str) -> Dict[str, int]:
    text_lower = text.lower()
    return {
        "urgency_count": sum(1 for w in URGENCY_WORDS if w in text_lower),
        "financial_count": sum(1 for w in FINANCIAL_WORDS if w in text_lower),
        "remote_access_count": sum(1 for w in REMOTE_ACCESS_WORDS if w in text_lower),
        "phishing_indicator_count": sum(1 for w in PHISHING_INDICATORS if w in text_lower),
        "has_question": 1 if "?" in text else 0,
        "has_exclamation": 1 if "!" in text else 0,
        "exclamation_count": text.count("!"),
        "question_count": text.count("?"),
    }


def extract_features(messages: List[Dict]) -> Dict[str, Any]:
    """Extract all features from a conversation."""
    full_text = " ".join(m["text"] for m in messages)
    features = {}

    # Text features
    features["text_length"] = _text_length(full_text)
    features["word_count"] = _word_count(full_text)
    features["caps_ratio"] = _caps_ratio(full_text)
    features["digit_ratio"] = _digit_ratio(full_text)
    features["hindi_ratio"] = _hindi_ratio(full_text)

    # Entity features
    features.update(_entity_counts(messages))

    # Conversation features
    features.update(_conversation_features(messages))

    # Pattern features
    features.update(_pattern_features(full_text))

    return features


def get_feature_names() -> List[str]:
    """Return ordered list of feature names."""
    dummy_msgs = [{"sender": "user", "text": "test"}]
    return sorted(extract_features(dummy_msgs).keys())


def conversations_to_feature_matrix(conversations: List[Dict]) -> tuple:
    """Convert conversations to feature matrix + labels.

    Returns:
        (X: np.ndarray, y: np.ndarray, feature_names: List[str])
    """
    feature_names = get_feature_names()
    X = []
    y = []

    label_map = {
        "legitimate": 0,
        "otp_harvesting": 1,
        "vishing": 2,
        "remote_access": 3,
        "refund_scam": 4,
        "fake_support": 5,
        "phishing": 6,
        "sim_swap": 7,
    }

    for conv in conversations:
        features = extract_features(conv["messages"])
        row = [features.get(name, 0.0) for name in feature_names]
        X.append(row)

        scam_type = conv.get("scam_type", "none")
        if scam_type == "none" and conv.get("label") == "legitimate":
            label = 0
        else:
            label = label_map.get(scam_type, 0)
        y.append(label)

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32), feature_names

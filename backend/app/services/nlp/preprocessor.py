"""Text preprocessor module.

Normalizes and cleans raw chat text before entity extraction and
classification. Handles Unicode normalization, zero-width character
removal, abbreviation expansion, and truncation.
"""

import re
import unicodedata
from typing import Dict


class TextPreprocessor:
    """Clean and normalize chat text for downstream NLP processing."""

    def __init__(self) -> None:
        self.abbreviations: Dict[str, str] = {
            "plz": "please",
            "aap": "aap",
            "thx": "thanks",
            "u": "you",
            "ur": "your",
        }

    def clean(self, text: str) -> str:
        """Normalize, clean, and truncate text.

        Args:
            text: Raw chat text.

        Returns:
            Cleaned text with normalized unicode, no zero-width characters,
            expanded abbreviations, and max 512 tokens.
        """
        text = unicodedata.normalize("NFKD", text)
        text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)

        words = text.split()
        expanded_words = [self.abbreviations.get(word.lower(), word) for word in words]
        text = " ".join(expanded_words)

        text = re.sub(r"\s+", " ", text).strip()

        tokens = text.split()
        if len(tokens) > 512:
            tokens = tokens[:512]
            text = " ".join(tokens)

        return text

    def detect_language(self, text: str) -> str:
        """Detect the primary language of the text.

        Uses a simple keyword-based heuristic. Returns one of:
        'en', 'hi', 'hinglish', or 'mixed'.

        Args:
            text: Cleaned chat text.

        Returns:
            Language code string.
        """
        hindi_keywords = {"aap", "hai", "karo", "bhai", "batao", "kya"}
        english_keywords = {"the", "is", "please", "help", "share"}

        text_lower = text.lower()
        has_hindi = any(word in text_lower for word in hindi_keywords)
        has_english = any(word in text_lower for word in english_keywords)

        if has_hindi and has_english:
            return "mixed"
        elif has_hindi:
            return "hi"
        elif has_english:
            return "en"
        else:
            return "hinglish"

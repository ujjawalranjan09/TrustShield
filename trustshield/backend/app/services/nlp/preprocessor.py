import unicodedata
import re

class TextPreprocessor:
    def __init__(self):
        self.abbreviations = {
            "plz": "please",
            "aap": "aap",
            "thx": "thanks",
            "u": "you",
            "ur": "your",
        }

    def clean(self, text: str) -> str:
        # Normalize unicode characters
        text = unicodedata.normalize('NFKD', text)

        # Strip zero-width spaces and invisible characters
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)

        # Expand common Hindi SMS abbreviations
        words = text.split()
        expanded_words = [self.abbreviations.get(word.lower(), word) for word in words]
        text = ' '.join(expanded_words)

        # Remove duplicate whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Truncate to 512 tokens (roughly words for simple implementation)
        tokens = text.split()
        if len(tokens) > 512:
            tokens = tokens[:512]
            text = ' '.join(tokens)

        return text

    def detect_language(self, text: str) -> str:
        # A very basic language detection mock
        hindi_keywords = ['aap', 'hai', 'karo', 'bhai', 'batao', 'kya']
        english_keywords = ['the', 'is', 'please', 'help', 'share']

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
            # Default to mixed or hingeish for unknown
            return "hinglish"

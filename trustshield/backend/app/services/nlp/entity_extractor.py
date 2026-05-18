import sys
from pathlib import Path

# Add the backend path so we can import schemas and utils
backend_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(backend_dir))

from app.utils.regex_patterns import (
    UPI_PATTERN, PHONE_PATTERN, ANYDESK_PATTERN, TEAMVIEWER_PATTERN,
    URL_SHORTLINK_PATTERN, IFSC_PATTERN, APK_PATTERN
)
from app.schemas.entity import ExtractedEntity, EntityType

class EntityExtractor:
    def extract(self, text: str) -> list[ExtractedEntity]:
        entities = []

        # Helper to process matches
        def process_matches(pattern, entity_type, confidence):
            for match in pattern.finditer(text):
                entities.append(
                    ExtractedEntity(
                        entity_type=entity_type,
                        value=match.group(0),
                        start_char=match.start(),
                        end_char=match.end(),
                        confidence_score=confidence
                    )
                )

        process_matches(UPI_PATTERN, EntityType.UPI, 0.95)
        process_matches(PHONE_PATTERN, EntityType.PHONE, 0.90)
        process_matches(ANYDESK_PATTERN, EntityType.ANYDESK, 0.99)
        process_matches(TEAMVIEWER_PATTERN, EntityType.TEAMVIEWER, 0.99)
        process_matches(URL_SHORTLINK_PATTERN, EntityType.URL_SHORTLINK, 0.85)
        process_matches(IFSC_PATTERN, EntityType.IFSC, 0.98)
        process_matches(APK_PATTERN, EntityType.APK, 0.95)

        return entities

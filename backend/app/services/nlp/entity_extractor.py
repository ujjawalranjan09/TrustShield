"""Entity extractor module.

Extracts fraud-relevant entities (UPI IDs, phone numbers, remote access
codes, shortlinks, IFSC codes, APK links) from preprocessed text using
compiled regex patterns.
"""

import logging
import re
from typing import List

from app.schemas.entity import EntityType, ExtractedEntity
from app.utils.regex_patterns import (
    ANYDESK_PATTERN,
    APK_PATTERN,
    IFSC_PATTERN,
    PHONE_PATTERN,
    TEAMVIEWER_PATTERN,
    UPI_PATTERN,
    URL_SHORTLINK_PATTERN,
)

logger = logging.getLogger(__name__)


class EntityExtractor:
    """Extract fraud-relevant entities from text using regex patterns."""

    def extract(self, text: str) -> List[ExtractedEntity]:
        """Extract all fraud-relevant entities from the given text.

        Args:
            text: Preprocessed chat text.

        Returns:
            List of ExtractedEntity objects with type, value, position,
            and confidence score.
        """
        entities: List[ExtractedEntity] = []

        self._process_matches(text, UPI_PATTERN, EntityType.UPI, 0.95, entities)
        self._process_matches(text, PHONE_PATTERN, EntityType.PHONE, 0.90, entities)
        self._process_matches(
            text, ANYDESK_PATTERN, EntityType.ANYDESK, 0.99, entities, use_group=True
        )
        self._process_matches(
            text,
            TEAMVIEWER_PATTERN,
            EntityType.TEAMVIEWER,
            0.99,
            entities,
            use_group=True,
        )
        self._process_matches(
            text, URL_SHORTLINK_PATTERN, EntityType.URL_SHORTLINK, 0.85, entities
        )
        self._process_matches(text, IFSC_PATTERN, EntityType.IFSC, 0.98, entities)
        self._process_matches(text, APK_PATTERN, EntityType.APK, 0.95, entities)

        if entities:
            logger.debug("Extracted %d entities from text", len(entities))

        return entities

    @staticmethod
    def _process_matches(
        text: str,
        pattern: re.Pattern,  # type: ignore[type-arg]
        entity_type: EntityType,
        confidence: float,
        entities: List[ExtractedEntity],
        use_group: bool = False,
    ) -> None:
        """Process regex matches and append extracted entities.

        Args:
            text: Text to search.
            pattern: Compiled regex pattern.
            entity_type: EntityType enum value.
            confidence: Base confidence score.
            entities: List to append results to.
            use_group: If True, use capture group(1) for the value.
        """
        for match in pattern.finditer(text):
            value = match.group(1) if use_group and match.lastindex else match.group(0)
            entities.append(
                ExtractedEntity(
                    entity_type=entity_type,
                    value=value,
                    start_char=match.start(),
                    end_char=match.end(),
                    confidence_score=confidence,
                )
            )

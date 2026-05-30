from pydantic import BaseModel
from enum import Enum

class EntityType(str, Enum):
    UPI = "UPI"
    PHONE = "PHONE"
    ANYDESK = "ANYDESK"
    TEAMVIEWER = "TEAMVIEWER"
    URL_SHORTLINK = "URL_SHORTLINK"
    IFSC = "IFSC"
    APK = "APK"

class ExtractedEntity(BaseModel):
    entity_type: EntityType
    value: str
    start_char: int
    end_char: int
    confidence_score: float

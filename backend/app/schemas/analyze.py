from enum import Enum
from pydantic import BaseModel

class ScamType(str, Enum):
    UNKNOWN = "unknown"
    VISHING = "vishing"
    FAKE_SUPPORT = "fake_support"
    REFUND_SCAM = "refund_scam"
    OTP_HARVESTING = "otp_harvesting"
    REMOTE_ACCESS = "remote_access"
    PHISHING = "phishing"
    SIM_SWAP = "sim_swap"

class ClassificationResult(BaseModel):
    is_scam: bool
    confidence: float
    scam_type: ScamType
    inference_time_ms: int

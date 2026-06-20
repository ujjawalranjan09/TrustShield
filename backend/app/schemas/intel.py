"""Multi-bank fraud intelligence schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field


class BankRegisterRequest(BaseModel):
    bank_name: str = Field(..., min_length=1, max_length=200)
    bank_code: str = Field(..., min_length=2, max_length=20)
    contact_email: str = Field(..., min_length=5, max_length=255)
    contact_name: str = Field(..., min_length=1, max_length=200)


class BankRegisterResponse(BaseModel):
    bank_id: str
    api_key: str


class BankRegistrationRequest(BaseModel):
    bank_name: str = Field(..., min_length=1, max_length=200)
    bank_code: str = Field(..., min_length=2, max_length=20)
    contact_email: str = Field(..., min_length=5, max_length=255)
    contact_name: str = Field(..., min_length=1, max_length=200)


class BankRegistrationResponse(BaseModel):
    bank_id: str
    bank_name: str
    api_key: str
    message: str


class ShareEntityRequest(BaseModel):
    entity_value: str = Field(..., min_length=1, max_length=255)
    entity_type: str
    scam_type: str = Field(..., min_length=1, max_length=100)
    risk_score: int = Field(..., ge=0, le=100)
    incident_count: int = Field(default=1, ge=1)
    notes: Optional[str] = Field(None, max_length=500)


class ShareEntityResponse(BaseModel):
    shared_id: str
    cross_bank_risk_score: float
    total_reports: int
    banks_reporting: int
    message: str


class CrossBankLookupRequest(BaseModel):
    entity_value: str = Field(..., min_length=1, max_length=255)
    entity_type: str


class CrossBankLookupResponse(BaseModel):
    entity_hash: str
    entity_type: str
    is_known_fraudster: bool
    cross_bank_risk_score: float
    total_reports: int
    banks_reporting: int
    scam_types: List[str]
    risk_level: str


class NetworkStats(BaseModel):
    registered_banks: int
    shared_entities: int
    total_cross_bank_reports: int
    active_alerts: int

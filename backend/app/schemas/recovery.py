"""Recovery case schemas."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FraudType(str, Enum):
    VISHING = "vishing"
    UPI_FRAUD = "upi_fraud"
    SIM_SWAP = "sim_swap"
    QR_CODE_FRAUD = "qr_code_fraud"
    REMOTE_ACCESS = "remote_access"
    IDENTITY_THEFT = "identity_theft"
    PHISHING = "phishing"
    OTHER = "other"


class RecoveryCaseCreate(BaseModel):
    victim_name: str
    scam_type: str
    details: str


class RecoveryCaseResponse(BaseModel):
    case_id: str
    status: str
    created_at: datetime


class RecoveryRequest(BaseModel):
    fraud_type: FraudType
    amount_lost: float = Field(..., ge=0)
    scammer_info: Optional[str] = Field(None, max_length=500)
    incident_date: str
    victim_name: Optional[str] = Field(None, max_length=200)
    victim_phone: Optional[str] = Field(None, max_length=15)
    bank_name: Optional[str] = Field(None, max_length=200)
    upi_id: Optional[str] = Field(None, max_length=255)


class RecoveryStep(BaseModel):
    step_number: int
    title: str
    description: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    is_urgent: bool = False
    estimated_time: Optional[str] = None


class ComplaintDraft(BaseModel):
    title: str
    body: str
    sections: Dict[str, str]


class RecoveryPlan(BaseModel):
    case_id: str
    fraud_type: str
    amount_lost: float
    steps: List[RecoveryStep]
    complaint_draft: ComplaintDraft
    helpline_numbers: List[Dict[str, str]]
    next_deadline: Optional[str] = None


class RecoveryStatusResponse(BaseModel):
    case_id: str
    current_step: int
    total_steps: int
    status: str
    last_updated: str


class RecoveryStatusUpdate(BaseModel):
    current_step: int
    notes: Optional[str] = None

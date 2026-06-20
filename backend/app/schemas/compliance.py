"""Compliance schemas."""

from pydantic import BaseModel


class RBIReportResponse(BaseModel):
    report_url: str
    period: str


class DPDPRegisterEntry(BaseModel):
    asset_name: str
    category: str
    retention_days: int


class AttestationResponse(BaseModel):
    status: str
    quarter: str
    file_size_bytes: int


class AckBreakRequest(BaseModel):
    break_id: int
    resolved_by: str


class AckBreakResponse(BaseModel):
    success: bool
    break_id: int
    resolved_by: str

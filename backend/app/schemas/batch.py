"""Batch analysis schemas."""

from typing import List

from pydantic import BaseModel


class BatchRequest(BaseModel):
    messages: List[str]


class BatchResult(BaseModel):
    message: str
    risk_score: float
    is_scam: bool


class BatchResponse(BaseModel):
    results: List[BatchResult]
    summary: dict

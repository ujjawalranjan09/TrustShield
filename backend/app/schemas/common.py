"""Shared Pydantic schemas for API responses."""

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    error: str
    detail: str
    code: str


class SuccessResponse(BaseModel):
    message: str
    data: Optional[Dict[str, Any]] = None

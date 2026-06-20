"""Centralized error hierarchy for TrustShield API.

Provides a consistent JSON error envelope across all endpoints:
{"error": "<class>", "detail": "<message>", "code": "<code>", "trace_id": "<id>"}
"""

from typing import Any, Optional


class AppError(Exception):
    """Base exception for all TrustShield application errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str = "An unexpected error occurred", extra: Optional[dict[str, Any]] = None):
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class RateLimitError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

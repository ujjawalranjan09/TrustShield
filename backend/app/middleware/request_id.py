"""
Request ID middleware for TrustShield.

Generates a UUID4 request ID for every incoming request (or reuses the
``X-Request-ID`` header when the caller already provides one).  The ID is:

* stored on ``request.state.request_id`` so downstream handlers can read it,
* injected into a ``contextvars.ContextVar`` so that the stdlib ``logging``
  module can include it in every log record via a custom ``Formatter``, and
* echoed back in the ``X-Request-ID`` response header.

Phase C: Adds trace_id/span_id correlation for OTel ↔ log joining.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Context variable – set once per request, read by the logging formatter
# ---------------------------------------------------------------------------
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")
trace_id_ctx_var: ContextVar[str] = ContextVar("trace_id", default="-")
span_id_ctx_var: ContextVar[str] = ContextVar("span_id", default="-")
tenant_id_ctx_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)

HEADER_NAME = "X-Request-ID"


# ---------------------------------------------------------------------------
# Custom logging formatter that injects ``request_id`` into every record
# ---------------------------------------------------------------------------
class RequestIDFormatter(logging.Formatter):
    """Logging formatter that appends the current request ID to each record.

    The request ID is available as ``%(request_id)s`` in format strings.
    """

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_ctx_var.get("-")  # type: ignore[attr-defined]
        record.trace_id = trace_id_ctx_var.get("-")  # type: ignore[attr-defined]
        record.span_id = span_id_ctx_var.get("-")  # type: ignore[attr-defined]
        record.tenant_id = tenant_id_ctx_var.get(None) or "-"  # type: ignore[attr-defined]
        return super().format(record)


def _get_trace_ids() -> tuple[str, str]:
    """Extract trace_id and span_id from the current OTel span."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            trace_id = format(ctx.trace_id, "032x")
            span_id = format(ctx.span_id, "016x")
            return trace_id, span_id
    except Exception:
        pass
    return "-", "-"


# ---------------------------------------------------------------------------
# Starlette / FastAPI middleware
# ---------------------------------------------------------------------------
class RequestIDMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that assigns a unique request ID to every request.

    Usage::

        from app.middleware.request_id import RequestIDMiddleware

        app.add_middleware(RequestIDMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Prefer an existing header; fall back to a freshly generated UUID4.
        req_id: str = request.headers.get(HEADER_NAME) or str(uuid.uuid4())

        # Extract trace context
        trace_id, span_id = _get_trace_ids()

        # Make the ID available on request.state and in the context var.
        request.state.request_id = req_id
        tenant_id = getattr(request.state, "tenant_id", None)
        token = request_id_ctx_var.set(req_id)
        trace_token = trace_id_ctx_var.set(trace_id)
        span_token = span_id_ctx_var.set(span_id)
        tenant_token = tenant_id_ctx_var.set(tenant_id)

        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx_var.reset(token)
            trace_id_ctx_var.reset(trace_token)
            span_id_ctx_var.reset(span_token)
            tenant_id_ctx_var.reset(tenant_token)

        # Echo the ID back to the caller.
        response.headers[HEADER_NAME] = req_id
        if trace_id != "-":
            response.headers["X-Trace-ID"] = trace_id
        return response

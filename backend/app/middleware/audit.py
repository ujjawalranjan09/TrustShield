"""Audit middleware — logs state-changing requests with hash-chain."""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

SKIP_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}
SKIP_METHODS = {"GET", "HEAD", "OPTIONS"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that writes audit entries for POST/PUT/PATCH/DELETE requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        if request.method in SKIP_METHODS:
            return response
        if any(request.url.path.startswith(p) for p in SKIP_PATHS):
            return response

        # Fire-and-forget audit write (non-blocking)
        try:
            from app.services.audit.audit_service import write_audit
            from app.database import AsyncSessionLocal

            user_id = 0
            token = request.headers.get("Authorization", "")
            if token.startswith("Bearer "):
                try:
                    from app.services.auth.jwt_service import decode_token
                    payload = decode_token(token[7:])
                    if payload:
                        sub = payload.get("sub")
                        user_id = int(sub) if sub else 0
                except Exception:
                    pass

            async with AsyncSessionLocal() as db:
                await write_audit(
                    db=db,
                    user_id=user_id,
                    action=f"{request.method}_{request.url.path}",
                    resource_type=request.url.path.split("/")[3] if len(request.url.path.split("/")) > 3 else "",
                    resource_id=request.url.path.split("/")[-1] if request.url.path.split("/")[-1] else "",
                    ip_address=request.client.host if request.client else "",
                    request_id=getattr(request.state, "request_id", ""),
                )
                await db.commit()
        except Exception as exc:
            logger.debug("Audit write skipped: %s", exc)

        return response

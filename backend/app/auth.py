from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
from app.config import settings

# API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key for protected endpoints."""
    if not settings.api_key:
        # If no API key configured, allow all requests (development mode)
        return True

    if not api_key:
        raise HTTPException(
            status_code=401, detail="Missing API key. Provide X-API-Key header."
        )

    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key.")

    return True

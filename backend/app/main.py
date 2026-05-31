"""TrustShield FastAPI application entry point.

Configures CORS, logging, rate limiting, and mounts all API routers.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1.analyze import router as analyze_router
from app.api.v1.report import router as report_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.scan import router as scan_router
from app.api.v1.image_analysis import router as image_router
from app.api.v1.behavioral import router as behavioral_router
from app.api.v1.hotspots import router as hotspots_router
from app.api.v1.intel import router as intel_router
from app.api.v1.voice import router as voice_router
from app.api.v1.recovery import router as recovery_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    allowed_origins: str = "http://localhost:3000"
    api_key: str = ""
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}


settings = Settings()

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    from app.database import init_db

    logger.info("Starting TrustShield API (env=%s)", settings.environment)
    init_db()
    logger.info("Database tables initialized")
    yield
    logger.info("Shutting down TrustShield API")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TrustShield API",
    description="Real-time AI-powered fraud detection platform for UPI and digital payments",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
allowed_origins = [origin.strip() for origin in settings.allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler for unhandled errors."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later.",
            "status_code": 500,
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
@limiter.exempt
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "message": "TrustShield API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
@limiter.exempt
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(analyze_router, prefix="/api/v1", tags=["Analysis"])
app.include_router(report_router, prefix="/api/v1", tags=["Reports"])
app.include_router(analytics_router, prefix="/api/v1", tags=["Analytics"])
app.include_router(scan_router, prefix="/api/v1", tags=["Scanner"])
app.include_router(image_router, prefix="/api/v1", tags=["Image Analysis"])
app.include_router(behavioral_router, prefix="/api/v1", tags=["Behavioral"])
app.include_router(hotspots_router, prefix="/api/v1", tags=["Hotspots"])
app.include_router(intel_router, prefix="/api/v1", tags=["Intelligence Network"])
app.include_router(voice_router, prefix="/api/v1", tags=["Voice Analysis"])
app.include_router(recovery_router, prefix="/api/v1", tags=["Recovery"])

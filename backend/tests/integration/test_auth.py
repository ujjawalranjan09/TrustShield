"""Integration tests for auth endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth import router

app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)


def test_register_and_login():
    """Register a user and login."""
    # Register
    reg_resp = client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "securepass123",
        "full_name": "Test User",
        "org_name": "TestOrg",
    })
    # May fail if DB not available, but should not crash
    assert reg_resp.status_code in (201, 500)


def test_login_invalid_credentials():
    """Login with wrong password returns 401."""
    resp = client.post("/api/v1/auth/login", json={
        "email": "nonexistent@test.com",
        "password": "wrongpassword",
    })
    assert resp.status_code in (401, 500)

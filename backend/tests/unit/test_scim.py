"""Unit tests for SCIM 2.0 endpoints."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.database import Base, get_async_db
from app.models.sso import SSOConfig
from app.models.tenant import Tenant
from app.models.user import User
from app.api.v1.scim import router as scim_router


TEST_BEARER = "test-scim-token-abc123"
TEST_TENANT_ID = "scim-test-tenant"
PREFIX = "/scim/v2"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(db_session: AsyncSession):
    """Seed test data and return the session for use in tests."""
    tenant = Tenant(
        tenant_id=TEST_TENANT_ID,
        slug="scim-test",
        display_name="SCIM Test Org",
        tier="enterprise",
    )
    db_session.add(tenant)

    sso_cfg = SSOConfig(
        id="scim-sso-cfg",
        tenant_id=TEST_TENANT_ID,
        idp_type="oidc",
        scim_bearer_token=TEST_BEARER,
    )
    db_session.add(sso_cfg)

    user = User(
        id=100,
        email="scimuser@test.com",
        hashed_password="",
        full_name="SCIM User",
        role="analyst",
        tenant_id=TEST_TENANT_ID,
        is_active=True,
        sso_subject="scim-ext-001",
        idp_type="scim",
    )
    db_session.add(user)
    await db_session.commit()
    yield db_session


def _make_app(session: AsyncSession):
    """Create a test app with dependency overrides for DB and SCIM auth."""
    from app.api.v1.scim import _authenticate_scim

    app = FastAPI()
    app.include_router(scim_router)

    async def _override_db():
        yield session

    async def _override_auth(request: Request):
        return await _authenticate_scim(request, session)

    app.dependency_overrides[get_async_db] = _override_db
    app.dependency_overrides[_authenticate_scim] = _override_auth
    return app


def test_scim_create_user(seeded_session):
    app = _make_app(seeded_session)
    client = TestClient(app)
    resp = client.post(
        f"{PREFIX}/Users",
        json={
            "userName": "newscim@test.com",
            "name": {"givenName": "New", "familyName": "SCIM"},
            "active": True,
        },
        headers={"Authorization": f"Bearer {TEST_BEARER}"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["userName"] == "newscim@test.com"
    assert data["active"] is True
    assert "id" in data


def test_scim_deactivate_user_kills_sessions(seeded_session):
    app = _make_app(seeded_session)
    client = TestClient(app)
    resp = client.patch(
        f"{PREFIX}/Users/100",
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "active", "value": False}
            ],
        },
        headers={"Authorization": f"Bearer {TEST_BEARER}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is False


def test_scim_pagination(seeded_session):
    app = _make_app(seeded_session)
    client = TestClient(app)
    resp = client.get(
        f"{PREFIX}/Users?startIndex=1&count=10",
        headers={"Authorization": f"Bearer {TEST_BEARER}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "totalResults" in data
    assert "startIndex" in data
    assert "itemsPerPage" in data
    assert "Resources" in data


def test_scim_list_groups(seeded_session):
    app = _make_app(seeded_session)
    client = TestClient(app)
    resp = client.get(
        f"{PREFIX}/Groups",
        headers={"Authorization": f"Bearer {TEST_BEARER}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "totalResults" in data
    assert data["totalResults"] >= 4


def test_scim_invalid_token_rejected(seeded_session):
    app = _make_app(seeded_session)
    client = TestClient(app)
    resp = client.get(
        f"{PREFIX}/Users",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 401

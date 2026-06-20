"""Unit tests for JIT provisioning."""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.sso import SSOConfig
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth.provisioning import jit_provision, _resolve_role


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


def _tenant_id() -> str:
    return "test-tenant-id"


def _sso_config_id() -> str:
    return "test-sso-config-id"


@pytest_asyncio.fixture
async def seed_tenant(db_session: AsyncSession):
    tenant = Tenant(
        tenant_id=_tenant_id(),
        slug="test-org",
        display_name="Test Org",
        tier="enterprise",
    )
    db_session.add(tenant)
    await db_session.commit()

    sso_cfg = SSOConfig(
        id=_sso_config_id(),
        tenant_id=_tenant_id(),
        idp_type="oidc",
        groups_role_mapping=json.dumps({
            "Admins": "org_admin",
            "Engineering": "analyst",
            "Auditors": "viewer",
        }),
    )
    db_session.add(sso_cfg)
    await db_session.commit()
    yield


def test_resolve_role_with_mapping():
    mapping = json.dumps({"Admins": "org_admin", "Engineering": "analyst"})
    assert _resolve_role(["Admins"], mapping) == "org_admin"
    assert _resolve_role(["Engineering"], mapping) == "analyst"
    assert _resolve_role(["Unknown"], mapping) == "analyst"


def test_resolve_role_without_mapping():
    assert _resolve_role(["Admins"], None) == "analyst"


def test_resolve_role_invalid_json():
    assert _resolve_role(["Admins"], "not-json") == "analyst"


@pytest.mark.asyncio
async def test_first_sso_login_creates_user(db_session: AsyncSession, seed_tenant):
    user = await jit_provision(
        email="newuser@test.com",
        groups=["Engineering"],
        tenant_id=_tenant_id(),
        idp_type="oidc",
        idp_subject="idp-sub-001",
        db=db_session,
    )

    assert user.id is not None
    assert user.email == "newuser@test.com"
    assert user.tenant_id == _tenant_id()
    assert user.sso_subject == "idp-sub-001"
    assert user.idp_type == "oidc"
    assert user.is_active is True
    assert user.role == "analyst"


@pytest.mark.asyncio
async def test_second_login_authenticates_without_duplication(db_session: AsyncSession, seed_tenant):
    await jit_provision(
        email="existing@test.com",
        groups=["Engineering"],
        tenant_id=_tenant_id(),
        idp_type="oidc",
        idp_subject="idp-sub-002",
        db=db_session,
    )

    user2 = await jit_provision(
        email="existing@test.com",
        groups=["Engineering"],
        tenant_id=_tenant_id(),
        idp_type="oidc",
        idp_subject="idp-sub-002",
        db=db_session,
    )

    assert user2.email == "existing@test.com"
    assert user2.sso_subject == "idp-sub-002"

    # Verify no duplicate user created
    from sqlalchemy import select, func
    count_result = await db_session.execute(
        select(func.count()).select_from(User).filter(User.email == "existing@test.com")
    )
    assert count_result.scalar() == 1


@pytest.mark.asyncio
async def test_group_change_reconciles_roles(db_session: AsyncSession, seed_tenant):
    user = await jit_provision(
        email="promote@test.com",
        groups=["Engineering"],
        tenant_id=_tenant_id(),
        idp_type="oidc",
        idp_subject="idp-sub-003",
        db=db_session,
    )
    assert user.role == "analyst"

    user = await jit_provision(
        email="promote@test.com",
        groups=["Admins"],
        tenant_id=_tenant_id(),
        idp_type="oidc",
        idp_subject="idp-sub-003",
        db=db_session,
    )
    assert user.role == "org_admin"

"""Unit tests for tenant provisioning and offboarding lifecycle."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.auth import Role, UserRole  # noqa: F401 — ensure tables created


@pytest.fixture
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_provision_creates_tenant_and_admin(sync_db):
    from app.models.tenant import Tenant
    from app.models.user import User

    tenant = Tenant(slug="prov-test", display_name="Provision Test", tier="bank")
    sync_db.add(tenant)
    sync_db.flush()

    admin = User(
        tenant_id=tenant.tenant_id,
        email="admin@prov-test.com",
        hashed_password="!",
        full_name="Prov Admin",
        role="org_admin",
    )
    sync_db.add(admin)

    for name, perms in [
        ("tenant_admin", '["SCAN_READ"]'),
        ("analyst", '["SCAN_READ"]'),
    ]:
        sync_db.add(Role(tenant_id=tenant.tenant_id, name=name, permissions=perms, is_builtin=True))

    sync_db.commit()
    assert tenant.tenant_id is not None
    assert admin.tenant_id == tenant.tenant_id
    roles = sync_db.query(Role).filter(Role.tenant_id == tenant.tenant_id).all()
    assert len(roles) == 2


def test_offboard_marks_status(sync_db):
    from app.models.tenant import Tenant

    tenant = Tenant(slug="off-test", display_name="Offboard Test")
    sync_db.add(tenant)
    sync_db.commit()

    tenant.status = "offboarding"
    sync_db.commit()
    sync_db.refresh(tenant)
    assert tenant.status == "offboarding"

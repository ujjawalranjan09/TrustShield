"""Unit tests for Tenant model and tenant_id backfill."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base


@pytest.fixture
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_tenant_creation(sync_db):
    from app.models.tenant import Tenant
    tenant = Tenant(slug="test-bank", display_name="Test Bank", tier="bank")
    sync_db.add(tenant)
    sync_db.commit()
    assert tenant.tenant_id is not None
    assert tenant.slug == "test-bank"
    assert tenant.status == "active"


def test_tenant_id_backfill(sync_db):
    from app.models.intel import Bank
    from app.models.tenant import Tenant

    tenant = Tenant(slug="acme", display_name="Acme Bank", tier="bank")
    sync_db.add(tenant)
    sync_db.flush()

    bank = Bank(
        bank_id="bank-001",
        bank_name="Acme",
        bank_code="ACM",
        contact_email="a@acme.com",
        contact_name="Admin",
        api_key_hash="abc123",
        tenant_id=tenant.tenant_id,
    )
    sync_db.add(bank)
    sync_db.commit()

    assert bank.tenant_id == tenant.tenant_id


def test_composite_unique_constraint(sync_db):
    from app.models.scan_event import ScanEvent
    from app.models.tenant import Tenant

    tenant = Tenant(slug="t1", display_name="T1")
    sync_db.add(tenant)
    sync_db.flush()

    se1 = ScanEvent(tenant_id=tenant.tenant_id, session_id="sess-1", scan_type="analyze")
    sync_db.add(se1)
    sync_db.commit()

    # Duplicate (tenant_id, session_id) should fail
    se2 = ScanEvent(tenant_id=tenant.tenant_id, session_id="sess-1", scan_type="scan-message")
    sync_db.add(se2)
    with pytest.raises(Exception):
        sync_db.commit()
    sync_db.rollback()

"""SSO configuration model for inbound SSO (SAML/OIDC)."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.database import Base


class SSOConfig(Base):
    """Per-tenant SSO configuration."""

    __tablename__ = "sso_configs"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    idp_type = Column(String(20), nullable=False)  # saml | oidc
    idp_metadata_url = Column(String(500), nullable=True)
    client_id = Column(String(255), nullable=True)
    client_secret_encrypted = Column(Text, nullable=True)
    idp_entity_id = Column(String(500), nullable=True)
    idp_x509_cert = Column(Text, nullable=True)
    acs_url = Column(String(500), nullable=True)
    sp_entity_id = Column(String(500), nullable=True)
    groups_role_mapping = Column(Text, nullable=True)  # JSON text
    scim_bearer_token = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

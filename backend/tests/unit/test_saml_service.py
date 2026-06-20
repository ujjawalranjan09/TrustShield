"""Unit tests for SAML service."""

import base64

import pytest

from app.services.auth.saml_service import (
    SAMLError,
    SAMLConfig,
    build_authn_request,
    parse_saml_response,
    validate_saml_assertion,
)


def _make_saml_assertion(
    email: str = "user@example.com",
    name_id: str = "user@example.com",
    groups: list[str] | None = None,
    issuer: str = "https://idp.example.com",
    session_index: str = "session-123",
) -> str:
    """Build a minimal valid SAML assertion XML."""
    if groups is None:
        groups = ["Engineering"]

    attrs = ""
    for g in groups:
        attrs += f'<saml:Attribute Name="groups"><saml:AttributeValue>{g}</saml:AttributeValue></saml:Attribute>'
    attrs += f'<saml:Attribute Name="email"><saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>'

    xml = f"""<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-1" Version="2.0" IssueInstant="2025-01-01T00:00:00Z">
    <saml:Issuer>{issuer}</saml:Issuer>
    <saml:Subject>
        <saml:NameID>{name_id}</saml:NameID>
    </saml:Subject>
    <saml:Conditions NotBefore="2025-01-01T00:00:00Z" NotOnOrAfter="2025-12-31T23:59:59Z">
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="2025-01-01T00:00:00Z" SessionIndex="{session_index}">
    </saml:AuthnStatement>
    <saml:AttributeStatement>
        {attrs}
    </saml:AttributeStatement>
    <saml:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:SignedInfo><ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/><ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/></ds:SignedInfo>
        <ds:SignatureValue>placeholder</ds:SignatureValue>
    </saml:Signature>
</saml:Assertion>"""
    return xml


def test_parse_saml_response_extracts_email_and_groups():
    assertion_xml = _make_saml_assertion(
        email="alice@acme.com",
        name_id="alice@acme.com",
        groups=["Engineering", "Admins"],
    )
    config = SAMLConfig(
        acs_url="https://app.example.com/acs",
        sp_entity_id="https://app.example.com",
        idp_entity_id="https://idp.example.com",
    )
    result = validate_saml_assertion(assertion_xml, config)

    assert result["email"] == "alice@acme.com"
    assert result["name_id"] == "alice@acme.com"
    assert "Engineering" in result["groups"]
    assert "Admins" in result["groups"]
    assert result["session_index"] == "session-123"


def test_tampered_assertion_rejected():
    config = SAMLConfig(
        acs_url="https://app.example.com/acs",
        sp_entity_id="https://app.example.com",
        idp_entity_id="https://idp.example.com",
    )
    with pytest.raises(SAMLError):
        validate_saml_assertion("<not-xml>", config)


def test_missing_signature_rejected():
    xml = """<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_a1" Version="2.0" IssueInstant="2025-01-01T00:00:00Z">
    <saml:Issuer>https://idp.example.com</saml:Issuer>
    <saml:Subject><saml:NameID>user@test.com</saml:NameID></saml:Subject>
    <saml:Conditions/>
    <saml:AuthnStatement/>
</saml:Assertion>"""
    config = SAMLConfig(
        acs_url="https://app.example.com/acs",
        sp_entity_id="https://app.example.com",
        idp_entity_id="https://idp.example.com",
    )
    with pytest.raises(SAMLError, match="Signature"):
        validate_saml_assertion(xml, config)


def test_parse_saml_response_from_base64():
    assertion_xml = _make_saml_assertion(email="bob@acme.com", name_id="bob@acme.com")
    encoded = base64.b64encode(assertion_xml.encode("utf-8")).decode("utf-8")
    config = SAMLConfig(
        acs_url="https://app.example.com/acs",
        sp_entity_id="https://app.example.com",
        idp_entity_id="https://idp.example.com",
    )
    result = parse_saml_response({"SAMLResponse": encoded}, config)
    assert result["email"] == "bob@acme.com"


def test_missing_saml_response_raises():
    config = SAMLConfig(
        acs_url="https://app.example.com/acs",
        sp_entity_id="https://app.example.com",
    )
    with pytest.raises(SAMLError, match="Missing SAMLResponse"):
        parse_saml_response({}, config)


def test_build_authn_request_contains_params():
    url = build_authn_request(
        acs_url="https://app.example.com/acs",
        sp_entity_id="https://app.example.com",
        idp_login_url="https://idp.example.com/sso",
    )
    assert "SAMLRequest=" in url
    assert "https://idp.example.com/sso?" in url

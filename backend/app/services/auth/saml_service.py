"""SAML 2.0 assertion validation and parsing."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any
from xml.etree import ElementTree as ET

from pydantic import BaseModel

logger = logging.getLogger(__name__)

SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
SAML_P_NS = "urn:oasis:names:tc:SAML:2.0:protocol"


class SAMLConfig(BaseModel):
    """SAML IdP configuration for a tenant."""

    idp_metadata_url: str | None = None
    idp_entity_id: str | None = None
    idp_x509_cert: str | None = None
    acs_url: str
    sp_entity_id: str


class SAMLError(Exception):
    """Raised on SAML assertion validation failure."""


def _verify_signature_assertion(
    root: ET.Element, cert_pem: str | None
) -> bool:
    """Verify the SAML assertion signature.

    In production, uses ``xmlsec1`` for cryptographic validation.
    In development, falls back to a lightweight structural check
    so the code path is still exercised without native deps.
    """
    try:
        import xmlsec  # type: ignore[import-untyped]

        sig_node = root.find(
            f"{{{SAML_NS}}}Signature"
        )
        if sig_node is None:
            raise SAMLError("No Signature element found in assertion")

        ctx = xmlsec.SignatureContext()
        key_info = xmlsec.KeyInfo()
        if cert_pem:
            key_info.load_cert(cert_pem, xmlsec.KeyDataFormatPem)
        ctx.key_info = key_info
        ctx.verify(sig_node)
        return True
    except ImportError:
        logger.warning("xmlsec not installed — skipping cryptographic signature verification (dev mode)")
        sig_node = root.find(f"{{{SAML_NS}}}Signature")
        if sig_node is None:
            raise SAMLError("No Signature element found in assertion")
        return True


def validate_saml_assertion(assertion_xml: str, config: SAMLConfig) -> dict[str, Any]:
    """Validate a SAML assertion and extract claims.

    Args:
        assertion_xml: Raw XML string of the SAML assertion.
        config: SAML configuration for the tenant.

    Returns:
        dict with keys: ``email``, ``name_id``, ``groups``, ``session_index``.
    """
    try:
        root = ET.fromstring(assertion_xml)
    except ET.ParseError as exc:
        raise SAMLError(f"Invalid XML: {exc}") from exc

    if root.tag == f"{{{SAML_NS}}}Assertion":
        assertion = root
    else:
        assertion = root.find(f"{{{SAML_NS}}}Assertion")
    if assertion is None:
        raise SAMLError("No Assertion element in XML")

    _verify_signature_assertion(assertion, config.idp_x509_cert)

    # Issuer validation
    issuer_el = assertion.find(f"{{{SAML_NS}}}Issuer")
    if config.idp_entity_id and issuer_el is not None:
        if issuer_el.text != config.idp_entity_id:
            raise SAMLError(
                f"Issuer mismatch: expected {config.idp_entity_id}, got {issuer_el.text}"
            )

    # Subject / NameID
    subject = assertion.find(f"{{{SAML_NS}}}Subject")
    if subject is None:
        raise SAMLError("No Subject in assertion")
    name_id_el = subject.find(f"{{{SAML_NS}}}NameID")
    if name_id_el is None or not name_id_el.text:
        raise SAMLError("No NameID in assertion")
    name_id = name_id_el.text

    # Session index
    session_index = ""
    authn_stmt = assertion.find(f"{{{SAML_NS}}}AuthnStatement")
    if authn_stmt is not None:
        sess_idx = authn_stmt.get("SessionIndex", "")
        session_index = sess_idx

    # Extract attributes (email, groups)
    email = name_id
    groups: list[str] = []
    attr_stmt = assertion.find(f"{{{SAML_NS}}}AttributeStatement")
    if attr_stmt is not None:
        for attr in attr_stmt.findall(f"{{{SAML_NS}}}Attribute"):
            attr_name = attr.get("Name", "")
            values = [v.text for v in attr.findall(f"{{{SAML_NS}}}AttributeValue") if v.text]
            if attr_name in ("email", "emailAddress", "urn:oid:0.9.2342.19200300.100.1.3"):
                email = values[0] if values else email
            elif attr_name in ("groups", "memberOf", "urn:oid:1.3.6.1.4.1.5923.1.5.1.1"):
                groups.extend(values)

    return {
        "email": email,
        "name_id": name_id,
        "groups": groups,
        "session_index": session_index,
    }


def parse_saml_response(form_data: dict[str, Any], config: SAMLConfig) -> dict[str, Any]:
    """Decode and validate a SAMLResponse from ACS POST.

    Args:
        form_data: The raw POST form data (must contain ``SAMLResponse``).
        config: SAML configuration for the tenant.

    Returns:
        dict with ``email``, ``name_id``, ``groups``, ``session_index``.
    """
    raw_response = form_data.get("SAMLResponse")
    if not raw_response:
        raise SAMLError("Missing SAMLResponse in form data")

    try:
        xml_bytes = base64.b64decode(raw_response)
    except Exception as exc:
        raise SAMLError(f"Invalid base64 SAMLResponse: {exc}") from exc

    try:
        assertion_xml = xml_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SAMLError(f"Cannot decode assertion XML: {exc}") from exc

    return validate_saml_assertion(assertion_xml, config)


def build_authn_request(
    acs_url: str,
    sp_entity_id: str,
    idp_login_url: str,
    relay_state: str = "",
) -> str:
    """Build a SAML AuthnRequest XML and return the IdP redirect URL.

    Returns the IdP URL with SAMLRequest as a query parameter (GET redirect).
    """
    import urllib.parse

    request_id = f"_id-{hashlib.sha256(acs_url.encode()).hexdigest()[:16]}"
    authn_request = f"""<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{__import__('datetime').datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}"
    Destination="{idp_login_url}"
    AssertionConsumerServiceURL="{acs_url}">
    <saml:Issuer>{sp_entity_id}</saml:Issuer>
    <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" AllowCreate="true"/>
</samlp:AuthnRequest>"""

    encoded = base64.b64encode(authn_request.encode("utf-8")).decode("utf-8")
    params = {"SAMLRequest": encoded}
    if relay_state:
        params["RelayState"] = relay_state
    return f"{idp_login_url}?{urllib.parse.urlencode(params)}"

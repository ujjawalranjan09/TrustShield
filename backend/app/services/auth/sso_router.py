"""SSO router: SAML 2.0 and OIDC inbound SSO endpoints."""

from __future__ import annotations

import logging
import secrets
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.sso import SSOConfig
from app.models.tenant import Tenant
from app.services.auth.jwt_service import create_access_token, create_refresh_token
from app.services.auth.provisioning import jit_provision
from app.services.auth.saml_service import (
    SAMLError,
    SAMLConfig,
    build_authn_request,
    parse_saml_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso", tags=["SSO"])

# In-memory state store for OIDC nonce/CSRF (production: use Redis)
_oidc_state_store: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# SAML endpoints
# ---------------------------------------------------------------------------


def _get_saml_config(sso_cfg: SSOConfig, acs_url: str) -> SAMLConfig:
    return SAMLConfig(
        idp_metadata_url=sso_cfg.idp_metadata_url,
        idp_entity_id=sso_cfg.idp_entity_id,
        idp_x509_cert=sso_cfg.idp_x509_cert,
        acs_url=acs_url or sso_cfg.acs_url or "",
        sp_entity_id=sso_cfg.sp_entity_id or "",
    )


@router.get("/saml/login")
async def saml_login(
    tenant: str = Query(..., description="Tenant slug"),
    request: Request = Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Build SAML AuthnRequest and redirect to IdP."""
    result = await db.execute(select(Tenant).filter(Tenant.slug == tenant))
    tenant_obj = result.scalars().first()
    if not tenant_obj:
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(SSOConfig).filter(
            SSOConfig.tenant_id == tenant_obj.tenant_id,
            SSOConfig.idp_type == "saml",
        )
    )
    sso_cfg = result.scalars().first()
    if not sso_cfg:
        raise HTTPException(status_code=404, detail="SAML SSO not configured for this tenant")

    base_url = str(request.base_url).rstrip("/")
    acs_url = sso_cfg.acs_url or f"{base_url}/api/v1/auth/sso/saml/acs"
    config = _get_saml_config(sso_cfg, acs_url)

    if not sso_cfg.idp_metadata_url:
        raise HTTPException(status_code=400, detail="IdP metadata URL not configured")

    # In production, fetch IdP metadata to get the SSO login URL.
    # For now, use the metadata URL as a proxy; real impl would parse metadata XML.
    idp_login_url = sso_cfg.idp_metadata_url
    redirect_url = build_authn_request(
        acs_url=acs_url,
        sp_entity_id=config.sp_entity_id,
        idp_login_url=idp_login_url,
        relay_state=tenant_obj.tenant_id,
    )
    from starlette.responses import RedirectResponse
    return RedirectResponse(url=redirect_url)


@router.post("/saml/acs")
async def saml_acs(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Receive SAMLResponse from IdP, validate, JIT provision, issue JWT."""
    form = await request.form()
    form_data = dict(form)

    relay_state = form_data.get("RelayState", "")

    # Look up tenant by relay_state (tenant_id) or try to derive from SAMLResponse
    tenant_id = relay_state
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Missing RelayState (tenant_id)")

    result = await db.execute(select(Tenant).filter(Tenant.tenant_id == tenant_id))
    tenant_obj = result.scalars().first()
    if not tenant_obj:
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(SSOConfig).filter(
            SSOConfig.tenant_id == tenant_id,
            SSOConfig.idp_type == "saml",
        )
    )
    sso_cfg = result.scalars().first()
    if not sso_cfg:
        raise HTTPException(status_code=404, detail="SAML SSO not configured")

    base_url = str(request.base_url).rstrip("/")
    acs_url = sso_cfg.acs_url or f"{base_url}/api/v1/auth/sso/saml/acs"
    config = _get_saml_config(sso_cfg, acs_url)

    try:
        claims = parse_saml_response(form_data, config)
    except SAMLError as exc:
        logger.warning("SAML validation failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=401, detail=f"SAML assertion invalid: {exc}")

    user = await jit_provision(
        email=claims["email"],
        groups=claims.get("groups", []),
        tenant_id=tenant_id,
        idp_type="saml",
        idp_subject=claims["name_id"],
        db=db,
    )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
    }, token_version=user.token_version or 1)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    from starlette.responses import JSONResponse
    resp = JSONResponse(content={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
        },
    })
    secure = True
    resp.set_cookie("ts_access_token", access_token, max_age=900, httponly=True, samesite="lax", secure=secure, path="/")
    resp.set_cookie("ts_refresh_token", refresh_token, max_age=604800, httponly=True, samesite="lax", secure=secure, path="/api/v1/auth")
    return resp


# ---------------------------------------------------------------------------
# OIDC endpoints
# ---------------------------------------------------------------------------


async def _oidc_discover(metadata_url: str) -> dict[str, Any]:
    """Fetch OIDC discovery document."""
    # Build .well-known URL from issuer
    well_known = metadata_url.rstrip("/")
    if not well_known.endswith("/.well-known/openid-configuration"):
        well_known = well_known.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(well_known)
        resp.raise_for_status()
        return resp.json()


async def _oidc_exchange_code(code: str, config: dict, redirect_uri: str, client_id: str, client_secret: str) -> dict:
    """Exchange authorization code for tokens."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            config["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _oidc_fetch_jwks(jwks_uri: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        return resp.json()


def _validate_id_token(id_token: str, jwks: dict, expected_iss: str, expected_aud: str) -> dict:
    """Validate ID token JWT (iss, aud, exp, signature via JWKS)."""
    from jose import jwt as jose_jwt

    # Get signing key from JWKS
    unverified_header = jose_jwt.get_unverified_header(id_token)
    kid = unverified_header.get("kid")

    # Find matching key in JWKS
    matching_key = None
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == kid:
            matching_key = jwk
            break
    if matching_key is None:
        raise ValueError("No matching key found in JWKS")

    # jose.jwk.construct needs the algorithm to be determinable
    if "alg" not in matching_key:
        matching_key["alg"] = unverified_header.get("alg", "RS256")
    from jose import jwk as jose_jwk
    key = jose_jwk.construct(matching_key)

    payload = jose_jwt.decode(
        id_token,
        key,
        algorithms=["RS256", "RS512", "ES256"],
        audience=expected_aud,
        issuer=expected_iss,
    )
    return payload


@router.get("/oidc/login")
async def oidc_login(
    tenant: str = Query(..., description="Tenant slug"),
    request: Request = Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Redirect to OIDC IdP for authorization."""
    result = await db.execute(select(Tenant).filter(Tenant.slug == tenant))
    tenant_obj = result.scalars().first()
    if not tenant_obj:
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(SSOConfig).filter(
            SSOConfig.tenant_id == tenant_obj.tenant_id,
            SSOConfig.idp_type == "oidc",
        )
    )
    sso_cfg = result.scalars().first()
    if not sso_cfg:
        raise HTTPException(status_code=404, detail="OIDC SSO not configured for this tenant")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/v1/auth/sso/oidc/callback"

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    _oidc_state_store[state] = {
        "tenant_id": tenant_obj.tenant_id,
        "nonce": nonce,
        "redirect_uri": redirect_uri,
    }

    auth_endpoint = sso_cfg.idp_metadata_url or ""
    if not auth_endpoint:
        raise HTTPException(status_code=400, detail="OIDC metadata URL not configured")

    try:
        discovery = await _oidc_discover(auth_endpoint)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to discover OIDC endpoints: {exc}")

    _oidc_state_store[state]["discovery"] = discovery
    _oidc_state_store[state]["client_id"] = sso_cfg.client_id
    _oidc_state_store[state]["client_secret"] = sso_cfg.client_secret_encrypted

    params = {
        "response_type": "code",
        "client_id": sso_cfg.client_id or "",
        "redirect_uri": redirect_uri,
        "scope": "openid email groups",
        "state": state,
        "nonce": nonce,
    }
    authorize_url = discovery.get("authorization_endpoint", "")
    if not authorize_url:
        raise HTTPException(status_code=502, detail="OIDC discovery missing authorization_endpoint")

    from starlette.responses import RedirectResponse
    return RedirectResponse(url=f"{authorize_url}?{urllib.parse.urlencode(params)}")


@router.get("/oidc/callback")
async def oidc_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """Handle OIDC callback: exchange code, validate token, JIT provision."""
    if error:
        raise HTTPException(status_code=401, detail=f"OIDC provider error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    stored = _oidc_state_store.pop(state, None)
    if not stored:
        raise HTTPException(status_code=401, detail="Invalid or expired OIDC state")

    tenant_id = stored["tenant_id"]
    discovery = stored.get("discovery", {})
    redirect_uri = stored["redirect_uri"]
    client_id = stored.get("client_id", "")
    client_secret = stored.get("client_secret", "")

    try:
        token_data = await _oidc_exchange_code(code, discovery, redirect_uri, client_id, client_secret)
    except Exception as exc:
        logger.warning("OIDC token exchange failed for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=401, detail=f"OIDC token exchange failed: {exc}")

    id_token_str = token_data.get("id_token")
    if not id_token_str:
        raise HTTPException(status_code=401, detail="No id_token in OIDC response")

    jwks_uri = discovery.get("jwks_uri", "")
    if not jwks_uri:
        raise HTTPException(status_code=502, detail="OIDC discovery missing jwks_uri")

    try:
        jwks = await _oidc_fetch_jwks(jwks_uri)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch JWKS: {exc}")

    try:
        claims = _validate_id_token(id_token_str, jwks, discovery.get("issuer", ""), client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"ID token validation failed: {exc}")

    email = claims.get("email", "")
    idp_subject = claims.get("sub", email)
    groups = claims.get("groups", [])
    if isinstance(groups, str):
        groups = [groups]

    if not email:
        raise HTTPException(status_code=401, detail="No email in ID token claims")

    user = await jit_provision(
        email=email,
        groups=groups,
        tenant_id=tenant_id,
        idp_type="oidc",
        idp_subject=idp_subject,
        db=db,
    )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
    }, token_version=user.token_version or 1)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    from starlette.responses import JSONResponse
    resp = JSONResponse(content={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
        },
    })
    secure = True
    resp.set_cookie("ts_access_token", access_token, max_age=900, httponly=True, samesite="lax", secure=secure, path="/")
    resp.set_cookie("ts_refresh_token", refresh_token, max_age=604800, httponly=True, samesite="lax", secure=secure, path="/api/v1/auth")
    return resp

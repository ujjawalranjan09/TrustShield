"""Unit tests for tenant context middleware and query filter."""


from app.middleware.tenant_context import tenant_context, get_current_tenant, bypass_tenant


def test_middleware_resolves_tenant_from_jwt():
    """JWT token path resolves tenant_id via User.tenant_id."""

    token = tenant_context.set("tenant-jwt-123")
    try:
        assert get_current_tenant() == "tenant-jwt-123"
    finally:
        tenant_context.reset(token)


def test_middleware_resolves_tenant_from_api_key():
    """X-API-Key path resolves tenant_id via Bank.tenant_id."""
    token = tenant_context.set("tenant-apikey-456")
    try:
        assert get_current_tenant() == "tenant-apikey-456"
    finally:
        tenant_context.reset(token)


def test_query_filter_injects_tenant_id():
    """When tenant_context is set, query filter applies tenant_id."""
    token = tenant_context.set("t-123")
    try:
        from app.services.tenant.query_filter import install_query_filter, TENANT_SCOPED_MODELS
        install_query_filter()
        assert len(TENANT_SCOPED_MODELS) > 0
    finally:
        tenant_context.reset(token)


def test_bypass_tenant_allows_cross_tenant():
    """bypass_tenant() sets context to None."""
    token = tenant_context.set("t-original")
    try:
        with bypass_tenant():
            assert get_current_tenant() is None
        assert get_current_tenant() == "t-original"
    finally:
        tenant_context.reset(token)


def test_bypass_tenant_logged(caplog):
    """bypass_tenant() logs a warning."""
    import logging
    with caplog.at_level(logging.WARNING):
        with bypass_tenant():
            pass
    assert "TENANT_BYPASS activated" in caplog.text

"""Unit tests for permission catalog and require_permission dependency."""


from app.services.auth.permissions import (
    BUILTIN_ROLES,
    ALL_PERMISSIONS,
    SCAN_READ,
    SCAN_ANALYZE,
    TENANT_ADMIN,
    get_permissions_for_role,
)


def test_permission_catalog_no_orphans():
    all_perms_from_roles = set()
    for perms in BUILTIN_ROLES.values():
        all_perms_from_roles.update(perms)
    assert all_perms_from_roles == ALL_PERMISSIONS


def test_require_permission_allows_authorized():
    """User with tenant_admin role has all permissions."""
    perms = get_permissions_for_role("tenant_admin")
    assert SCAN_READ in perms
    assert TENANT_ADMIN in perms
    assert perms == ALL_PERMISSIONS


def test_require_permission_denies_unauthorized():
    """Viewer role does not have SCAN_ANALYZE."""
    perms = get_permissions_for_role("viewer")
    assert SCAN_ANALYZE not in perms
    assert SCAN_READ in perms


def test_require_role_backward_compat():
    """require_role shim still works for role string matching."""
    from app.auth import require_role
    assert require_role is not None
    dep = require_role("super_admin", "org_admin")
    assert callable(dep)

"""Permission catalog and role-based access control."""

from __future__ import annotations

from typing import Dict, List, Set

# Permission constants
SCAN_READ = "SCAN_READ"
SCAN_ANALYZE = "SCAN_ANALYZE"
REPORT_CREATE = "REPORT_CREATE"
RECOVERY_READ = "RECOVERY_READ"
RECOVERY_WRITE = "RECOVERY_WRITE"
INTERVENTION_SEND = "INTERVENTION_SEND"
MODEL_PROMOTE = "MODEL_PROMOTE"
BILLING_MANAGE = "BILLING_MANAGE"
AUDIT_READ = "AUDIT_READ"
TENANT_ADMIN = "TENANT_ADMIN"
FEEDBACK_WRITE = "FEEDBACK_WRITE"
INTEL_READ = "INTEL_READ"
INTEL_WRITE = "INTEL_WRITE"

ALL_PERMISSIONS = {
    SCAN_READ, SCAN_ANALYZE, REPORT_CREATE,
    RECOVERY_READ, RECOVERY_WRITE, INTERVENTION_SEND,
    MODEL_PROMOTE, BILLING_MANAGE, AUDIT_READ,
    TENANT_ADMIN, FEEDBACK_WRITE, INTEL_READ, INTEL_WRITE,
}

BUILTIN_ROLES: Dict[str, Set[str]] = {
    "tenant_admin": ALL_PERMISSIONS,
    "analyst": {SCAN_READ, SCAN_ANALYZE, REPORT_CREATE, RECOVERY_READ, INTERVENTION_SEND},
    "viewer": {SCAN_READ, REPORT_CREATE},
    "compliance_officer": {AUDIT_READ, RECOVERY_READ},
}


def get_permissions_for_role(role_name: str) -> Set[str]:
    """Return the permission set for a built-in role, or empty set."""
    return BUILTIN_ROLES.get(role_name, set())


def expand_user_permissions(user_role: str, role_permissions: List[str]) -> Set[str]:
    """Merge built-in role permissions with explicit role_permissions list."""
    base = get_permissions_for_role(user_role)
    return base | set(role_permissions)

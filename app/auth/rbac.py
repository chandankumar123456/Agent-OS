"""Role-based access control primitives.

This module is plain Python: it has no FastAPI imports and raises plain
domain exceptions on permission failures.  The FastAPI dependency-style
glue (``require_permission``, ``require_role``) lives in
``app.api.deps`` and calls into these primitives.
"""
from enum import Enum
from typing import Any, Iterable


class Role(str, Enum):
    admin = "admin"
    user = "user"
    viewer = "viewer"


class Permission(str, Enum):
    create_task = "create_task"
    create_agent = "create_agent"
    create_workflow = "create_workflow"
    delete_any = "delete_any"
    manage_users = "manage_users"
    view_analytics = "view_analytics"


ROLE_PERMISSIONS = {
    Role.admin: list(Permission),
    Role.user: [
        Permission.create_task,
        Permission.create_agent,
        Permission.create_workflow,
        Permission.view_analytics,
    ],
    Role.viewer: [
        Permission.view_analytics,
    ],
}


class AuthorizationError(Exception):
    """Raised when a principal lacks the requested role/permission.

    Carries an HTTP-shaped status hint (default 403) so the route layer can
    surface the failure cleanly without this module importing FastAPI.
    """

    def __init__(self, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def has_permission(user: Any, permission: Permission) -> bool:
    role_str = getattr(user, "role", "user")
    role = Role(role_str) if role_str in [r.value for r in Role] else Role.user
    return permission in ROLE_PERMISSIONS.get(role, [])


def check_permission(
    user: Any,
    permission: Permission,
    *,
    auth_type: str | None = None,
    api_key_permissions: Iterable[str] | None = None,
) -> None:
    """Raise :class:`AuthorizationError` if ``user`` may not perform ``permission``.

    When the principal authenticated via API key, the explicit
    ``api_key_permissions`` list takes precedence over role-based rules.
    """
    if auth_type == "api_key":
        if permission.value in (api_key_permissions or []):
            return
        raise AuthorizationError(f"Permission denied: {permission.value}")

    if not has_permission(user, permission):
        raise AuthorizationError(f"Permission denied: {permission.value}")


def check_role(user: Any, role: Role) -> None:
    """Raise :class:`AuthorizationError` if ``user`` does not have ``role``."""
    user_role = getattr(user, "role", "user")
    if user_role != role.value:
        raise AuthorizationError(f"{role.value} access required")

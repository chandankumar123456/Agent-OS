from enum import Enum
from fastapi import HTTPException, status, Request
from typing import Any


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


def has_permission(user: Any, permission: Permission) -> bool:
    role_str = getattr(user, "role", "user")
    role = Role(role_str) if role_str in [r.value for r in Role] else Role.user
    return permission in ROLE_PERMISSIONS.get(role, [])


def require_permission(permission: Permission):
    from fastapi import Depends
    from ..api.deps import get_current_user

    async def _check_permission(
        request: Request,
        current_user: Any = Depends(get_current_user)
    ):
        # Check API key permissions if authenticated via API key
        auth_type = getattr(request.state, "auth_type", None)
        if auth_type == "api_key":
            api_key_permissions = getattr(request.state, "api_key_permissions", [])
            if permission.value in api_key_permissions:
                return current_user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}"
            )
        
        # Otherwise check role-based permissions
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}"
            )
        return current_user
    return _check_permission


def require_role(role: Role):
    from fastapi import Depends
    from ..api.deps import get_current_user

    async def _check_role(current_user: Any = Depends(get_current_user)):
        user_role = getattr(current_user, "role", "user")
        if user_role != role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{role.value} access required"
            )
        return current_user
    return _check_role

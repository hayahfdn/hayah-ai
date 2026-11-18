from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Role, User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)

# Role groups used by the routers.
ALL_ROLES = set(Role)
MANAGERS = {Role.super_admin, Role.operations_manager}
ADMINS = {Role.super_admin}
FIELD_WRITERS = {Role.super_admin, Role.operations_manager, Role.contractor}
MAINTENANCE_WRITERS = {Role.super_admin, Role.operations_manager, Role.maintenance}


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.token_version != payload.get("tv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session no longer valid")
    return user


def require_roles(*roles: Role | set):
    allowed: set = set()
    for r in roles:
        allowed |= r if isinstance(r, set) else {r}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot perform this action")
        return user
    return checker


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None

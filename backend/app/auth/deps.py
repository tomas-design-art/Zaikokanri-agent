"""FastAPI dependencies for auth + role checks."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.db import get_db
from app.models import User

ACCESS_COOKIE_NAME = "zk_access"
REFRESH_COOKIE_NAME = "zk_refresh"


# Role hierarchy
ROLE_LEVEL = {"GUEST": 1, "USER": 2, "ADMIN": 3}


@dataclass(slots=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    role: str
    department: str | None
    department_id: int | None

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    @property
    def is_guest(self) -> bool:
        return self.role == "GUEST"

    def has_role(self, required: str) -> bool:
        return ROLE_LEVEL.get(self.role, 0) >= ROLE_LEVEL.get(required, 99)


def _read_token(request: Request, cookie_val: str | None) -> str | None:
    if cookie_val:
        return cookie_val
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    zk_access: str | None = Cookie(default=None),
) -> CurrentUser:
    token = _read_token(request, zk_access)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    username = payload.get("sub")
    user: User | None = db.query(User).filter(User.username == username, User.is_active == 1).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.user_role,
        department=user.department,
        department_id=user.department_id,
    )


def require_role(required: str):
    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_role(required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _checker


require_admin = require_role("ADMIN")
require_user = require_role("USER")

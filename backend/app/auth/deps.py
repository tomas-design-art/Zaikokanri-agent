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
ROLES = tuple(ROLE_LEVEL)

# パスワード変更が必須のユーザーでも呼べるパス（A-03）
_ALLOWED_WHILE_MUST_CHANGE = {"/auth/me", "/auth/password", "/auth/logout", "/auth/refresh"}
PASSWORD_CHANGE_REQUIRED = "パスワードの変更が必要です。新しいパスワードを設定してください。"
SESSION_REVOKED = "パスワードが変更されたため、もう一度ログインしてください"


def revoke_sessions(user: User) -> None:
    """これまでに発行したトークンをすべて使えなくする（G-03）。"""
    user.token_version = (user.token_version or 0) + 1


@dataclass(slots=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    role: str
    department: str | None
    department_id: int | None
    must_change_password: bool = False

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


def to_current_user(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.user_role,
        department=user.department,
        department_id=user.department_id,
        must_change_password=bool(user.must_change_password),
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    zk_access: str | None = Cookie(default=None),
) -> CurrentUser:
    token = _read_token(request, zk_access)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ログインしてください")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ログインの有効期限が切れました")
    user: User | None = db.query(User).filter(User.username == payload.get("sub"), User.is_active == 1).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ユーザーが見つかりません")
    if payload.get("ver", 0) != (user.token_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_REVOKED)
    current = to_current_user(user)
    if current.must_change_password and request.url.path not in _ALLOWED_WHILE_MUST_CHANGE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_CHANGE_REQUIRED)
    return current


def require_role(required: str):
    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_role(required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="この操作の権限がありません")
        return user

    return _checker


require_admin = require_role("ADMIN")
require_user = require_role("USER")

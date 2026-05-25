"""Auth router: /auth/login, /auth/logout, /auth/me, /auth/refresh."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/auth", tags=["auth"])

limiter = Limiter(key_func=get_remote_address)


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    samesite = settings.cookie_samesite.lower()
    if samesite not in {"lax", "strict", "none"}:
        samesite = "lax"
    common = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": samesite,
        "path": "/",
    }
    if settings.cookie_domain:
        common["domain"] = settings.cookie_domain
    response.set_cookie(
        ACCESS_COOKIE_NAME, access, max_age=settings.jwt_access_ttl_min * 60, **common
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME, refresh, max_age=settings.jwt_refresh_ttl_days * 86400, **common
    )


def _clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        response.delete_cookie(name, path="/", domain=settings.cookie_domain or None)


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.rate_limit_login)
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    user: User | None = db.query(User).filter(User.username == body.username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="認証に失敗しました")
    ok, is_legacy = verify_password(body.password, user.password_hash)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="認証に失敗しました")
    # Transparent migration of legacy SHA-256 to bcrypt
    if is_legacy:
        user.password_hash = hash_password(body.password)
        db.commit()

    access = create_access_token(sub=user.username, role=user.user_role, extra={"uid": user.id})
    refresh = create_refresh_token(sub=user.username)
    _set_auth_cookies(response, access, refresh)
    return LoginResponse(
        user=MeResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.user_role,
            department=user.department,
            department_id=user.department_id,
        )
    )


@router.post("/logout")
def logout(response: Response) -> dict:
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        department=user.department,
        department_id=user.department_id,
    )


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh")
    username = payload.get("sub")
    user: User | None = db.query(User).filter(User.username == username, User.is_active == 1).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    access = create_access_token(sub=user.username, role=user.user_role, extra={"uid": user.id})
    new_refresh = create_refresh_token(sub=user.username)
    _set_auth_cookies(response, access, new_refresh)
    return {"ok": True}

"""Auth router: /auth/login, /auth/logout, /auth/me, /auth/refresh, /auth/password."""
from __future__ import annotations

from datetime import timedelta

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
from app.auth.deps import revoke_sessions, to_current_user
from app.config import settings
from app.db import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, PasswordChangeRequest
from app.security_log import security_event
from app.utils.datetime import jst_now

router = APIRouter(prefix="/auth", tags=["auth"])

limiter = Limiter(key_func=get_remote_address)

LOGIN_FAILED = "ユーザー名またはパスワードが違います"
# ユーザーが見つからないときも同じ重さの照合をするための、どのパスワードとも一致しないハッシュ（G-04）
_DUMMY_HASH = hash_password("dummy-password-for-timing-equalization")


def _set_auth_cookies(response: Response, user: User) -> None:
    ver = user.token_version or 0
    access = create_access_token(sub=user.username, role=user.user_role, extra={"uid": user.id, "ver": ver})
    refresh = create_refresh_token(sub=user.username, ver=ver)
    samesite = settings.cookie_samesite.lower()
    if samesite not in {"lax", "strict", "none"}:
        samesite = "lax"
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": samesite, "path": "/"}
    if settings.cookie_domain:
        common["domain"] = settings.cookie_domain
    response.set_cookie(ACCESS_COOKIE_NAME, access, max_age=settings.jwt_access_ttl_min * 60, **common)
    response.set_cookie(REFRESH_COOKIE_NAME, refresh, max_age=settings.jwt_refresh_ttl_days * 86400, **common)


def _clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        response.delete_cookie(name, path="/", domain=settings.cookie_domain or None)


def _me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        department=user.department,
        department_id=user.department_id,
        must_change_password=user.must_change_password,
    )


def _lock_message(user: User) -> str:
    minutes = max(1, int((user.locked_until - jst_now()).total_seconds() // 60) + 1)
    return f"ログインに続けて失敗したため、このアカウントを一時的にロックしています（あと約{minutes}分）。急ぐ場合は管理者に解除を依頼してください"


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.rate_limit_login)
def login(request: Request, response: Response, body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    username = body.username.strip()
    user: User | None = db.query(User).filter(User.username == username).first()
    ip = get_remote_address(request)
    if not user or not user.is_active:
        verify_password(body.password, _DUMMY_HASH)  # 応答時間でユーザーの有無を悟らせない（G-04）
        # ユーザー名の欄にパスワードを打ち間違えることがあるので、存在しない名前は記録に残さない（H-13）
        security_event("login_failed", user=username if user else f"(不明・{len(username)}文字)", reason="unknown_or_inactive", ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=LOGIN_FAILED)
    now = jst_now()
    if user.locked_until and user.locked_until > now:
        security_event("login_blocked", user=username, ip=ip)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_lock_message(user))
    ok, is_legacy = verify_password(body.password, user.password_hash)
    if not ok:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        security_event("login_failed", user=username, reason="bad_password", count=user.failed_login_count, ip=ip)
        if user.failed_login_count >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_count = 0
            security_event("account_locked", user=username, minutes=settings.login_lock_minutes, ip=ip)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=LOGIN_FAILED)
    user.failed_login_count, user.locked_until = 0, None
    if is_legacy:  # 旧 SHA-256 → bcrypt へ透過的に移行
        user.password_hash = hash_password(body.password)
    db.commit()
    security_event("login_succeeded", user=username, ip=ip)
    _set_auth_cookies(response, user)
    return LoginResponse(user=_me(to_current_user(user)))


@router.post("/logout")
def logout(response: Response) -> dict:
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return _me(user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    payload = decode_token(token) if token else None
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="もう一度ログインしてください")
    user: User | None = db.query(User).filter(User.username == payload.get("sub"), User.is_active == 1).first()
    # パスワード変更・リセット・無効化より前のリフレッシュは使えない（G-03）
    if not user or payload.get("ver", 0) != (user.token_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="もう一度ログインしてください")
    _set_auth_cookies(response, user)
    return {"ok": True}


@router.post("/password")
def change_password(
    body: PasswordChangeRequest,
    response: Response,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict:
    """自分のパスワードを変える（A-04）。変更必須フラグもここで外れる（A-03）。

    ほかの端末のログインは無効にし、今の画面には新しいトークンを渡して続けられるようにする（G-03）。
    """
    user = db.get(User, current.id)
    ok, _ = verify_password(body.current_password, user.password_hash)
    if not ok:
        security_event("password_change_failed", user=user.username)
        raise HTTPException(400, "今のパスワードが違います")
    if body.current_password == body.new_password:
        raise HTTPException(400, "新しいパスワードは今のパスワードと別のものにしてください")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = 0
    revoke_sessions(user)
    db.commit()
    security_event("password_changed", user=user.username)
    _set_auth_cookies(response, user)
    return {"ok": True}

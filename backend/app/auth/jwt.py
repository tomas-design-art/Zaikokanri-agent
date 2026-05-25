"""JWT encode/decode helpers."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.config import settings


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def create_access_token(sub: str, role: str, extra: dict | None = None) -> str:
    now = _now_utc()
    payload = {
        "sub": sub,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_ttl_min)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(sub: str) -> str:
    now = _now_utc()
    payload = {
        "sub": sub,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_refresh_ttl_days)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

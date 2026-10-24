"""JWT encode/decode helpers (PyJWT)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(sub: str, role: str, extra: dict | None = None) -> str:
    now = _now_utc()
    payload = {
        "sub": sub,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_ttl_min),
    }
    if extra:
        payload.update(extra)
    return _encode(payload)


def create_refresh_token(sub: str, ver: int = 0) -> str:
    now = _now_utc()
    return _encode(
        {"sub": sub, "type": "refresh", "ver": ver, "iat": now, "exp": now + timedelta(days=settings.jwt_refresh_ttl_days)}
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        return None

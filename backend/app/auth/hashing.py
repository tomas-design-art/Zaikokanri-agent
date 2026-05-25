"""Password hashing — bcrypt as primary, legacy `salt$sha256` for migration compat.

Returns True if the legacy hash matched. Caller should then re-hash with bcrypt
and persist the new value (transparent migration).
"""
from __future__ import annotations

import hashlib

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return (ok, is_legacy). If is_legacy, caller should re-hash."""
    if not stored_hash:
        return False, False
    try:
        if stored_hash.startswith("$2"):
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")), False
        if "$" in stored_hash:
            salt, expected = stored_hash.split("$", 1)
            calc = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
            return calc == expected, True
    except (ValueError, AttributeError):
        return False, False
    return False, False

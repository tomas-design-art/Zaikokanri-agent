"""JST timezone utilities (Streamlit版 utils/date_utils.py 互換)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def jst_now() -> datetime:
    """Return current datetime in JST (naive, for SQLite compat)."""
    return datetime.now(JST).replace(tzinfo=None)


def jst_now_iso() -> str:
    return jst_now().isoformat(timespec="seconds")

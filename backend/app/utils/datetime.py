"""JST timezone utilities.

DB には JST の naive datetime を保存する（SPEC.md「時刻管理ルール」）。
サーバーの時計（Render は UTC）に依存しないよう、「今日」も必ず JST で求める（B-17）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def jst_now() -> datetime:
    """Return current datetime in JST (naive, for SQLite compat)."""
    return datetime.now(JST).replace(tzinfo=None)


def jst_today() -> date:
    return jst_now().date()


def jst_now_iso() -> str:
    return jst_now().isoformat(timespec="seconds")


def month_start(d: date, months_back: int = 0) -> date:
    """d を含む月の1日から months_back か月さかのぼった月の1日。"""
    y, m = d.year, d.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def day_range(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """[開始日 0:00, 終了日の翌日 0:00) の半開区間に直す。"""
    start = datetime.combine(date_from, datetime.min.time()) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time()) if date_to else None
    return start, end

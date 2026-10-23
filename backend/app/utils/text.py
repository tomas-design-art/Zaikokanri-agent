"""文字列の共通処理。"""
from __future__ import annotations

from typing import Any

LIKE_ESCAPE = "\\"


def blank_to_none(v: Any) -> Any:
    """画面から来る空文字・空白だけの文字列を「未設定（None）」にそろえる（B-01）。"""
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def like_pattern(q: str) -> str:
    """ユーザー入力の % _ を文字として扱う部分一致パターン（B-15）。"""
    escaped = q.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")
    return f"%{escaped}%"


def contains(column, q: str):
    """大文字小文字を区別しない部分一致（PostgreSQL / SQLite 共通）。"""
    return column.ilike(like_pattern(q), escape=LIKE_ESCAPE)


# CSV / Excel を開いたときに数式として実行される先頭の文字（OWASP: CSV Injection）（G-01）
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(v):  # noqa: ANN001, ANN201
    """CSV のセル。数式と解釈される文字列の先頭に ' を付けて、ただの文字にする。"""
    if isinstance(v, str) and v.startswith(FORMULA_PREFIXES):
        return "'" + v
    return v

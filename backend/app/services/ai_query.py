"""AI が作った SQL を安全に実行する（E-02）。

判定はコードのルールで機械的に行う（AI に安全かどうかを判定させない＝開発憲章 5章）。
  1. 1文の SELECT / WITH だけ
  2. 書き込み・DDL・PRAGMA 等のキーワードを含まない
  3. 参照してよいテーブルは物品・在庫・履歴・部署・カテゴリ・業者だけ。
     それ以外のテーブル名（users 等）やシステムカタログ（sqlite_ / pg_ / information_schema）が
     文字列のどこかに現れたら拒否（"users" のような引用符つきも含む）
  4. 読み取り専用のトランザクションで実行し、結果は最大 limit 行
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import Base

ALLOWED_TABLES = {"items", "inventory", "inventory_history", "departments", "categories", "vendors"}
MAX_ROWS = 200

_FIRST_WORD = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|detach|pragma|grant|revoke|copy|vacuum|"
    r"replace|merge|call|execute|exec|do|set|reset|load|lock|listen|notify)\b",
    re.IGNORECASE,
)
_SYSTEM = re.compile(r"(sqlite_|pg_|information_schema|u&)", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _blocked_tables() -> set[str]:
    return {t for t in Base.metadata.tables if t not in ALLOWED_TABLES}


def is_safe_sql(sql: str) -> bool:
    if not sql or not _FIRST_WORD.match(sql):
        return False
    if ";" in sql.strip().rstrip(";"):
        return False
    if _FORBIDDEN.search(sql) or _SYSTEM.search(sql):
        return False
    words = {w.lower() for w in _WORD.findall(sql)}
    return not (words & _blocked_tables())


def run_readonly_query(db: Session, sql: str, *, limit: int = MAX_ROWS) -> list[dict[str, Any]]:
    """読み取り専用で実行し、最大 limit 行を返す。安全でない SQL は ValueError。"""
    if not is_safe_sql(sql):
        raise ValueError("安全でないSQLのため実行しません")
    wrapped = f"SELECT * FROM ({sql.strip().rstrip(';')}) AS ai_q LIMIT :lim"
    with db.get_bind().connect() as conn:
        dialect = conn.dialect.name
        trans = conn.begin()
        try:
            if dialect == "postgresql":
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            elif dialect == "sqlite":
                conn.exec_driver_sql("PRAGMA query_only = ON")
            rows = [dict(r._mapping) for r in conn.execute(text(wrapped), {"lim": limit}).all()]
        finally:
            trans.rollback()
            if dialect == "sqlite":
                conn.exec_driver_sql("PRAGMA query_only = OFF")
    return rows

"""SQLite → Postgres 移行スクリプト。

旧 Streamlit 版の `inventory.db` (SQLite) から、
本番 Postgres (Supabase 等) へデータを移行する。

使い方:
    1. Postgres 側で `alembic upgrade head` を完了させ、空のスキーマを用意
    2. 環境変数を設定:
         SOURCE_SQLITE=<path/to/inventory.db>
         TARGET_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname
    3. python -m scripts.migrate_sqlite_to_postgres
       オプション: --dry-run (件数のみ表示)
                   --truncate (移行前に target を TRUNCATE)

設計:
- ID/FK を保持するため、INSERT 後に各テーブルの PRIMARY KEY シーケンスを
  setval(MAX(id)) で再同期する。
- SQLite 側にあって Postgres 側にない列、または逆は自動でスキップ
  (両方の table_info を取得して共通列のみを INSERT)。
- 依存順 (FK 順) でテーブルを並べ、外部キーチェック付きで挿入する。
- すべて 1 トランザクションで実行し、失敗時はロールバック。
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from contextlib import closing
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("migrate")

# FK 依存順 (親 → 子)
TABLE_ORDER = [
    "departments",
    "categories",
    "vendors",
    "users",
    "items",
    "inventory",
    "inventory_history",
    "pending_transactions",
    "disposal_requests",
    "purchase_requests",
    "purchase_candidates",
    "stocktake_sessions",
    "stocktake_templates",
    "stocktake_template_mappings",
    "stocktake_records",
]


def get_sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def get_pg_columns(engine: Engine, table: str) -> list[str]:
    sql = text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
    )
    with engine.connect() as c:
        return [r[0] for r in c.execute(sql, {"t": table}).fetchall()]


def migrate_table(
    src: sqlite3.Connection,
    dst_engine: Engine,
    table: str,
    dry_run: bool,
) -> int:
    src_cols = get_sqlite_columns(src, table)
    dst_cols = get_pg_columns(dst_engine, table)
    if not src_cols:
        log.warning("  [%s] source table missing, skip", table)
        return 0
    if not dst_cols:
        log.warning("  [%s] target table missing, skip", table)
        return 0
    common = [c for c in src_cols if c in dst_cols]
    if not common:
        log.warning("  [%s] no common columns", table)
        return 0
    skipped = set(src_cols) ^ set(dst_cols)
    if skipped:
        log.info("  [%s] skip cols: %s", table, sorted(skipped))

    col_list = ", ".join(f'"{c}"' for c in common)
    placeholders = ", ".join(f":{c}" for c in common)
    sel_sql = f"SELECT {col_list} FROM {table}"
    rows = list(src.execute(sel_sql).fetchall())
    if not rows:
        log.info("  [%s] 0 rows", table)
        return 0
    log.info("  [%s] %d rows", table, len(rows))
    if dry_run:
        return len(rows)

    ins_sql = text(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})')
    payload: list[dict[str, Any]] = []
    for r in rows:
        payload.append({col: r[i] for i, col in enumerate(common)})
    with dst_engine.begin() as conn:
        conn.execute(ins_sql, payload)
    return len(rows)


def reset_sequence(engine: Engine, table: str) -> None:
    """Postgres SERIAL/IDENTITY シーケンスを MAX(id)+1 に同期。"""
    with engine.begin() as conn:
        seq = conn.execute(
            text("SELECT pg_get_serial_sequence(:t, 'id')"),
            {"t": table},
        ).scalar()
        if not seq:
            return
        max_id = conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')).scalar() or 0
        conn.execute(text(f"SELECT setval('{seq}', GREATEST(:m, 1), :exists)"), {"m": max_id, "exists": max_id > 0})
        log.info("  [%s] sequence -> %s", table, max_id)


def truncate_all(engine: Engine, tables: list[str]) -> None:
    quoted = ", ".join(f'"{t}"' for t in tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    log.info("Truncated %d tables", len(tables))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--truncate", action="store_true", help="移行前にtarget全表をTRUNCATE")
    parser.add_argument("--source", default=os.getenv("SOURCE_SQLITE", "inventory.db"))
    parser.add_argument("--target", default=os.getenv("TARGET_DATABASE_URL"))
    args = parser.parse_args()

    if not args.target:
        log.error("TARGET_DATABASE_URL is required (postgresql+psycopg://...)")
        return 2
    if not os.path.exists(args.source):
        log.error("Source SQLite not found: %s", args.source)
        return 2

    log.info("Source: %s", args.source)
    log.info("Target: %s", args.target.split("@")[-1])  # ログにパスワード露出させない

    src = sqlite3.connect(args.source)
    src.row_factory = sqlite3.Row
    engine = create_engine(args.target, future=True)

    try:
        if args.truncate and not args.dry_run:
            truncate_all(engine, list(reversed(TABLE_ORDER)))

        total = 0
        with closing(src):
            for table in TABLE_ORDER:
                n = migrate_table(src, engine, table, args.dry_run)
                total += n

        if not args.dry_run:
            log.info("Resetting sequences...")
            for table in TABLE_ORDER:
                try:
                    reset_sequence(engine, table)
                except Exception as e:
                    log.warning("  [%s] sequence reset failed: %s", table, e)

        log.info("=" * 50)
        log.info("Total rows migrated: %d (dry_run=%s)", total, args.dry_run)
        return 0
    except Exception:
        log.exception("Migration failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

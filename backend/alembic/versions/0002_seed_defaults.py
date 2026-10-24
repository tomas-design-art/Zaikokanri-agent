"""seed defaults: default admin, departments, categories, vendors

Revision ID: 0002_seed_defaults
Revises: 0001_initial
Create Date: 2026-05-25 00:01:00

2026-10-23 修正：元は exec_driver_sql に `:n` 形式の値を渡しており、PostgreSQL（psycopg3）では必ず失敗していた
（空の PostgreSQL では起動できなかった）。sa.text() で書き直した。PostgreSQL で成功したことは無いので、
適用済みの DB への影響は無い。SQLite で適用済みの DB は再実行されない。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import sqlalchemy as sa

from alembic import op

revision = "0002_seed_defaults"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _jst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None, microsecond=0)


def _insert_ignore(conn, table: str, cols: list[str], conflict: str, rows: list[dict]) -> None:  # noqa: ANN001
    """既にあれば入れない INSERT（SQLite / PostgreSQL 共通）。"""
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    if conn.dialect.name == "sqlite":
        stmt = f"INSERT OR IGNORE INTO {table} ({names}) VALUES ({values})"
    else:
        stmt = f"INSERT INTO {table} ({names}) VALUES ({values}) ON CONFLICT ({conflict}) DO NOTHING"
    for row in rows:
        conn.execute(sa.text(stmt), row)


def upgrade() -> None:
    conn = op.get_bind()
    now = _jst_now()

    _insert_ignore(
        conn, "departments", ["name", "is_active", "created_at"], "name",
        [{"name": d, "is_active": 1, "created_at": now} for d in ["総務部", "営業部", "経理部", "看護係", "薬剤部", "未設定"]],
    )
    _insert_ignore(
        conn, "categories", ["name", "is_active", "created_at"], "name",
        [{"name": c, "is_active": 1, "created_at": now} for c in ["事務用品", "薬品", "医療機器", "消耗品", "その他"]],
    )
    vendors = [
        ("V001", "○○商事", "東京都千代田区1-2-3", "03-1234-5678", "info@example.co.jp"),
        ("V002", "△△物産", "大阪府大阪市2-3-4", "06-9876-5432", "sales@example.com"),
        ("V003", "未登録業者", "", "", ""),
    ]
    _insert_ignore(
        conn, "vendors",
        ["vendor_code", "vendor_name", "address", "phone", "email", "is_active", "created_at", "updated_at"], "vendor_code",
        [
            {"vendor_code": c, "vendor_name": n, "address": a, "phone": p, "email": e, "is_active": 1, "created_at": now, "updated_at": now}
            for c, n, a, p, e in vendors
        ],
    )
    # 初期管理者（admin / admin123）。0003 でパスワード変更が必須になる
    pw = bcrypt.hashpw(b"admin123", bcrypt.gensalt(rounds=12)).decode("utf-8")
    _insert_ignore(
        conn, "users",
        ["username", "password_hash", "display_name", "department", "user_role", "is_active", "created_at", "updated_at"], "username",
        [{"username": "admin", "password_hash": pw, "display_name": "管理者", "department": "総務部", "user_role": "ADMIN",
          "is_active": 1, "created_at": now, "updated_at": now}],
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM users WHERE username = 'admin'"))
    conn.execute(sa.text("DELETE FROM vendors WHERE vendor_code IN ('V001', 'V002', 'V003')"))
    conn.execute(sa.text("DELETE FROM categories"))
    conn.execute(sa.text("DELETE FROM departments"))

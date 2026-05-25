"""seed defaults: default admin, departments, categories, vendors

Revision ID: 0002_seed_defaults
Revises: 0001_initial
Create Date: 2026-05-25 00:01:00
"""
from __future__ import annotations

import bcrypt
from alembic import op
from datetime import datetime, timedelta, timezone

revision = "0002_seed_defaults"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _jst_now_str() -> str:
    return datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None).isoformat(timespec="seconds")


def upgrade() -> None:
    conn = op.get_bind()
    now = _jst_now_str()

    # Departments
    depts = ["総務部", "営業部", "経理部", "看護係", "薬剤部", "未設定"]
    for d in depts:
        conn.exec_driver_sql(
            "INSERT INTO departments (name, is_active, created_at) VALUES (:n, 1, :t) "
            + ("ON CONFLICT(name) DO NOTHING" if conn.dialect.name != "sqlite" else ""),
            {"n": d, "t": now},
        ) if conn.dialect.name != "sqlite" else conn.exec_driver_sql(
            "INSERT OR IGNORE INTO departments (name, is_active, created_at) VALUES (:n, 1, :t)",
            {"n": d, "t": now},
        )

    # Categories
    cats = ["事務用品", "薬品", "医療機器", "消耗品", "その他"]
    for c in cats:
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO categories (name, is_active, created_at) VALUES (:n, 1, :t)",
                {"n": c, "t": now},
            )
        else:
            conn.exec_driver_sql(
                "INSERT INTO categories (name, is_active, created_at) VALUES (:n, 1, :t) ON CONFLICT(name) DO NOTHING",
                {"n": c, "t": now},
            )

    # Vendors
    vendors = [
        ("V001", "○○商事", "東京都千代田区1-2-3", "03-1234-5678", "info@example.co.jp"),
        ("V002", "△△物産", "大阪府大阪市2-3-4", "06-9876-5432", "sales@example.com"),
        ("V003", "未登録業者", "", "", ""),
    ]
    for code, name, addr, phone, email in vendors:
        params = {"c": code, "n": name, "a": addr, "p": phone, "e": email, "t": now}
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO vendors (vendor_code, vendor_name, address, phone, email, is_active, created_at, updated_at) "
                "VALUES (:c, :n, :a, :p, :e, 1, :t, :t)",
                params,
            )
        else:
            conn.exec_driver_sql(
                "INSERT INTO vendors (vendor_code, vendor_name, address, phone, email, is_active, created_at, updated_at) "
                "VALUES (:c, :n, :a, :p, :e, 1, :t, :t) ON CONFLICT(vendor_code) DO NOTHING",
                params,
            )

    # Default admin (admin / admin123) — bcrypt
    pw = bcrypt.hashpw(b"admin123", bcrypt.gensalt(rounds=12)).decode("utf-8")
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql(
            "INSERT OR IGNORE INTO users (username, password_hash, display_name, department, user_role, is_active, created_at, updated_at) "
            "VALUES ('admin', :h, '管理者', '総務部', 'ADMIN', 1, :t, :t)",
            {"h": pw, "t": now},
        )
    else:
        conn.exec_driver_sql(
            "INSERT INTO users (username, password_hash, display_name, department, user_role, is_active, created_at, updated_at) "
            "VALUES ('admin', :h, '管理者', '総務部', 'ADMIN', 1, :t, :t) ON CONFLICT(username) DO NOTHING",
            {"h": pw, "t": now},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DELETE FROM users WHERE username='admin'")
    conn.exec_driver_sql("DELETE FROM vendors WHERE vendor_code IN ('V001','V002','V003')")
    conn.exec_driver_sql("DELETE FROM categories")
    conn.exec_driver_sql("DELETE FROM departments")

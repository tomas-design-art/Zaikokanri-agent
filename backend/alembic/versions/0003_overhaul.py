"""overhaul: unit, must_change_password, history ref, stocktake scope, data cleanup

Revision ID: 0003_overhaul
Revises: 0002_seed_defaults
Create Date: 2026-10-23 00:00:00

docs/REVIEW_2026-10-23.md の A-03 / B-01 / B-02 / B-10 / B-19 / D-07 / G-02 / G-03 / H-04 / H-10 / H-11 に対応。
"""
from __future__ import annotations

import re

import bcrypt
import sqlalchemy as sa

from alembic import op

revision = "0003_overhaul"
down_revision = "0002_seed_defaults"
branch_labels = None
depends_on = None

# 空文字を NULL に直す列（B-01：空文字の期限が「期限切れ」に数えられていた）
_BLANK_TO_NULL = [
    "item_code", "vendor_name", "vendor_item_code", "department_tags", "frequency_tag",
    "expiry_date", "location_text", "last_inspection_date", "next_inspection_date",
]


def upgrade() -> None:
    # モデルと同じく NOT NULL（既定値つき）にそろえる（H-11）
    op.add_column("items", sa.Column("unit", sa.String(16), nullable=False, server_default="個"))
    op.add_column("users", sa.Column("must_change_password", sa.Integer, nullable=False, server_default="0"))
    op.add_column("users", sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime))
    op.add_column("users", sa.Column("token_version", sa.Integer, nullable=False, server_default="0"))
    op.add_column("inventory_history", sa.Column("ref_type", sa.String(16)))
    op.add_column("inventory_history", sa.Column("ref_id", sa.Integer))
    op.add_column("stocktake_sessions", sa.Column("scope_category", sa.String(64)))
    # 実施中（OPEN）の棚卸しは1つだけ（H-04）。古いデータに複数あれば、新しい1つを残して中止にする
    op.get_bind().execute(sa.text(
        "UPDATE stocktake_sessions SET status = 'CANCELLED' WHERE status = 'OPEN' AND id <> "
        "(SELECT MAX(id) FROM stocktake_sessions WHERE status = 'OPEN')"
    ))
    op.create_index("uq_stocktake_one_open", "stocktake_sessions", ["status"], unique=True,
                    sqlite_where=sa.text("status = 'OPEN'"), postgresql_where=sa.text("status = 'OPEN'"))

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE items SET unit = '個' WHERE unit IS NULL"))
    for col in _BLANK_TO_NULL:
        conn.execute(sa.text(f"UPDATE items SET {col} = NULL WHERE TRIM({col}) = ''"))  # noqa: S608 (固定の列名)
    conn.execute(sa.text("UPDATE items SET unit_price = 0 WHERE unit_price IS NULL"))
    # 古い日付の書き方（2026/10/01・2026-1-5 など）を YYYY-MM-DD にそろえる。期限切れの判定は文字の大小で比べるため（H-10）
    for col in ("expiry_date", "last_inspection_date", "next_inspection_date"):
        rows = conn.execute(sa.text(f"SELECT id, {col} FROM items WHERE {col} IS NOT NULL")).all()  # noqa: S608
        for item_id, value in rows:
            m = re.fullmatch(r"\s*(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})\s*", value)
            if m:
                iso = f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
                if iso != value:
                    conn.execute(sa.text(f"UPDATE items SET {col} = :v WHERE id = :i"), {"v": iso, "i": item_id})  # noqa: S608
    # B-02：発注点（items.reorder_point）を在庫不足の判定（inventory.threshold）にそろえる
    conn.execute(
        sa.text(
            "UPDATE inventory SET threshold = ("
            " SELECT items.reorder_point FROM items WHERE items.id = inventory.item_id"
            ") WHERE EXISTS ("
            " SELECT 1 FROM items WHERE items.id = inventory.item_id AND items.reorder_point IS NOT NULL)"
        )
    )
    conn.execute(sa.text("UPDATE users SET must_change_password = 0 WHERE must_change_password IS NULL"))
    # 部署名だけ入っていて部署IDが空のユーザー（0002 の初期管理者など）に部署IDを入れる
    conn.execute(
        sa.text(
            "UPDATE users SET department_id = (SELECT departments.id FROM departments WHERE departments.name = users.department)"
            " WHERE department_id IS NULL AND department IS NOT NULL"
        )
    )
    # A-03：初期パスワード（admin / admin123）のままの管理者は変更を必須にする
    for uid, pw_hash in conn.execute(sa.text("SELECT id, password_hash FROM users WHERE username = 'admin'")):
        try:
            is_default = bool(pw_hash) and pw_hash.startswith("$2") and bcrypt.checkpw(b"admin123", pw_hash.encode())
        except ValueError:
            is_default = False
        if is_default:
            conn.execute(sa.text("UPDATE users SET must_change_password = 1 WHERE id = :i"), {"i": uid})


def downgrade() -> None:
    op.drop_index("uq_stocktake_one_open", table_name="stocktake_sessions")
    with op.batch_alter_table("stocktake_sessions") as b:
        b.drop_column("scope_category")
    with op.batch_alter_table("inventory_history") as b:
        b.drop_column("ref_id")
        b.drop_column("ref_type")
    with op.batch_alter_table("users") as b:
        b.drop_column("token_version")
        b.drop_column("locked_until")
        b.drop_column("failed_login_count")
        b.drop_column("must_change_password")
    with op.batch_alter_table("items") as b:
        b.drop_column("unit")

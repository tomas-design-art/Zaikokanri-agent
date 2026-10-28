"""departments: 部署ごとの見える範囲・ゲストの廃棄の連絡・申請と履歴の部署ID

Revision ID: 0004_departments
Revises: 0003_overhaul
Create Date: 2026-10-24 00:00:00

docs/REVIEW_2026-10-23.md の I-01 / I-02 / I-06 / I-08 に対応。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_departments"
down_revision = "0003_overhaul"
branch_labels = None
depends_on = None

_DEPT_ID_TABLES = ("inventory_history", "purchase_requests", "disposal_requests")


def upgrade() -> None:
    for table in _DEPT_ID_TABLES:
        op.add_column(table, sa.Column("department_id", sa.Integer))
        op.create_index(f"ix_{table}_department_id", table, ["department_id"])

    op.create_table(
        "disposal_notices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("reporter_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("department_id", sa.Integer, sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("status", sa.String(16), server_default="OPEN"),
        sa.Column("handled_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("handled_at", sa.DateTime),
        sa.Column("handled_comment", sa.Text),
        sa.Column("disposal_request_id", sa.Integer, sa.ForeignKey("disposal_requests.id")),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("idx_notice_status", "disposal_notices", ["status"])
    op.create_index("idx_notice_department", "disposal_notices", ["department_id"])

    conn = op.get_bind()
    # 既存の物品は「共通」から始める（所属部署が決まっている物品はそのまま：I-02）
    conn.execute(sa.text("UPDATE items SET is_common = 1 WHERE owner_department_id IS NULL"))
    # 過去の履歴・申請にも部署IDを埋める（I-06）。部署名が一致しないものは空のまま
    conn.execute(sa.text(
        "UPDATE inventory_history SET department_id = "
        "(SELECT d.id FROM departments d WHERE d.name = inventory_history.department) "
        "WHERE department IS NOT NULL"
    ))
    conn.execute(sa.text(
        "UPDATE purchase_requests SET department_id = COALESCE("
        "(SELECT d.id FROM departments d WHERE d.name = purchase_requests.requested_by_department), "
        "(SELECT u.department_id FROM users u WHERE u.id = purchase_requests.requested_by_user_id))"
    ))
    conn.execute(sa.text(
        "UPDATE disposal_requests SET department_id = "
        "(SELECT u.department_id FROM users u WHERE u.id = disposal_requests.requester_id)"
    ))


def downgrade() -> None:
    op.drop_index("idx_notice_department", table_name="disposal_notices")
    op.drop_index("idx_notice_status", table_name="disposal_notices")
    op.drop_table("disposal_notices")
    for table in _DEPT_ID_TABLES:
        op.drop_index(f"ix_{table}_department_id", table_name=table)
        with op.batch_alter_table(table) as b:
            b.drop_column("department_id")
    # 物品の is_common は戻さない（0003 以前もこの列はあり、共通の印が付いていても動きは変わらない）

"""initial schema: all 14 tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-25 00:00:00

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_departments_name", "departments", ["name"], unique=True)

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_categories_name", "categories", ["name"], unique=True)

    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("vendor_code", sa.String(32), nullable=False, unique=True),
        sa.Column("vendor_name", sa.String(128), nullable=False, unique=True),
        sa.Column("address", sa.Text),
        sa.Column("phone", sa.String(32)),
        sa.Column("email", sa.String(128)),
        sa.Column("is_active", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_vendors_vendor_code", "vendors", ["vendor_code"], unique=True)
    op.create_index("ix_vendors_vendor_name", "vendors", ["vendor_name"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("department", sa.String(64)),
        sa.Column("department_id", sa.Integer, sa.ForeignKey("departments.id")),
        sa.Column("user_role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_department", "users", ["department"])
    op.create_index("ix_users_department_id", "users", ["department_id"])
    op.create_index("ix_users_user_role", "users", ["user_role"])

    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("item_code", sa.String(64)),
        sa.Column("vendor_name", sa.String(128)),
        sa.Column("vendor_item_code", sa.String(64)),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("department_tags", sa.Text),
        sa.Column("unit_price", sa.Float, server_default="0"),
        sa.Column("is_asset", sa.Integer, server_default="0"),
        sa.Column("frequency_tag", sa.String(32)),
        sa.Column("expiry_date", sa.String(32)),
        sa.Column("is_active", sa.Integer, server_default="1"),
        sa.Column("owner_department_id", sa.Integer, sa.ForeignKey("departments.id")),
        sa.Column("is_common", sa.Integer, server_default="0"),
        sa.Column("location_text", sa.String(128)),
        sa.Column("last_inspection_date", sa.String(32)),
        sa.Column("next_inspection_date", sa.String(32)),
        sa.Column("interval_months", sa.Integer),
        sa.Column("reorder_point", sa.Integer),
        sa.Column("is_inventory_target", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        sa.UniqueConstraint("vendor_name", "vendor_item_code", name="uq_items_vendor_itemcode"),
    )
    op.create_index("idx_items_name", "items", ["item_name"])
    op.create_index("idx_items_code", "items", ["item_code"])
    op.create_index("idx_items_category", "items", ["category"])
    op.create_index("idx_items_vendor", "items", ["vendor_name", "vendor_item_code"])

    op.create_table(
        "inventory",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False, unique=True),
        sa.Column("quantity", sa.Integer, server_default="0"),
        sa.Column("threshold", sa.Integer, server_default="10"),
        sa.Column("location", sa.String(128)),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_inventory_item_id", "inventory", ["item_id"], unique=True)

    op.create_table(
        "inventory_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("user_name", sa.String(64), nullable=False),
        sa.Column("department", sa.String(64)),
        sa.Column("status", sa.String(16), server_default="CONFIRMED"),
        sa.Column("note", sa.Text),
        sa.Column("vendor_name", sa.String(128)),
        sa.Column("unit_price", sa.Float),
        sa.Column("total_price", sa.Float),
        sa.Column("created_by", sa.Integer),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("idx_history_item", "inventory_history", ["item_id", "created_at"])
    op.create_index("idx_history_status", "inventory_history", ["status"])
    op.create_index("idx_history_change_type", "inventory_history", ["change_type"])
    op.create_index("ix_inventory_history_created_at", "inventory_history", ["created_at"])

    op.create_table(
        "pending_transactions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("actor_name", sa.String(64), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("guest_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("department_id", sa.Integer, sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING"),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("reject_reason", sa.Text),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("idx_pending_status", "pending_transactions", ["status"])
    op.create_index("idx_pending_department", "pending_transactions", ["department_id"])

    op.create_table(
        "disposal_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("requester_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING"),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("reject_reason", sa.Text),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("idx_disposal_status", "disposal_requests", ["status"])
    op.create_index("idx_disposal_requester", "disposal_requests", ["requester_id"])

    op.create_table(
        "purchase_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("requested_qty", sa.Integer, nullable=False),
        sa.Column("priority", sa.String(16), server_default="NORMAL"),
        sa.Column("due_date", sa.String(32)),
        sa.Column("note", sa.Text),
        sa.Column("requested_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_by_department", sa.String(64)),
        sa.Column("status", sa.String(16), server_default="PENDING"),
        sa.Column("admin_comment", sa.Text),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("deleted_at", sa.DateTime),
        sa.Column("deleted_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("received_qty", sa.Integer, server_default="0"),
        sa.Column("received_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("idx_pr_status", "purchase_requests", ["status"])
    op.create_index("idx_pr_requester", "purchase_requests", ["requested_by_user_id"])
    op.create_index("idx_pr_item", "purchase_requests", ["item_id"])

    op.create_table(
        "purchase_candidates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False, unique=True),
        sa.Column("auto_reason", sa.String(64)),
        sa.Column("selected_for_order", sa.Integer, server_default="0"),
        sa.Column("deferred", sa.Integer, server_default="0"),
        sa.Column("priority", sa.String(16), server_default="NORMAL"),
        sa.Column("recommended_qty", sa.Integer),
        sa.Column("note", sa.Text),
        sa.Column("status", sa.String(16), server_default="OPEN"),
        sa.Column("updated_by_user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("idx_pc_status", "purchase_candidates", ["status"])
    op.create_index("idx_pc_item", "purchase_candidates", ["item_id"])

    op.create_table(
        "stocktake_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("start_date", sa.String(32)),
        sa.Column("end_date", sa.String(32)),
        sa.Column("status", sa.String(16), server_default="OPEN"),
        sa.Column("note", sa.Text),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime),
        sa.Column("closed_at", sa.DateTime),
    )

    op.create_table(
        "stocktake_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("stocktake_sessions.id"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("system_qty", sa.Integer, server_default="0"),
        sa.Column("actual_qty", sa.Integer),
        sa.Column("diff_qty", sa.Integer),
        sa.Column("counted_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("counted_at", sa.DateTime),
        sa.Column("verified_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("verified_at", sa.DateTime),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("note", sa.Text),
        sa.Column("status", sa.String(16), server_default="PENDING"),
        sa.UniqueConstraint("session_id", "item_id", name="uq_stocktake_session_item"),
    )
    op.create_index("idx_st_records_session", "stocktake_records", ["session_id"])

    op.create_table(
        "stocktake_templates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("file_type", sa.String(16)),
        sa.Column("is_active", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )

    op.create_table(
        "stocktake_template_mappings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("stocktake_templates.id"), nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("excel_cell", sa.String(16)),
        sa.Column("display_label", sa.String(64)),
        sa.Column("sort_order", sa.Integer, server_default="0"),
    )


def downgrade() -> None:
    for tbl in [
        "stocktake_template_mappings",
        "stocktake_templates",
        "stocktake_records",
        "stocktake_sessions",
        "purchase_candidates",
        "purchase_requests",
        "disposal_requests",
        "pending_transactions",
        "inventory_history",
        "inventory",
        "items",
        "users",
        "vendors",
        "categories",
        "departments",
    ]:
        op.drop_table(tbl)

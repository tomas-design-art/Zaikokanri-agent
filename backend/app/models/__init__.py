"""ORM models (legacy SQLite schema + 0003 additions)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils.datetime import jst_now


# ---------- Mixins ----------
def _jst_now() -> datetime:
    return jst_now()


# ---------- Master tables ----------
class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    vendor_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, onupdate=_jst_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str | None] = mapped_column(String(64), index=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"), index=True
    )
    user_role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    # 1 = 次のログイン後にパスワード変更が必須（初期パスワード・管理者がリセットした場合）
    must_change_password: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # ログインに続けて失敗した回数と、ロックが解ける時刻（G-02）
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    # パスワード変更・リセット・無効化で増やす。これより古いトークンは使えない（G-03）
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, onupdate=_jst_now)

    department_rel = relationship("Department", lazy="joined")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("vendor_name", "vendor_item_code", name="uq_items_vendor_itemcode"),
        Index("idx_items_name", "item_name"),
        Index("idx_items_code", "item_code"),
        Index("idx_items_category", "category"),
        Index("idx_items_vendor", "vendor_name", "vendor_item_code"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(64))
    vendor_name: Mapped[str | None] = mapped_column(String(128))
    vendor_item_code: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="個", server_default="個")
    department_tags: Mapped[str | None] = mapped_column(Text)  # CSV
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    is_asset: Mapped[int] = mapped_column(Integer, default=0)
    frequency_tag: Mapped[str | None] = mapped_column(String(32))
    expiry_date: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    owner_department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    is_common: Mapped[int] = mapped_column(Integer, default=0)
    location_text: Mapped[str | None] = mapped_column(String(128))
    last_inspection_date: Mapped[str | None] = mapped_column(String(32))
    next_inspection_date: Mapped[str | None] = mapped_column(String(32))
    interval_months: Mapped[int | None] = mapped_column(Integer)
    reorder_point: Mapped[int | None] = mapped_column(Integer)
    is_inventory_target: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, onupdate=_jst_now)


class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id"), unique=True, nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    threshold: Mapped[int] = mapped_column(Integer, default=10)
    location: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, onupdate=_jst_now)

    item = relationship("Item", lazy="joined")


class InventoryHistory(Base):
    __tablename__ = "inventory_history"
    __table_args__ = (
        Index("idx_history_item", "item_id", "created_at"),
        Index("idx_history_status", "status"),
        Index("idx_history_change_type", "change_type"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    # IN/OUT/DISPOSE は正の数量。ADJUST/STOCKTAKE は増減つき（負もある）
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    user_name: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="CONFIRMED")
    note: Mapped[str | None] = mapped_column(Text)
    vendor_name: Mapped[str | None] = mapped_column(String(128))
    unit_price: Mapped[float | None] = mapped_column(Float)
    total_price: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[int | None] = mapped_column(Integer)
    # 由来：None=画面からの通常の入出庫, INIT=初期在庫, UNDO=取消, PT=ゲスト申請, DR=廃棄申請, PR=発注受領, ST=棚卸し
    ref_type: Mapped[str | None] = mapped_column(String(16))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, index=True)


class PendingTransaction(Base):
    __tablename__ = "pending_transactions"
    __table_args__ = (
        Index("idx_pending_status", "status"),
        Index("idx_pending_department", "department_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    guest_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)


class DisposalRequest(Base):
    __tablename__ = "disposal_requests"
    __table_args__ = (
        Index("idx_disposal_status", "status"),
        Index("idx_disposal_requester", "requester_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    __table_args__ = (
        Index("idx_pr_status", "status"),
        Index("idx_pr_requester", "requested_by_user_id"),
        Index("idx_pr_item", "item_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    requested_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="NORMAL")
    due_date: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    requested_by_department: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    admin_comment: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_qty: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, onupdate=_jst_now)


class PurchaseCandidate(Base):
    __tablename__ = "purchase_candidates"
    __table_args__ = (
        Index("idx_pc_status", "status"),
        Index("idx_pc_item", "item_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, unique=True)
    auto_reason: Mapped[str | None] = mapped_column(String(64))
    selected_for_order: Mapped[int] = mapped_column(Integer, default=0)
    deferred: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[str] = mapped_column(String(16), default="NORMAL")
    recommended_qty: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, onupdate=_jst_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)


class StocktakeSession(Base):
    __tablename__ = "stocktake_sessions"
    # 実施中（OPEN）は1つだけ（H-04）
    __table_args__ = (
        Index("uq_stocktake_one_open", "status", unique=True,
              sqlite_where=text("status = 'OPEN'"), postgresql_where=text("status = 'OPEN'")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(32))
    end_date: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN / CLOSED / CANCELLED
    note: Mapped[str | None] = mapped_column(Text)
    scope_category: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class StocktakeRecord(Base):
    __tablename__ = "stocktake_records"
    __table_args__ = (
        UniqueConstraint("session_id", "item_id", name="uq_stocktake_session_item"),
        Index("idx_st_records_session", "session_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("stocktake_sessions.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    system_qty: Mapped[int] = mapped_column(Integer, default=0)
    actual_qty: Mapped[int | None] = mapped_column(Integer)
    diff_qty: Mapped[int | None] = mapped_column(Integer)
    counted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    counted_at: Mapped[datetime | None] = mapped_column(DateTime)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING / COUNTED / APPLIED


class StocktakeTemplate(Base):
    __tablename__ = "stocktake_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_jst_now, onupdate=_jst_now)


class StocktakeTemplateMapping(Base):
    __tablename__ = "stocktake_template_mappings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("stocktake_templates.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    excel_cell: Mapped[str | None] = mapped_column(String(16))
    display_label: Mapped[str | None] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

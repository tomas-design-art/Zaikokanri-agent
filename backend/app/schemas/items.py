"""Item (物品マスター) / inventory schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OptDate, OptStr, ReqStr


class ItemFields(BaseModel):
    """作成・更新で共通の項目。空文字は None にそろえる（B-01）。"""

    item_code: OptStr = Field(default=None, max_length=64)
    vendor_name: OptStr = Field(default=None, max_length=128)
    vendor_item_code: OptStr = Field(default=None, max_length=64)
    department_tags: OptStr = None
    frequency_tag: OptStr = Field(default=None, max_length=32)
    expiry_date: OptDate = None
    owner_department_id: int | None = None
    location_text: OptStr = Field(default=None, max_length=128)
    last_inspection_date: OptDate = None
    next_inspection_date: OptDate = None
    interval_months: int | None = Field(default=None, ge=0)
    reorder_point: int | None = Field(default=None, ge=0)


class ItemCreate(ItemFields):
    item_name: ReqStr = Field(max_length=255)
    category: ReqStr = Field(max_length=64)
    unit: ReqStr = Field(default="個", max_length=16)
    unit_price: float = Field(default=0.0, ge=0, le=100_000_000, allow_inf_nan=False)
    is_asset: Literal[0, 1] = 0
    is_common: Literal[0, 1] | None = None  # 指定なし：所属部署が無ければ共通（I-01）
    is_inventory_target: Literal[0, 1] = 1
    initial_quantity: int = Field(default=0, ge=0, le=1_000_000)


class ItemUpdate(ItemFields):
    item_name: ReqStr | None = Field(default=None, max_length=255)
    category: ReqStr | None = Field(default=None, max_length=64)
    unit: ReqStr | None = Field(default=None, max_length=16)
    unit_price: float | None = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)
    is_asset: Literal[0, 1] | None = None
    is_common: Literal[0, 1] | None = None
    is_inventory_target: Literal[0, 1] | None = None
    is_active: Literal[0, 1] | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_name: str
    item_code: str | None = None
    vendor_name: str | None = None
    vendor_item_code: str | None = None
    category: str
    unit: str = "個"
    department_tags: str | None = None
    unit_price: float | None = 0.0  # ゲストには出さない（None）
    is_asset: int = 0
    frequency_tag: str | None = None
    expiry_date: str | None = None
    owner_department_id: int | None = None
    is_common: int = 0
    location_text: str | None = None
    last_inspection_date: str | None = None
    next_inspection_date: str | None = None
    interval_months: int | None = None
    reorder_point: int | None = None
    is_inventory_target: int = 1
    is_active: int


class ItemDetail(ItemOut):
    quantity: int = 0
    threshold: int = 0


class InventoryRow(BaseModel):
    item_id: int
    item_name: str
    item_code: str | None = None
    category: str
    unit: str = "個"
    vendor_name: str | None = None
    unit_price: float | None = 0.0  # ゲストには出さない（None）
    owner_department_id: int | None = None
    is_common: bool = True
    quantity: int
    threshold: int
    location: str | None = None
    expiry_date: str | None = None
    is_low_stock: bool = False
    is_expired: bool = False
    is_expiring_soon: bool = False

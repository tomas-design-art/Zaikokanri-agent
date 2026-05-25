"""Item (物品マスター) schemas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    item_code: str | None = None
    vendor_name: str | None = None
    vendor_item_code: str | None = None
    category: str
    department_tags: str | None = None
    unit_price: float = 0.0
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


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    item_name: str | None = None
    item_code: str | None = None
    vendor_name: str | None = None
    vendor_item_code: str | None = None
    category: str | None = None
    department_tags: str | None = None
    unit_price: float | None = None
    is_asset: int | None = None
    frequency_tag: str | None = None
    expiry_date: str | None = None
    is_active: int | None = None
    owner_department_id: int | None = None
    is_common: int | None = None
    location_text: str | None = None
    last_inspection_date: str | None = None
    next_inspection_date: str | None = None
    interval_months: int | None = None
    reorder_point: int | None = None
    is_inventory_target: int | None = None


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: int


class InventoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: int
    item_name: str
    item_code: str | None = None
    category: str
    vendor_name: str | None = None
    quantity: int
    threshold: int
    location: str | None = None
    expiry_date: str | None = None
    is_low_stock: bool = False
    is_expired: bool = False
    is_expiring_soon: bool = False

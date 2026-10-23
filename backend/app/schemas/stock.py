"""Schemas for stock operations."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import OptStr, ReqStr


class OutboundCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    note: OptStr = Field(default=None, max_length=512)


class OutboundBulkCreate(BaseModel):
    items: list[OutboundCreate] = Field(min_length=1, max_length=200)


class InboundCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    vendor_name: OptStr = Field(default=None, max_length=128)
    unit_price: float | None = Field(default=None, ge=0)
    note: OptStr = Field(default=None, max_length=512)


class ReceiveRequest(BaseModel):
    purchase_request_id: int
    received_qty: int = Field(ge=1)
    note: OptStr = Field(default=None, max_length=512)


class AdjustRequest(BaseModel):
    item_id: int
    new_quantity: int = Field(ge=0)
    reason: ReqStr = Field(max_length=512)


class StockResultOut(BaseModel):
    item_id: int
    item_name: str
    change: int
    new_quantity: int
    history_id: int | None = None
    # ゲストの出庫は在庫を動かさず「承認待ちの申請」になる（B-07）
    pending: bool = False
    pending_id: int | None = None

"""Schemas for stock operations."""
from __future__ import annotations

from pydantic import BaseModel, Field


class OutboundCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    note: str | None = None


class OutboundBulkItem(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    note: str | None = None


class OutboundBulkCreate(BaseModel):
    items: list[OutboundBulkItem]


class InboundCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    vendor_name: str | None = None
    unit_price: float | None = None
    note: str | None = None


class AdjustRequest(BaseModel):
    item_id: int
    new_quantity: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=512)


class StockResultOut(BaseModel):
    item_id: int
    item_name: str
    change: int
    new_quantity: int
    history_id: int


class UndoRequest(BaseModel):
    history_id: int

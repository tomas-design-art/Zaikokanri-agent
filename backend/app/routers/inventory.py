"""Inventory router — listing with KPIs, filters, pagination."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Inventory, Item
from app.schemas.common import Page
from app.schemas.items import InventoryRow

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryKPI(BaseModel):
    total_items: int
    total_quantity: int
    low_stock_count: int
    expired_count: int
    expiring_soon_count: int


def _today_iso() -> str:
    return date.today().isoformat()


def _soon_iso(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


@router.get("/kpi", response_model=InventoryKPI)
def kpi(
    db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)
) -> InventoryKPI:
    today = _today_iso()
    soon = _soon_iso(30)
    total_items = db.query(func.count(Item.id)).filter(Item.is_active == 1).scalar() or 0
    total_qty = (
        db.query(func.coalesce(func.sum(Inventory.quantity), 0))
        .join(Item, Item.id == Inventory.item_id)
        .filter(Item.is_active == 1)
        .scalar()
        or 0
    )
    low = (
        db.query(func.count(Inventory.id))
        .join(Item, Item.id == Inventory.item_id)
        .filter(Item.is_active == 1, Inventory.quantity <= Inventory.threshold)
        .scalar()
        or 0
    )
    expired = (
        db.query(func.count(Item.id))
        .filter(Item.is_active == 1, Item.expiry_date != None, Item.expiry_date < today)  # noqa: E711
        .scalar()
        or 0
    )
    expiring = (
        db.query(func.count(Item.id))
        .filter(
            Item.is_active == 1,
            Item.expiry_date != None,  # noqa: E711
            Item.expiry_date >= today,
            Item.expiry_date <= soon,
        )
        .scalar()
        or 0
    )
    return InventoryKPI(
        total_items=total_items,
        total_quantity=total_qty,
        low_stock_count=low,
        expired_count=expired,
        expiring_soon_count=expiring,
    )


@router.get("", response_model=Page[InventoryRow])
def list_inventory(
    q: str | None = None,
    category: str | None = None,
    department: str | None = None,
    only_low_stock: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Page[InventoryRow]:
    today = _today_iso()
    soon = _soon_iso(30)
    query = db.query(Item, Inventory).join(Inventory, Inventory.item_id == Item.id).filter(
        Item.is_active == 1
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Item.item_name.like(like),
                Item.item_code.like(like),
                Item.vendor_name.like(like),
                Item.vendor_item_code.like(like),
            )
        )
    if category:
        query = query.filter(Item.category == category)
    if department:
        query = query.filter(Item.department_tags.like(f"%{department}%"))
    if only_low_stock:
        query = query.filter(Inventory.quantity <= Inventory.threshold)

    total = query.count()
    rows = (
        query.order_by(Item.item_name)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    out: list[InventoryRow] = []
    for item, inv in rows:
        is_expired = bool(item.expiry_date and item.expiry_date < today)
        is_soon = bool(
            item.expiry_date and not is_expired and today <= item.expiry_date <= soon
        )
        out.append(
            InventoryRow(
                item_id=item.id,
                item_name=item.item_name,
                item_code=item.item_code,
                category=item.category,
                vendor_name=item.vendor_name,
                quantity=inv.quantity,
                threshold=inv.threshold,
                location=inv.location,
                expiry_date=item.expiry_date,
                is_low_stock=inv.quantity <= inv.threshold,
                is_expired=is_expired,
                is_expiring_soon=is_soon,
            )
        )
    return Page[InventoryRow](items=out, total=total, page=page, per_page=per_page)

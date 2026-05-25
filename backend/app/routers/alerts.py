"""Alerts router — low stock / expired / expiring soon."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Inventory, Item
from app.schemas.items import InventoryRow

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/low-stock", response_model=list[InventoryRow])
def low_stock(
    db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)
) -> list[InventoryRow]:
    rows = (
        db.query(Item, Inventory)
        .join(Inventory, Inventory.item_id == Item.id)
        .filter(Item.is_active == 1, Inventory.quantity <= Inventory.threshold)
        .order_by(Inventory.quantity)
        .all()
    )
    return [
        InventoryRow(
            item_id=i.id,
            item_name=i.item_name,
            item_code=i.item_code,
            category=i.category,
            vendor_name=i.vendor_name,
            quantity=inv.quantity,
            threshold=inv.threshold,
            location=inv.location,
            expiry_date=i.expiry_date,
            is_low_stock=True,
        )
        for i, inv in rows
    ]


@router.get("/expiring", response_model=list[InventoryRow])
def expiring(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[InventoryRow]:
    today = date.today().isoformat()
    soon = (date.today() + timedelta(days=days)).isoformat()
    rows = (
        db.query(Item, Inventory)
        .join(Inventory, Inventory.item_id == Item.id)
        .filter(
            Item.is_active == 1,
            Item.expiry_date != None,  # noqa: E711
            Item.expiry_date <= soon,
        )
        .order_by(Item.expiry_date)
        .all()
    )
    return [
        InventoryRow(
            item_id=i.id,
            item_name=i.item_name,
            item_code=i.item_code,
            category=i.category,
            vendor_name=i.vendor_name,
            quantity=inv.quantity,
            threshold=inv.threshold,
            location=inv.location,
            expiry_date=i.expiry_date,
            is_expired=bool(i.expiry_date and i.expiry_date < today),
            is_expiring_soon=bool(i.expiry_date and i.expiry_date >= today and i.expiry_date <= soon),
        )
        for i, inv in rows
    ]

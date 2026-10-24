"""Alerts router — 在庫不足 / 期限切れ / 期限間近。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Inventory, Item
from app.schemas.items import InventoryRow
from app.services.inventory_view import expiry_window, inventory_query, to_row
from app.services.scope import Scope, item_filter

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/low-stock", response_model=list[InventoryRow])
def low_stock(
    scope: Scope | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> list[InventoryRow]:
    rows = inventory_query(db, only_low_stock=True, visible=item_filter(user, scope)).order_by(Inventory.quantity, Item.item_name).all()
    return [to_row(i, inv, hide_prices=user.is_guest) for i, inv in rows]


@router.get("/expiring", response_model=list[InventoryRow])
def expiring(
    days: int = Query(30, ge=1, le=365),
    scope: Scope | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[InventoryRow]:
    _, soon = expiry_window(days)
    rows = (
        inventory_query(db, visible=item_filter(user, scope))
        .filter(Item.expiry_date.is_not(None), Item.expiry_date <= soon)
        .order_by(Item.expiry_date)
        .all()
    )
    return [to_row(i, inv, days=days, hide_prices=user.is_guest) for i, inv in rows]

"""在庫一覧・アラート・CSV で共通の「1行」の組み立て。"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models import Inventory, Item
from app.schemas.items import InventoryRow
from app.utils.datetime import jst_today
from app.utils.text import contains

DEFAULT_THRESHOLD = 10
EXPIRING_DAYS = 30


def expiry_window(days: int = EXPIRING_DAYS) -> tuple[str, str]:
    today = jst_today()
    return today.isoformat(), (today + timedelta(days=days)).isoformat()


def to_row(item: Item, inv: Inventory, *, days: int = EXPIRING_DAYS) -> InventoryRow:
    today, soon = expiry_window(days)
    expired = bool(item.expiry_date and item.expiry_date < today)
    return InventoryRow(
        item_id=item.id,
        item_name=item.item_name,
        item_code=item.item_code,
        category=item.category,
        unit=item.unit or "個",
        vendor_name=item.vendor_name,
        unit_price=item.unit_price or 0.0,
        quantity=inv.quantity,
        threshold=inv.threshold,
        location=item.location_text or inv.location,  # B-03：保管場所は物品側を正とする
        expiry_date=item.expiry_date,
        is_low_stock=inv.quantity <= inv.threshold,
        is_expired=expired,
        is_expiring_soon=bool(item.expiry_date and not expired and item.expiry_date <= soon),
    )


def search_items(query: Query, q: str | None) -> Query:
    if not q or not q.strip():
        return query
    q = q.strip()
    return query.filter(
        or_(
            contains(Item.item_name, q),
            contains(Item.item_code, q),
            contains(Item.vendor_name, q),
            contains(Item.vendor_item_code, q),
        )
    )


def inventory_query(
    db: Session,
    *,
    q: str | None = None,
    category: str | None = None,
    department: str | None = None,
    only_low_stock: bool = False,
) -> Query:
    query = db.query(Item, Inventory).join(Inventory, Inventory.item_id == Item.id).filter(Item.is_active == 1)
    query = search_items(query, q)
    if category:
        query = query.filter(Item.category == category)
    if department:
        query = query.filter(contains(Item.department_tags, department))
    if only_low_stock:
        query = query.filter(Inventory.quantity <= Inventory.threshold)
    return query


def sync_threshold(db: Session, item: Item) -> None:
    """発注点を在庫不足の判定に反映する（B-02）。"""
    inv = db.query(Inventory).filter(Inventory.item_id == item.id).first()
    if inv and item.reorder_point is not None:
        inv.threshold = item.reorder_point

"""Service layer: outbound / inbound / adjust core logic (transaction-safe)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Inventory, InventoryHistory, Item
from app.utils.datetime import jst_now


@dataclass
class StockResult:
    item_id: int
    item_name: str
    change: int
    new_quantity: int
    history_id: int


class StockError(Exception):
    pass


def _get_inventory_for_update(db: Session, item_id: int) -> tuple[Item, Inventory]:
    item = db.get(Item, item_id)
    if not item or not item.is_active:
        raise StockError("対象の物品が見つかりません")
    inv = db.query(Inventory).filter(Inventory.item_id == item_id).with_for_update().first()
    if not inv:
        # Auto-create if missing
        inv = Inventory(item_id=item_id, quantity=0, threshold=10)
        db.add(inv)
        db.flush()
    return item, inv


def process_outbound(
    db: Session,
    *,
    item_id: int,
    quantity: int,
    user_name: str,
    department: str | None,
    note: str | None = None,
    status: str = "CONFIRMED",
) -> StockResult:
    if quantity <= 0 or quantity > settings.outbound_max:
        raise StockError(f"数量は 1〜{settings.outbound_max} の範囲で指定してください")
    item, inv = _get_inventory_for_update(db, item_id)
    if inv.quantity < quantity:
        raise StockError(f"在庫不足: 現在庫 {inv.quantity}, 出庫 {quantity}")
    inv.quantity -= quantity
    inv.updated_at = jst_now()
    hist = InventoryHistory(
        item_id=item_id,
        change_type="OUT",
        quantity=quantity,
        user_name=user_name,
        department=department,
        status=status,
        note=note,
        created_at=jst_now(),
    )
    db.add(hist)
    db.flush()
    return StockResult(item.id, item.item_name, -quantity, inv.quantity, hist.id)


def process_inbound(
    db: Session,
    *,
    item_id: int,
    quantity: int,
    user_name: str,
    department: str | None,
    vendor_name: str | None = None,
    unit_price: float | None = None,
    note: str | None = None,
) -> StockResult:
    if quantity <= 0 or quantity > settings.inbound_max:
        raise StockError(f"数量は 1〜{settings.inbound_max} の範囲で指定してください")
    item, inv = _get_inventory_for_update(db, item_id)
    inv.quantity += quantity
    inv.updated_at = jst_now()
    total = (unit_price or 0) * quantity if unit_price else None
    hist = InventoryHistory(
        item_id=item_id,
        change_type="IN",
        quantity=quantity,
        user_name=user_name,
        department=department,
        status="CONFIRMED",
        note=note,
        vendor_name=vendor_name,
        unit_price=unit_price,
        total_price=total,
        created_at=jst_now(),
    )
    db.add(hist)
    db.flush()
    return StockResult(item.id, item.item_name, quantity, inv.quantity, hist.id)


def process_dispose(
    db: Session,
    *,
    item_id: int,
    quantity: int,
    user_name: str,
    department: str | None,
    reason: str,
) -> StockResult:
    if quantity <= 0:
        raise StockError("数量は1以上を指定してください")
    item, inv = _get_inventory_for_update(db, item_id)
    if inv.quantity < quantity:
        raise StockError(f"在庫不足: 現在庫 {inv.quantity}, 廃棄 {quantity}")
    inv.quantity -= quantity
    inv.updated_at = jst_now()
    hist = InventoryHistory(
        item_id=item_id,
        change_type="DISPOSE",
        quantity=quantity,
        user_name=user_name,
        department=department,
        status="CONFIRMED",
        note=reason,
        created_at=jst_now(),
    )
    db.add(hist)
    db.flush()
    return StockResult(item.id, item.item_name, -quantity, inv.quantity, hist.id)


def process_adjust(
    db: Session,
    *,
    item_id: int,
    new_quantity: int,
    user_name: str,
    department: str | None,
    reason: str,
) -> StockResult:
    if new_quantity < 0:
        raise StockError("新数量は0以上で指定してください")
    item, inv = _get_inventory_for_update(db, item_id)
    diff = new_quantity - inv.quantity
    inv.quantity = new_quantity
    inv.updated_at = jst_now()
    change_type = "IN" if diff >= 0 else "OUT"
    hist = InventoryHistory(
        item_id=item_id,
        change_type=change_type,
        quantity=abs(diff),
        user_name=user_name,
        department=department,
        status="CONFIRMED",
        note=f"[調整] {reason}",
        created_at=jst_now(),
    )
    db.add(hist)
    db.flush()
    return StockResult(item.id, item.item_name, diff, inv.quantity, hist.id)


def process_undo(db: Session, *, history_id: int, user_name: str) -> StockResult:
    """Undo within UNDO_MINUTES — reverts the stock change."""
    h = db.get(InventoryHistory, history_id)
    if not h:
        raise StockError("履歴が見つかりません")
    if h.status != "CONFIRMED":
        raise StockError("確定済み履歴のみ取消可能です")
    if h.change_type not in {"IN", "OUT"}:
        raise StockError("入出庫履歴のみ取消可能です")
    age = jst_now() - h.created_at
    if age > timedelta(minutes=settings.undo_minutes):
        raise StockError(f"取消可能時間({settings.undo_minutes}分)を超過しています")

    item, inv = _get_inventory_for_update(db, h.item_id)
    if h.change_type == "IN":
        if inv.quantity < h.quantity:
            raise StockError("入庫取消に必要な在庫がありません")
        inv.quantity -= h.quantity
        reverse_type = "OUT"
    else:
        inv.quantity += h.quantity
        reverse_type = "IN"
    inv.updated_at = jst_now()
    h.status = "REJECTED"
    new_h = InventoryHistory(
        item_id=h.item_id,
        change_type=reverse_type,
        quantity=h.quantity,
        user_name=user_name,
        department=h.department,
        status="CONFIRMED",
        note=f"[取消] history_id={h.id}",
        created_at=jst_now(),
    )
    db.add(new_h)
    db.flush()
    return StockResult(item.id, item.item_name, -h.quantity if h.change_type == "IN" else h.quantity, inv.quantity, new_h.id)

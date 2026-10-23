"""在庫を動かす処理はすべてここを通す（履歴の記録と在庫の増減を同じトランザクションで行う）。

呼び出し側は成功したら commit、StockError なら rollback する。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Inventory, InventoryHistory, Item
from app.utils.datetime import jst_now

DEFAULT_THRESHOLD = 10
# 取消できる由来（None＝画面からの通常の入出庫）。申請・受領・棚卸し等は元の処理側で直す（B-10）
UNDOABLE_REF_TYPES = {None}


@dataclass(frozen=True, slots=True)
class Actor:
    """操作した人。履歴の担当者・部署・操作者IDに使う。"""

    user_id: int | None
    name: str
    department: str | None


@dataclass
class StockResult:
    item_id: int
    item_name: str
    change: int
    new_quantity: int
    history_id: int


class StockError(Exception):
    """利用者に見せてよい在庫処理のエラー（日本語のメッセージ）。"""


def lock_inventory(db: Session, item_id: int) -> tuple[Item, Inventory]:
    item = db.get(Item, item_id)
    if not item or not item.is_active:
        raise StockError("対象の物品が見つからないか、無効になっています")
    # Inventory は物品を外部結合で読み込むため、ロックは在庫の表だけにかける
    # （PostgreSQL は外部結合の NULL 側に FOR UPDATE を付けられない）
    inv = db.query(Inventory).filter(Inventory.item_id == item_id).with_for_update(of=Inventory).first()
    if not inv:
        inv = Inventory(item_id=item_id, quantity=0, threshold=item.reorder_point or DEFAULT_THRESHOLD)
        db.add(inv)
        db.flush()
    return item, inv


def _record(
    db: Session,
    inv: Inventory,
    item: Item,
    actor: Actor,
    *,
    change_type: str,
    signed_change: int,
    history_qty: int,
    note: str | None = None,
    ref: tuple[str, int | None] | None = None,
    vendor_name: str | None = None,
    unit_price: float | None = None,
) -> StockResult:
    inv.quantity += signed_change
    inv.updated_at = jst_now()
    hist = InventoryHistory(
        item_id=item.id,
        change_type=change_type,
        quantity=history_qty,
        user_name=actor.name,
        department=actor.department,
        status="CONFIRMED",
        note=note,
        vendor_name=vendor_name,
        unit_price=unit_price,
        total_price=unit_price * history_qty if unit_price is not None else None,
        created_by=actor.user_id,
        ref_type=ref[0] if ref else None,
        ref_id=ref[1] if ref else None,
        created_at=jst_now(),
    )
    db.add(hist)
    db.flush()
    return StockResult(item.id, item.item_name, signed_change, inv.quantity, hist.id)


def check_outbound(item: Item, inv: Inventory, quantity: int, verb: str = "出庫") -> None:
    if quantity <= 0 or quantity > settings.outbound_max:
        raise StockError(f"数量は 1〜{settings.outbound_max} の範囲で指定してください")
    if inv.quantity < quantity:
        raise StockError(f"「{item.item_name}」の在庫が足りません（現在庫 {inv.quantity}、{verb} {quantity}）")


def process_outbound(
    db: Session, actor: Actor, *, item_id: int, quantity: int, note: str | None = None,
    ref: tuple[str, int | None] | None = None,
) -> StockResult:
    item, inv = lock_inventory(db, item_id)
    check_outbound(item, inv, quantity)
    return _record(db, inv, item, actor, change_type="OUT", signed_change=-quantity, history_qty=quantity, note=note, ref=ref)


def process_inbound(
    db: Session, actor: Actor, *, item_id: int, quantity: int, vendor_name: str | None = None,
    unit_price: float | None = None, note: str | None = None, ref: tuple[str, int | None] | None = None,
) -> StockResult:
    if quantity <= 0 or quantity > settings.inbound_max:
        raise StockError(f"数量は 1〜{settings.inbound_max} の範囲で指定してください")
    item, inv = lock_inventory(db, item_id)
    return _record(
        db, inv, item, actor, change_type="IN", signed_change=quantity, history_qty=quantity, note=note, ref=ref,
        vendor_name=vendor_name, unit_price=unit_price,
    )


def process_dispose(
    db: Session, actor: Actor, *, item_id: int, quantity: int, reason: str, ref: tuple[str, int | None] | None = None,
) -> StockResult:
    item, inv = lock_inventory(db, item_id)
    check_outbound(item, inv, quantity, verb="廃棄")
    return _record(db, inv, item, actor, change_type="DISPOSE", signed_change=-quantity, history_qty=quantity, note=reason, ref=ref)


def process_adjust(db: Session, actor: Actor, *, item_id: int, new_quantity: int, reason: str) -> StockResult:
    """在庫数を直接直す。履歴は ADJUST（増減つき）で、出庫統計には入らない（B-12）。"""
    if new_quantity < 0:
        raise StockError("新しい数量は0以上で指定してください")
    item, inv = lock_inventory(db, item_id)
    diff = new_quantity - inv.quantity
    if diff == 0:
        raise StockError("現在の在庫数と同じです。変更はありません")
    return _record(db, inv, item, actor, change_type="ADJUST", signed_change=diff, history_qty=diff, note=reason)


def apply_stocktake_diff(db: Session, actor: Actor, *, item_id: int, diff: int, session_id: int, note: str) -> StockResult | None:
    """棚卸しの差異を今の在庫に足す（D-02）。在庫は0未満にしない。"""
    item, inv = lock_inventory(db, item_id)
    delta = max(diff, -inv.quantity)
    if delta == 0:
        return None
    return _record(
        db, inv, item, actor, change_type="STOCKTAKE", signed_change=delta, history_qty=delta, note=note,
        ref=("ST", session_id),
    )


def record_initial_stock(db: Session, actor: Actor, item: Item, inv: Inventory, quantity: int) -> None:
    if quantity > 0:
        _record(db, inv, item, actor, change_type="IN", signed_change=quantity, history_qty=quantity,
                note="初期在庫", ref=("INIT", None))


def undo_problem(h: InventoryHistory, *, user_id: int, is_admin: bool) -> str | None:
    """取消できない理由（取消できるなら None）。画面の「取消」ボタンの表示にも使う（B-10 / B-11）。"""
    if h.change_type not in {"IN", "OUT"} or h.ref_type not in UNDOABLE_REF_TYPES:
        return "通常の入庫・出庫だけ取り消せます"
    if h.status != "CONFIRMED":
        return "この履歴はすでに取り消されています"
    if not is_admin and h.created_by != user_id:
        return "本人の操作だけ取り消せます"
    if jst_now() - h.created_at > timedelta(minutes=settings.undo_minutes):
        return f"取り消せるのは操作から{settings.undo_minutes}分以内です"
    return None


def process_undo(db: Session, actor: Actor, h: InventoryHistory) -> StockResult:
    item, inv = lock_inventory(db, h.item_id)
    if h.change_type == "IN":
        if inv.quantity < h.quantity:
            raise StockError("取り消すと在庫がマイナスになるため取り消せません")
        signed, reverse = -h.quantity, "OUT"
    else:
        signed, reverse = h.quantity, "IN"
    h.status = "REJECTED"
    return _record(
        db, inv, item, actor, change_type=reverse, signed_change=signed, history_qty=h.quantity,
        note=f"取消（履歴 #{h.id}）", ref=("UNDO", h.id),
    )


def actor_of(user) -> Actor:  # noqa: ANN001 (CurrentUser)
    return Actor(user_id=user.id, name=user.display_name, department=user.department)

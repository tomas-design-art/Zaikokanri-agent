"""Outbound (出庫) router. GUEST → 承認待ちの申請, USER/ADMIN → 即時に在庫から引く。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Inventory, Item, PendingTransaction
from app.schemas.stock import OutboundBulkCreate, OutboundCreate, StockResultOut
from app.services.stock_service import StockError, actor_of, check_outbound, lock_inventory, process_outbound
from app.utils.datetime import jst_now

router = APIRouter(prefix="/outbound", tags=["outbound"])


def _request_as_guest(db: Session, user: CurrentUser, line: OutboundCreate) -> StockResultOut:
    """ゲストの出庫は申請として登録する。在庫と上限は申請の時点でも確かめる（B-08）。"""
    if user.department_id is None:
        raise StockError("部署が設定されていないため申請できません。管理者に部署の設定を依頼してください")
    item, inv = lock_inventory(db, line.item_id)
    check_outbound(item, inv, line.quantity)
    pt = PendingTransaction(
        change_type="OUT",
        item_id=item.id,
        quantity=line.quantity,
        actor_name=user.display_name,
        note=line.note,
        guest_user_id=user.id,
        department_id=user.department_id,
        status="PENDING",
        created_at=jst_now(),
    )
    db.add(pt)
    db.flush()
    return StockResultOut(item_id=item.id, item_name=item.item_name, change=0, new_quantity=inv.quantity,
                          pending=True, pending_id=pt.id)


def _process(db: Session, user: CurrentUser, lines: list[OutboundCreate]) -> list[StockResultOut]:
    results = []
    try:
        for line in lines:
            if user.is_guest:
                results.append(_request_as_guest(db, user, line))
            else:
                r = process_outbound(db, actor_of(user), item_id=line.item_id, quantity=line.quantity, note=line.note)
                results.append(StockResultOut(**r.__dict__))
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return results


@router.post("", response_model=StockResultOut, status_code=201)
def create_outbound(
    body: OutboundCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> StockResultOut:
    return _process(db, user, [body])[0]


@router.post("/bulk", response_model=list[StockResultOut], status_code=201)
def bulk_outbound(
    body: OutboundBulkCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> list[StockResultOut]:
    """まとめて出庫。1件でも失敗したら全件取りやめ（B-14）。"""
    return _process(db, user, body.items)


class MyRequestOut(BaseModel):
    id: int
    item_id: int
    item_name: str
    quantity: int
    current_stock: int
    note: str | None
    status: str
    reject_reason: str | None
    created_at: str
    decided_at: str | None


@router.get("/my-requests", response_model=list[MyRequestOut])
def my_requests(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> list[MyRequestOut]:
    """自分の出庫申請と結果（B-09）。"""
    rows = (
        db.query(PendingTransaction, Item.item_name, Inventory.quantity)
        .join(Item, Item.id == PendingTransaction.item_id)
        .outerjoin(Inventory, Inventory.item_id == PendingTransaction.item_id)
        .filter(PendingTransaction.guest_user_id == user.id)
        .order_by(PendingTransaction.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        MyRequestOut(
            id=p.id, item_id=p.item_id, item_name=name, quantity=p.quantity, current_stock=stock or 0,
            note=p.note, status=p.status, reject_reason=p.reject_reason,
            created_at=p.created_at.isoformat() if p.created_at else "",
            decided_at=p.approved_at.isoformat() if p.approved_at else None,
        )
        for p, name, stock in rows
    ]

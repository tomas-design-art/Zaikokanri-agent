"""Outbound (出庫) router. GUEST → pending, USER/ADMIN → immediate."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Inventory, Item, PendingTransaction
from app.schemas.stock import (
    OutboundBulkCreate,
    OutboundCreate,
    StockResultOut,
    UndoRequest,
)
from app.services.stock_service import StockError, process_outbound, process_undo
from app.utils.datetime import jst_now

router = APIRouter(prefix="/outbound", tags=["outbound"])


@router.post("", response_model=StockResultOut, status_code=201)
def create_outbound(
    body: OutboundCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> StockResultOut:
    if user.is_guest:
        # Pending approval flow
        item = db.get(Item, body.item_id)
        if not item:
            raise HTTPException(404, "対象の物品が見つかりません")
        if user.department_id is None:
            raise HTTPException(400, "部署が未設定のユーザーは申請できません")
        pt = PendingTransaction(
            change_type="OUT",
            item_id=body.item_id,
            quantity=body.quantity,
            actor_name=user.display_name,
            note=body.note,
            guest_user_id=user.id,
            department_id=user.department_id,
            status="PENDING",
            created_at=jst_now(),
        )
        db.add(pt)
        db.commit()
        inv = db.query(Inventory).filter(Inventory.item_id == body.item_id).first()
        return StockResultOut(
            item_id=item.id,
            item_name=item.item_name,
            change=0,
            new_quantity=inv.quantity if inv else 0,
            history_id=pt.id,
        )
    try:
        result = process_outbound(
            db,
            item_id=body.item_id,
            quantity=body.quantity,
            user_name=user.display_name,
            department=user.department,
            note=body.note,
        )
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return StockResultOut(**result.__dict__)


@router.post("/bulk", response_model=list[StockResultOut])
def bulk_outbound(
    body: OutboundBulkCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[StockResultOut]:
    if user.is_guest:
        raise HTTPException(403, "ゲストは一括出庫を利用できません")
    results = []
    try:
        for it in body.items:
            r = process_outbound(
                db,
                item_id=it.item_id,
                quantity=it.quantity,
                user_name=user.display_name,
                department=user.department,
                note=it.note,
            )
            results.append(StockResultOut(**r.__dict__))
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return results


@router.post("/undo", response_model=StockResultOut)
def undo_outbound(
    body: UndoRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> StockResultOut:
    try:
        r = process_undo(db, history_id=body.history_id, user_name=user.display_name)
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return StockResultOut(**r.__dict__)

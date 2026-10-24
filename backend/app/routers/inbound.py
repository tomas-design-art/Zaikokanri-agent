"""Inbound (入庫) router. 通常の入庫 + 発注品の受領（C-05）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, update
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_user
from app.db import get_db
from app.models import PurchaseRequest
from app.schemas.stock import InboundCreate, ReceiveRequest, StockResultOut
from app.services.stock_service import StockError, actor_of, process_inbound
from app.utils.datetime import jst_now

router = APIRouter(prefix="/inbound", tags=["inbound"])


@router.post("", response_model=StockResultOut, status_code=201)
def create_inbound(body: InboundCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> StockResultOut:
    try:
        r = process_inbound(
            db, actor_of(user), item_id=body.item_id, quantity=body.quantity,
            vendor_name=body.vendor_name, unit_price=body.unit_price, note=body.note,
        )
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return StockResultOut(**r.__dict__)


@router.post("/receive", response_model=StockResultOut)
def receive_purchase(body: ReceiveRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> StockResultOut:
    """承認済・発注済の申請の品物が届いたときの入庫。残数までしか受け取れない。"""
    pr = (
        db.query(PurchaseRequest)
        .filter(PurchaseRequest.id == body.purchase_request_id, PurchaseRequest.deleted_at.is_(None))
        .with_for_update()
        .first()
    )
    if not pr:
        raise HTTPException(404, "発注申請が見つかりません")
    if pr.status not in {"APPROVED", "ORDERED"}:
        raise HTTPException(400, "承認済・発注済の申請だけ受領できます")
    remaining = pr.requested_qty - (pr.received_qty or 0)
    if body.received_qty > remaining:
        raise HTTPException(400, f"受領数が残数（{remaining}）を超えています。追加分は通常の入庫で登録してください")
    try:
        note = f"発注受領（申請 #{pr.id}）" + (f" {body.note}" if body.note else "")
        r = process_inbound(db, actor_of(user), item_id=pr.item_id, quantity=body.received_qty, note=note, ref=("PR", pr.id))
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    # 残数を超えないときだけ受領数を足す（同時の受領で残数を超えない：H-01）
    new_received = func.coalesce(PurchaseRequest.received_qty, 0) + body.received_qty
    res = db.execute(
        update(PurchaseRequest)
        .where(PurchaseRequest.id == pr.id, PurchaseRequest.status.in_(("APPROVED", "ORDERED")),
               new_received <= PurchaseRequest.requested_qty)
        .values(received_qty=new_received, received_at=jst_now(),
                status=case((new_received >= PurchaseRequest.requested_qty, "RECEIVED"), else_="ORDERED"))
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "ほかの人が先に受領しました。画面を更新してください")
    db.commit()
    return StockResultOut(**r.__dict__)

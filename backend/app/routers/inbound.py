"""Inbound (入庫) router. Normal + receive-via-purchase-request."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_user
from app.db import get_db
from app.models import PurchaseRequest
from app.schemas.stock import InboundCreate, StockResultOut
from app.services.stock_service import StockError, process_inbound
from app.utils.datetime import jst_now

router = APIRouter(prefix="/inbound", tags=["inbound"])


@router.post("", response_model=StockResultOut, status_code=201)
def create_inbound(
    body: InboundCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_user),
) -> StockResultOut:
    try:
        r = process_inbound(
            db,
            item_id=body.item_id,
            quantity=body.quantity,
            user_name=user.display_name,
            department=user.department,
            vendor_name=body.vendor_name,
            unit_price=body.unit_price,
            note=body.note,
        )
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return StockResultOut(**r.__dict__)


class ReceiveRequest(BaseModel):
    purchase_request_id: int
    received_qty: int = Field(ge=1)
    note: str | None = None


@router.post("/receive", response_model=StockResultOut)
def receive_purchase(
    body: ReceiveRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_user),
) -> StockResultOut:
    pr = db.get(PurchaseRequest, body.purchase_request_id)
    if not pr:
        raise HTTPException(404, "発注申請が見つかりません")
    if pr.status not in {"APPROVED", "ORDERED"}:
        raise HTTPException(400, "承認済みの発注申請のみ受領できます")
    try:
        r = process_inbound(
            db,
            item_id=pr.item_id,
            quantity=body.received_qty,
            user_name=user.display_name,
            department=user.department,
            note=f"[発注受領] PR#{pr.id} {body.note or ''}",
        )
        pr.received_qty = (pr.received_qty or 0) + body.received_qty
        pr.received_at = jst_now()
        pr.status = "ORDERED"
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return StockResultOut(**r.__dict__)

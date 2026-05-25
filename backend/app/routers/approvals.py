"""Approvals (ゲスト出庫承認) router — ADMIN approves PendingTransactions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_admin
from app.db import get_db
from app.models import Inventory, Item, PendingTransaction
from app.schemas.common import Page
from app.services.stock_service import StockError, process_outbound
from app.utils.datetime import jst_now

router = APIRouter(prefix="/approvals", tags=["approvals"])


class PendingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    change_type: str
    item_id: int
    item_name: str
    quantity: int
    current_stock: int
    actor_name: str
    note: str | None
    department_id: int
    status: str
    reject_reason: str | None
    created_at: str


class ApproveRequest(BaseModel):
    approve: bool
    reject_reason: str | None = None


@router.get("", response_model=Page[PendingOut])
def list_pending(
    status: str | None = "PENDING",
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
) -> Page[PendingOut]:
    q = db.query(PendingTransaction, Item.item_name, Inventory.quantity).join(
        Item, Item.id == PendingTransaction.item_id
    ).outerjoin(Inventory, Inventory.item_id == PendingTransaction.item_id)
    if status:
        q = q.filter(PendingTransaction.status == status)
    total = q.count()
    rows = (
        q.order_by(PendingTransaction.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    items = [
        PendingOut(
            id=p.id,
            change_type=p.change_type,
            item_id=p.item_id,
            item_name=name,
            quantity=p.quantity,
            current_stock=stock or 0,
            actor_name=p.actor_name,
            note=p.note,
            department_id=p.department_id,
            status=p.status,
            reject_reason=p.reject_reason,
            created_at=p.created_at.isoformat() if p.created_at else "",
        )
        for p, name, stock in rows
    ]
    return Page[PendingOut](items=items, total=total, page=page, per_page=per_page)


@router.post("/{pid}/decide", response_model=PendingOut)
def decide(
    pid: int,
    body: ApproveRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
) -> PendingOut:
    p = db.get(PendingTransaction, pid)
    if not p:
        raise HTTPException(404, "Not found")
    if p.status != "PENDING":
        raise HTTPException(400, "保留中のみ処理可能")
    if body.approve:
        try:
            process_outbound(
                db,
                item_id=p.item_id,
                quantity=p.quantity,
                user_name=p.actor_name,
                department=None,
                note=f"[承認済ゲスト出庫] PT#{p.id} {p.note or ''}",
            )
        except StockError as e:
            db.rollback()
            raise HTTPException(400, str(e)) from e
        p.status = "APPROVED"
    else:
        p.status = "REJECTED"
        p.reject_reason = body.reject_reason
    p.approved_by = user.id
    p.approved_at = jst_now()
    db.commit()
    item = db.get(Item, p.item_id)
    inv = db.query(Inventory).filter(Inventory.item_id == p.item_id).first()
    return PendingOut(
        id=p.id,
        change_type=p.change_type,
        item_id=p.item_id,
        item_name=item.item_name if item else "",
        quantity=p.quantity,
        current_stock=inv.quantity if inv else 0,
        actor_name=p.actor_name,
        note=p.note,
        department_id=p.department_id,
        status=p.status,
        reject_reason=p.reject_reason,
        created_at=p.created_at.isoformat() if p.created_at else "",
    )

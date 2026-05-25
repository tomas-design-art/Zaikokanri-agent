"""Disposal requests (廃棄申請) router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.models import DisposalRequest, Item, User
from app.schemas.common import Page
from app.services.stock_service import StockError, process_dispose
from app.utils.datetime import jst_now

router = APIRouter(prefix="/disposal-requests", tags=["disposal-requests"])


class DRCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=512)


class DRApprove(BaseModel):
    approve: bool
    reject_reason: str | None = None


class DROut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    item_name: str
    quantity: int
    reason: str
    requester: str
    status: str
    reject_reason: str | None
    created_at: str


@router.get("", response_model=Page[DROut])
def list_dr(
    status: str | None = None,
    mine: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Page[DROut]:
    q = db.query(DisposalRequest, Item.item_name, User.display_name).join(
        Item, Item.id == DisposalRequest.item_id
    ).join(User, User.id == DisposalRequest.requester_id)
    if status:
        q = q.filter(DisposalRequest.status == status)
    if mine:
        q = q.filter(DisposalRequest.requester_id == user.id)
    total = q.count()
    rows = (
        q.order_by(DisposalRequest.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    items = [
        DROut(
            id=d.id,
            item_id=d.item_id,
            item_name=name,
            quantity=d.quantity,
            reason=d.reason,
            requester=who,
            status=d.status,
            reject_reason=d.reject_reason,
            created_at=d.created_at.isoformat() if d.created_at else "",
        )
        for d, name, who in rows
    ]
    return Page[DROut](items=items, total=total, page=page, per_page=per_page)


@router.post("", response_model=DROut, status_code=201)
def create_dr(
    body: DRCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> DROut:
    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    d = DisposalRequest(
        item_id=body.item_id,
        quantity=body.quantity,
        reason=body.reason,
        requester_id=user.id,
        status="PENDING",
        created_at=jst_now(),
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return DROut(
        id=d.id,
        item_id=d.item_id,
        item_name=item.item_name,
        quantity=d.quantity,
        reason=d.reason,
        requester=user.display_name,
        status=d.status,
        reject_reason=None,
        created_at=d.created_at.isoformat(),
    )


@router.post("/{dr_id}/approve", response_model=DROut)
def approve_dr(
    dr_id: int,
    body: DRApprove,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
) -> DROut:
    d = db.get(DisposalRequest, dr_id)
    if not d:
        raise HTTPException(404, "Not found")
    if d.status != "PENDING":
        raise HTTPException(400, "保留中のみ処理可能")
    if body.approve:
        try:
            process_dispose(
                db,
                item_id=d.item_id,
                quantity=d.quantity,
                user_name=user.display_name,
                department=user.department,
                reason=f"[廃棄承認] DR#{d.id} {d.reason}",
            )
        except StockError as e:
            db.rollback()
            raise HTTPException(400, str(e)) from e
        d.status = "APPROVED"
    else:
        d.status = "REJECTED"
        d.reject_reason = body.reject_reason
    d.approved_by = user.id
    d.approved_at = jst_now()
    db.commit()
    item = db.get(Item, d.item_id)
    requester = db.get(User, d.requester_id)
    return DROut(
        id=d.id,
        item_id=d.item_id,
        item_name=item.item_name if item else "",
        quantity=d.quantity,
        reason=d.reason,
        requester=requester.display_name if requester else "",
        status=d.status,
        reject_reason=d.reject_reason,
        created_at=d.created_at.isoformat() if d.created_at else "",
    )

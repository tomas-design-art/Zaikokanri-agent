"""Disposal requests (廃棄申請) router（C-01 / C-03）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.models import DisposalRequest, Item, User
from app.schemas.common import OptStr, Page, ReqStr
from app.services.stock_service import StockError, actor_of, check_outbound, lock_inventory, process_dispose
from app.services.workflow import claim, require_reason
from app.utils.datetime import jst_now

router = APIRouter(prefix="/disposal-requests", tags=["disposal-requests"])


class DRCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    reason: ReqStr = Field(max_length=512)


class DRApprove(BaseModel):
    approve: bool
    reject_reason: OptStr = None


class DROut(BaseModel):
    id: int
    item_id: int
    item_name: str
    unit: str
    quantity: int
    reason: str
    requester: str
    requester_id: int
    status: str
    reject_reason: str | None
    created_at: str


def _rows(db: Session):
    return (
        db.query(DisposalRequest, Item.item_name, Item.unit, User.display_name)
        .join(Item, Item.id == DisposalRequest.item_id)
        .join(User, User.id == DisposalRequest.requester_id)
    )


def _out(row) -> DROut:  # noqa: ANN001
    d, name, unit, who = row
    return DROut(
        id=d.id, item_id=d.item_id, item_name=name, unit=unit or "個", quantity=d.quantity, reason=d.reason,
        requester=who, requester_id=d.requester_id, status=d.status, reject_reason=d.reject_reason,
        created_at=d.created_at.isoformat(timespec="seconds") if d.created_at else "",
    )


@router.get("", response_model=Page[DROut])
def list_dr(
    status: str | None = None,
    mine: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Page[DROut]:
    q = _rows(db)
    if status:
        q = q.filter(DisposalRequest.status == status)
    if mine:
        q = q.filter(DisposalRequest.requester_id == user.id)
    total = q.count()
    rows = q.order_by(DisposalRequest.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return Page[DROut](items=[_out(r) for r in rows], total=total, page=page, per_page=per_page)


@router.post("", response_model=DROut, status_code=201)
def create_dr(body: DRCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> DROut:
    try:
        item, inv = lock_inventory(db, body.item_id)
        check_outbound(item, inv, body.quantity, verb="廃棄")
    except StockError as e:
        raise HTTPException(400, str(e)) from e
    d = DisposalRequest(
        item_id=body.item_id, quantity=body.quantity, reason=body.reason, requester_id=user.id,
        status="PENDING", created_at=jst_now(),
    )
    db.add(d)
    db.commit()
    return _out(_rows(db).filter(DisposalRequest.id == d.id).one())


@router.delete("/{dr_id}", status_code=204)
def cancel_dr(dr_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    """申請者本人（または管理者）が保留中の申請を取り下げる。"""
    d = db.get(DisposalRequest, dr_id)
    if not d:
        raise HTTPException(404, "申請が見つかりません")
    if d.requester_id != user.id and not user.is_admin:
        raise HTTPException(403, "本人の申請だけ取り下げられます")
    claim(db, DisposalRequest, dr_id, to_status="CANCELLED")
    db.commit()


@router.post("/{dr_id}/approve", response_model=DROut)
def approve_dr(dr_id: int, body: DRApprove, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)) -> DROut:
    d = db.get(DisposalRequest, dr_id)
    if not d:
        raise HTTPException(404, "申請が見つかりません")
    require_reason(body.approve, body.reject_reason)
    claim(db, DisposalRequest, dr_id, to_status="APPROVED" if body.approve else "REJECTED")
    if body.approve:
        try:
            process_dispose(db, actor_of(user), item_id=d.item_id, quantity=d.quantity,
                            reason=f"廃棄申請 #{d.id}：{d.reason}", ref=("DR", d.id))
        except StockError as e:
            db.rollback()
            raise HTTPException(400, str(e)) from e
    else:
        d.reject_reason = body.reject_reason
    d.approved_by = user.id
    d.approved_at = jst_now()
    db.commit()
    return _out(_rows(db).filter(DisposalRequest.id == dr_id).one())

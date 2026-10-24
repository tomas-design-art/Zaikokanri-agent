"""Approvals (ゲスト出庫承認) router — ADMIN が PendingTransaction を承認・却下する。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_admin
from app.db import get_db
from app.models import Department, Inventory, Item, PendingTransaction
from app.schemas.common import OptStr, Page
from app.services.stock_service import Actor, StockError, process_outbound
from app.services.workflow import claim, require_reason
from app.utils.datetime import jst_now

router = APIRouter(prefix="/approvals", tags=["approvals"])


class PendingOut(BaseModel):
    id: int
    change_type: str
    item_id: int
    item_name: str
    unit: str
    quantity: int
    current_stock: int
    actor_name: str
    note: str | None
    department_id: int
    department: str | None
    status: str
    reject_reason: str | None
    created_at: str


class ApproveRequest(BaseModel):
    approve: bool
    reject_reason: OptStr = None


def _rows(db: Session):
    return (
        db.query(PendingTransaction, Item.item_name, Item.unit, Inventory.quantity, Department.name)
        .join(Item, Item.id == PendingTransaction.item_id)
        .outerjoin(Inventory, Inventory.item_id == PendingTransaction.item_id)
        .outerjoin(Department, Department.id == PendingTransaction.department_id)
    )


def _out(row) -> PendingOut:  # noqa: ANN001
    p, name, unit, stock, dept = row
    return PendingOut(
        id=p.id, change_type=p.change_type, item_id=p.item_id, item_name=name, unit=unit or "個",
        quantity=p.quantity, current_stock=stock or 0, actor_name=p.actor_name, note=p.note,
        department_id=p.department_id, department=dept, status=p.status, reject_reason=p.reject_reason,
        created_at=p.created_at.isoformat(timespec="seconds") if p.created_at else "",
    )


@router.get("", response_model=Page[PendingOut])
def list_pending(
    status: str | None = "PENDING",
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
) -> Page[PendingOut]:
    q = _rows(db)
    if status:
        q = q.filter(PendingTransaction.status == status)
    total = q.count()
    rows = q.order_by(PendingTransaction.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return Page[PendingOut](items=[_out(r) for r in rows], total=total, page=page, per_page=per_page)


@router.post("/{pid}/decide", response_model=PendingOut)
def decide(
    pid: int, body: ApproveRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)
) -> PendingOut:
    p = db.get(PendingTransaction, pid)
    if not p:
        raise HTTPException(404, "申請が見つかりません")
    require_reason(body.approve, body.reject_reason)
    claim(db, PendingTransaction, pid, to_status="APPROVED" if body.approve else "REJECTED")
    if body.approve:
        dept = db.get(Department, p.department_id)
        # 履歴の担当者は申請したゲスト、部署はゲストの部署（B-08）
        actor = Actor(user_id=p.guest_user_id, name=p.actor_name, department=dept.name if dept else None)
        note = f"ゲスト出庫申請 #{p.id}（承認：{user.display_name}）" + (f" {p.note}" if p.note else "")
        try:
            process_outbound(db, actor, item_id=p.item_id, quantity=p.quantity, note=note, ref=("PT", p.id))
        except StockError as e:
            db.rollback()
            raise HTTPException(400, str(e)) from e
    else:
        p.reject_reason = body.reject_reason
    p.approved_by = user.id
    p.approved_at = jst_now()
    db.commit()
    return _out(_rows(db).filter(PendingTransaction.id == pid).one())

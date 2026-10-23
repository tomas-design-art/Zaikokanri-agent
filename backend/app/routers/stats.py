"""Stats router — 月別・出庫ランキング・部署別・処理待ち件数（E-01 / C-09）。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_user
from app.db import get_db
from app.models import DisposalRequest, InventoryHistory, Item, PendingTransaction, PurchaseRequest
from app.utils.datetime import day_range, jst_today, month_start

router = APIRouter(prefix="/stats", tags=["stats"])

# 利用の実態を表す区分だけを集計する（調整・棚卸し・取消の打ち消しは含めない）
USAGE_TYPES = ("IN", "OUT", "DISPOSE")


def _usage(query: SAQuery) -> SAQuery:
    return query.filter(
        InventoryHistory.status == "CONFIRMED",
        or_(InventoryHistory.ref_type.is_(None), InventoryHistory.ref_type != "UNDO"),
    )


def _period(query: SAQuery, date_from: date | None, date_to: date | None) -> SAQuery:
    start, end = day_range(date_from or month_start(jst_today()), date_to)
    query = query.filter(InventoryHistory.created_at >= start)
    if end:
        query = query.filter(InventoryHistory.created_at < end)
    return query


class MonthlyRow(BaseModel):
    ym: str
    change_type: str
    total_quantity: int


@router.get("/monthly", response_model=list[MonthlyRow])
def monthly(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[MonthlyRow]:
    start, _end = day_range(month_start(jst_today(), months - 1), None)
    # "YYYY-MM-DD HH:MM:SS" の先頭7文字＝年月（SQLite / PostgreSQL 共通）
    ym = func.substr(cast(InventoryHistory.created_at, String), 1, 7).label("ym")
    rows = (
        _usage(db.query(ym, InventoryHistory.change_type, func.sum(InventoryHistory.quantity)))
        .filter(InventoryHistory.change_type.in_(USAGE_TYPES), InventoryHistory.created_at >= start)
        .group_by(ym, InventoryHistory.change_type)
        .order_by(ym)
        .all()
    )
    return [MonthlyRow(ym=r[0] or "", change_type=r[1], total_quantity=int(r[2] or 0)) for r in rows]


class TopRow(BaseModel):
    item_id: int
    item_name: str
    total_quantity: int


@router.get("/top-outbound", response_model=list[TopRow])
def top_outbound(
    limit: int = Query(10, ge=1, le=50),
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[TopRow]:
    """出庫の多い物品。期間の既定は当月（JST）。"""
    total = func.sum(InventoryHistory.quantity)
    query = _usage(db.query(Item.id, Item.item_name, total).join(Item, Item.id == InventoryHistory.item_id))
    rows = (
        _period(query.filter(InventoryHistory.change_type == "OUT"), date_from, date_to)
        .group_by(Item.id, Item.item_name)
        .order_by(total.desc())
        .limit(limit)
        .all()
    )
    return [TopRow(item_id=r[0], item_name=r[1], total_quantity=int(r[2] or 0)) for r in rows]


class DeptRow(BaseModel):
    department: str
    total_outbound: int


@router.get("/by-department", response_model=list[DeptRow])
def by_department(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[DeptRow]:
    total = func.sum(InventoryHistory.quantity)
    rows = (
        _period(_usage(db.query(InventoryHistory.department, total)).filter(InventoryHistory.change_type == "OUT"), date_from, date_to)
        .group_by(InventoryHistory.department)
        .order_by(total.desc())
        .all()
    )
    return [DeptRow(department=r[0] or "(未設定)", total_outbound=int(r[1] or 0)) for r in rows]


class TodoOut(BaseModel):
    guest_outbound: int
    disposal: int
    purchase: int
    receivable: int


@router.get("/todo", response_model=TodoOut)
def todo(db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> TodoOut:
    """処理待ちの件数（C-09）。管理者は全員分、それ以外は自分の申請分。"""
    pt = db.query(PendingTransaction).filter(PendingTransaction.status == "PENDING")
    dr = db.query(DisposalRequest).filter(DisposalRequest.status == "PENDING")
    pr = db.query(PurchaseRequest).filter(PurchaseRequest.deleted_at.is_(None))
    if not user.is_admin:
        pt = pt.filter(PendingTransaction.guest_user_id == user.id)
        dr = dr.filter(DisposalRequest.requester_id == user.id)
        pr = pr.filter(PurchaseRequest.requested_by_user_id == user.id)
    return TodoOut(
        guest_outbound=pt.count(),
        disposal=dr.count(),
        purchase=pr.filter(PurchaseRequest.status == "PENDING").count(),
        receivable=pr.filter(PurchaseRequest.status.in_(("APPROVED", "ORDERED"))).count(),
    )

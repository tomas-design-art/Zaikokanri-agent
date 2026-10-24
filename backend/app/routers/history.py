"""History router — 一覧・CSV・取消（B-10 / B-11 / E-04）。"""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_user
from app.db import get_db
from app.models import InventoryHistory, Item
from app.schemas.common import Page
from app.schemas.stock import StockResultOut
from app.services.stock_service import StockError, actor_of, process_undo, undo_problem
from app.utils.datetime import day_range
from app.utils.text import contains, csv_safe

router = APIRouter(prefix="/history", tags=["history"])

CHANGE_TYPE_LABELS = {"IN": "入庫", "OUT": "出庫", "DISPOSE": "廃棄", "ADJUST": "調整", "STOCKTAKE": "棚卸し", "ORDER": "発注"}
STATUS_LABELS = {"CONFIRMED": "確定", "REJECTED": "取消済", "PENDING": "保留"}


class HistoryRow(BaseModel):
    id: int
    item_id: int
    item_name: str
    unit: str
    change_type: str
    quantity: int
    user_name: str
    department: str | None = None
    status: str
    note: str | None = None
    vendor_name: str | None = None
    unit_price: float | None = None
    total_price: float | None = None
    created_at: str
    can_undo: bool = False


class HistoryFilter(BaseModel):
    q: str | None = None
    change_type: str | None = None
    department: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    mine: bool = False


def _base_query(db: Session, f: HistoryFilter, user: CurrentUser) -> SAQuery:
    query = db.query(InventoryHistory, Item.item_name, Item.unit).join(Item, Item.id == InventoryHistory.item_id)
    if f.q and f.q.strip():
        query = query.filter(or_(contains(Item.item_name, f.q.strip()), contains(InventoryHistory.user_name, f.q.strip())))
    if f.change_type:
        query = query.filter(InventoryHistory.change_type == f.change_type)
    if f.department:
        query = query.filter(InventoryHistory.department == f.department)
    if f.mine:
        query = query.filter(InventoryHistory.created_by == user.id)
    start, end = day_range(f.date_from, f.date_to)
    if start:
        query = query.filter(InventoryHistory.created_at >= start)
    if end:
        query = query.filter(InventoryHistory.created_at < end)
    return query


@router.get("", response_model=Page[HistoryRow])
def list_history(
    f: HistoryFilter = Depends(),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Page[HistoryRow]:
    query = _base_query(db, f, user)
    total = query.count()
    rows = (
        query.order_by(InventoryHistory.created_at.desc(), InventoryHistory.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    can_undo_role = user.has_role("USER")
    items = [
        HistoryRow(
            id=h.id, item_id=h.item_id, item_name=name, unit=unit or "個", change_type=h.change_type,
            quantity=h.quantity, user_name=h.user_name, department=h.department, status=h.status, note=h.note,
            vendor_name=h.vendor_name, unit_price=h.unit_price, total_price=h.total_price,
            created_at=h.created_at.isoformat(timespec="seconds") if h.created_at else "",
            can_undo=can_undo_role and undo_problem(h, user_id=user.id, is_admin=user.is_admin) is None,
        )
        for h, name, unit in rows
    ]
    return Page[HistoryRow](items=items, total=total, page=page, per_page=per_page)


@router.post("/{hid}/undo", response_model=StockResultOut)
def undo(hid: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> StockResultOut:
    """打ち間違いの取消。本人（管理者は全員分）の通常の入出庫を、操作から10分以内だけ（B-10）。"""
    h = db.query(InventoryHistory).filter(InventoryHistory.id == hid).with_for_update().first()
    if not h:
        raise HTTPException(404, "履歴が見つかりません")
    problem = undo_problem(h, user_id=user.id, is_admin=user.is_admin)
    if problem == "本人の操作だけ取り消せます":
        raise HTTPException(403, problem)
    if problem:
        raise HTTPException(400, problem)
    try:
        r = process_undo(db, actor_of(user), h)
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return StockResultOut(**r.__dict__)


@router.get("/export.csv")
def export_csv(
    f: HistoryFilter = Depends(),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    rows = _base_query(db, f, user).order_by(InventoryHistory.created_at.desc()).all()
    buf = io.StringIO()
    buf.write("﻿")  # Excel で文字化けしないように
    w = csv.writer(buf)
    w.writerow(["日時", "物品名", "区分", "数量", "単位", "担当者", "部署", "状態", "備考", "業者", "単価", "合計"])
    for h, name, unit in rows:
        w.writerow([csv_safe(v) for v in [
            h.created_at.isoformat(sep=" ", timespec="seconds") if h.created_at else "",
            name, CHANGE_TYPE_LABELS.get(h.change_type, h.change_type), h.quantity, unit or "個", h.user_name,
            h.department or "", STATUS_LABELS.get(h.status, h.status), h.note or "", h.vendor_name or "",
            h.unit_price if h.unit_price is not None else "", h.total_price if h.total_price is not None else "",
        ]])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="history.csv"'},
    )

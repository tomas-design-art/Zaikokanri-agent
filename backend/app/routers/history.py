"""History router — listing + CSV export."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import InventoryHistory, Item
from app.schemas.common import Page

router = APIRouter(prefix="/history", tags=["history"])


class HistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    item_name: str
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


def _base_query(db: Session, q: str | None, change_type: str | None, department: str | None, date_from: str | None, date_to: str | None):
    query = (
        db.query(InventoryHistory, Item.item_name)
        .join(Item, Item.id == InventoryHistory.item_id)
    )
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Item.item_name.like(like), InventoryHistory.user_name.like(like)))
    if change_type:
        query = query.filter(InventoryHistory.change_type == change_type)
    if department:
        query = query.filter(InventoryHistory.department == department)
    if date_from:
        query = query.filter(InventoryHistory.created_at >= date_from)
    if date_to:
        query = query.filter(InventoryHistory.created_at <= date_to + " 23:59:59")
    return query


@router.get("", response_model=Page[HistoryRow])
def list_history(
    q: str | None = None,
    change_type: str | None = None,
    department: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Page[HistoryRow]:
    query = _base_query(db, q, change_type, department, date_from, date_to)
    total = query.count()
    rows = (
        query.order_by(InventoryHistory.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    items = [
        HistoryRow(
            id=h.id,
            item_id=h.item_id,
            item_name=name,
            change_type=h.change_type,
            quantity=h.quantity,
            user_name=h.user_name,
            department=h.department,
            status=h.status,
            note=h.note,
            vendor_name=h.vendor_name,
            unit_price=h.unit_price,
            total_price=h.total_price,
            created_at=h.created_at.isoformat() if h.created_at else "",
        )
        for h, name in rows
    ]
    return Page[HistoryRow](items=items, total=total, page=page, per_page=per_page)


@router.get("/export.csv")
def export_csv(
    q: str | None = None,
    change_type: str | None = None,
    department: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    query = _base_query(db, q, change_type, department, date_from, date_to)
    rows = query.order_by(InventoryHistory.created_at.desc()).all()
    buf = io.StringIO()
    # BOM for Excel JP compat
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["日時", "物品名", "区分", "数量", "担当者", "部署", "状態", "備考", "業者", "単価", "合計"])
    for h, name in rows:
        w.writerow([
            h.created_at.isoformat() if h.created_at else "",
            name,
            h.change_type,
            h.quantity,
            h.user_name,
            h.department or "",
            h.status,
            h.note or "",
            h.vendor_name or "",
            h.unit_price or "",
            h.total_price or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="history.csv"'},
    )

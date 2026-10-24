"""Inventory router — 在庫一覧（KPI・絞り込み・ページ送り・CSV）。"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import Department, Inventory, Item
from app.schemas.common import Page
from app.schemas.items import InventoryRow
from app.services.inventory_view import expiry_window, inventory_query, to_row
from app.services.scope import Scope, item_filter
from app.utils.text import csv_safe

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryKPI(BaseModel):
    total_items: int
    total_quantity: int
    low_stock_count: int
    expired_count: int
    expiring_soon_count: int


@router.get("/kpi", response_model=InventoryKPI)
def kpi(scope: Scope | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> InventoryKPI:
    today, soon = expiry_window()
    active = db.query(Item).filter(Item.is_active == 1)
    stock = db.query(Inventory).join(Item, Item.id == Inventory.item_id).filter(Item.is_active == 1)
    visible = item_filter(user, scope)
    if visible is not None:
        active, stock = active.filter(visible), stock.filter(visible)
    with_expiry = active.filter(Item.expiry_date.is_not(None))
    return InventoryKPI(
        total_items=active.count(),
        total_quantity=stock.with_entities(func.coalesce(func.sum(Inventory.quantity), 0)).scalar() or 0,
        low_stock_count=stock.filter(Inventory.quantity <= Inventory.threshold).count(),
        expired_count=with_expiry.filter(Item.expiry_date < today).count(),
        expiring_soon_count=with_expiry.filter(Item.expiry_date >= today, Item.expiry_date <= soon).count(),
    )


@router.get("", response_model=Page[InventoryRow])
def list_inventory(
    q: str | None = None,
    category: str | None = None,
    department: str | None = None,
    only_low_stock: bool = False,
    scope: Scope | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Page[InventoryRow]:
    query = inventory_query(db, q=q, category=category, department=department, only_low_stock=only_low_stock,
                            visible=item_filter(user, scope))
    total = query.count()
    rows = query.order_by(Item.item_name).offset((page - 1) * per_page).limit(per_page).all()
    items = [to_row(i, inv, hide_prices=user.is_guest) for i, inv in rows]
    return Page[InventoryRow](items=items, total=total, page=page, per_page=per_page)


@router.get("/export.csv")
def export_csv(
    q: str | None = None,
    category: str | None = None,
    only_low_stock: bool = False,
    scope: Scope | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """在庫一覧の CSV（B-20）。Excel で文字化けしないよう BOM 付き UTF-8。ゲストには業者・単価の列を出さない（I-09）。"""
    rows = inventory_query(db, q=q, category=category, only_low_stock=only_low_stock,
                           visible=item_filter(user, scope)).order_by(Item.item_name).all()
    depts = dict(db.query(Department.id, Department.name).all())
    priced = not user.is_guest
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    # 列の順は前と同じ（所属部署は最後に足した）
    w.writerow(["物品名", "物品コード", "カテゴリ", *(["業者"] if priced else []), "保管場所", "在庫数", "単位", "発注点",
                *(["単価"] if priced else []), "有効期限", "状態", "所属部署"])
    for item, inv in rows:
        r = to_row(item, inv)
        flags = (("期限切れ", r.is_expired), ("期限間近", r.is_expiring_soon), ("在庫不足", r.is_low_stock))
        owner = "・".join(x for x in (depts.get(item.owner_department_id), "共通" if item.is_common else None) if x)
        w.writerow([csv_safe(v) for v in [
            r.item_name, r.item_code or "", r.category, *([r.vendor_name or ""] if priced else []), r.location or "",
            r.quantity, r.unit, r.threshold, *([r.unit_price] if priced else []), r.expiry_date or "",
            "・".join(s for s, on in flags if on), owner,
        ]])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="inventory.csv"'},
    )

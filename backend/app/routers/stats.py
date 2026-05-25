"""Stats router — monthly, top, by-department."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.db import get_db
from app.models import InventoryHistory, Item

router = APIRouter(prefix="/stats", tags=["stats"])


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
    # Use strftime for SQLite or to_char for postgres — use a portable substring.
    ym = func.substr(func.cast(InventoryHistory.created_at, type_=__import__("sqlalchemy").String), 1, 7)
    rows = (
        db.query(ym.label("ym"), InventoryHistory.change_type, func.sum(InventoryHistory.quantity))
        .filter(InventoryHistory.status == "CONFIRMED")
        .group_by("ym", InventoryHistory.change_type)
        .order_by("ym")
        .all()
    )
    out = [MonthlyRow(ym=r[0] or "", change_type=r[1], total_quantity=int(r[2] or 0)) for r in rows]
    return out[-months * 3:] if out else []


class TopRow(BaseModel):
    item_id: int
    item_name: str
    total_quantity: int


@router.get("/top-outbound", response_model=list[TopRow])
def top_outbound(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[TopRow]:
    rows = (
        db.query(Item.id, Item.item_name, func.sum(InventoryHistory.quantity))
        .join(Item, Item.id == InventoryHistory.item_id)
        .filter(InventoryHistory.change_type == "OUT", InventoryHistory.status == "CONFIRMED")
        .group_by(Item.id, Item.item_name)
        .order_by(func.sum(InventoryHistory.quantity).desc())
        .limit(limit)
        .all()
    )
    return [TopRow(item_id=r[0], item_name=r[1], total_quantity=int(r[2] or 0)) for r in rows]


class DeptRow(BaseModel):
    department: str
    total_outbound: int


@router.get("/by-department", response_model=list[DeptRow])
def by_department(
    db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)
) -> list[DeptRow]:
    rows = (
        db.query(InventoryHistory.department, func.sum(InventoryHistory.quantity))
        .filter(InventoryHistory.change_type == "OUT", InventoryHistory.status == "CONFIRMED")
        .group_by(InventoryHistory.department)
        .order_by(func.sum(InventoryHistory.quantity).desc())
        .all()
    )
    return [DeptRow(department=r[0] or "(未設定)", total_outbound=int(r[1] or 0)) for r in rows]

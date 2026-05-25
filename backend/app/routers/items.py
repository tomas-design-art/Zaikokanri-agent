"""Items router — CRUD + search."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.models import Inventory, Item
from app.schemas.common import Page
from app.schemas.items import ItemCreate, ItemOut, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=Page[ItemOut])
def list_items(
    q: str | None = None,
    category: str | None = None,
    is_active: int | None = 1,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Page[ItemOut]:
    query = db.query(Item)
    if is_active is not None:
        query = query.filter(Item.is_active == is_active)
    if category:
        query = query.filter(Item.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Item.item_name.like(like),
                Item.item_code.like(like),
                Item.vendor_name.like(like),
                Item.vendor_item_code.like(like),
            )
        )
    total = query.count()
    rows = (
        query.order_by(Item.item_name)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return Page[ItemOut](
        items=[ItemOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=ItemOut, status_code=201)
def create_item(
    body: ItemCreate, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
) -> ItemOut:
    item = Item(**body.model_dump())
    db.add(item)
    db.flush()
    # auto-create inventory row
    inv = Inventory(item_id=item.id, quantity=0, threshold=body.reorder_point or 10)
    db.add(inv)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)
) -> ItemOut:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return ItemOut.model_validate(item)


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    body: ItemUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
) -> ItemOut:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


@router.delete("/{item_id}", status_code=204)
def deactivate_item(
    item_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
) -> None:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    item.is_active = 0
    db.commit()

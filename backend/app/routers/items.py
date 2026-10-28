"""Items router — 物品マスターの CRUD + 検索。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.models import Category, Department, Inventory, Item
from app.schemas.common import Page
from app.schemas.items import ItemCreate, ItemDetail, ItemOut, ItemUpdate
from app.services.inventory_view import DEFAULT_THRESHOLD, search_items, sync_threshold
from app.services.scope import Scope, item_filter, require_visible_to_guest
from app.services.stock_service import actor_of, record_initial_stock

router = APIRouter(prefix="/items", tags=["items"])

# DB 上 NULL にできない列。更新で None が来たら「変更しない」（B-04）
_NOT_NULL = {"item_name", "category", "unit", "unit_price", "is_asset", "is_common", "is_inventory_target", "is_active"}


def _check_category(db: Session, name: str) -> None:
    if not db.query(Category).filter(Category.name == name, Category.is_active == 1).first():
        raise HTTPException(400, f"カテゴリ「{name}」が登録されていません。先にマスタ管理で登録してください")


def _check_owner(db: Session, item: Item) -> None:
    """所属部署か全社共通のどちらかは必ずある。所属部署は有効な部署だけ（I-01）。"""
    if item.owner_department_id is not None:
        d = db.get(Department, item.owner_department_id)
        if not d or not d.is_active:
            raise HTTPException(400, "所属部署が見つからないか、無効になっています")
    elif not item.is_common:
        raise HTTPException(400, "所属部署を選ぶか、全社共通にしてください")


def _out(model, item: Item, user: CurrentUser, **extra):  # noqa: ANN001
    """ゲストには単価・業者を出さない（I-09）。"""
    out = model.model_validate(item).model_copy(update=extra)
    if user.is_guest:
        out = out.model_copy(update={"unit_price": None, "vendor_name": None, "vendor_item_code": None})
    return out


@router.get("", response_model=Page[ItemOut])
def list_items(
    q: str | None = None,
    category: str | None = None,
    include_inactive: bool = False,
    scope: Scope | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Page[ItemOut]:
    query = db.query(Item)
    if not include_inactive:
        query = query.filter(Item.is_active == 1)
    if category:
        query = query.filter(Item.category == category)
    visible = item_filter(user, scope)
    if visible is not None:
        query = query.filter(visible)
    query = search_items(query, q)
    total = query.count()
    rows = query.order_by(Item.is_active.desc(), Item.item_name).offset((page - 1) * per_page).limit(per_page).all()
    return Page[ItemOut](items=[_out(ItemOut, r, user) for r in rows], total=total, page=page, per_page=per_page)


@router.post("", response_model=ItemOut, status_code=201)
def create_item(body: ItemCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)) -> ItemOut:
    _check_category(db, body.category)
    data = body.model_dump(exclude={"initial_quantity"})
    if data["is_common"] is None:
        data["is_common"] = 0 if data["owner_department_id"] is not None else 1
    item = Item(**data)
    _check_owner(db, item)
    db.add(item)
    db.flush()
    threshold = body.reorder_point if body.reorder_point is not None else DEFAULT_THRESHOLD
    inv = Inventory(item_id=item.id, quantity=0, threshold=threshold)
    db.add(inv)
    db.flush()
    record_initial_stock(db, actor_of(user), item, inv, body.initial_quantity)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


@router.get("/{item_id}", response_model=ItemDetail)
def get_item(item_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> ItemDetail:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "物品が見つかりません")
    require_visible_to_guest(user, item)
    inv = db.query(Inventory).filter(Inventory.item_id == item_id).first()
    return _out(ItemDetail, item, user, quantity=inv.quantity if inv else 0,
                threshold=inv.threshold if inv else DEFAULT_THRESHOLD)


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int, body: ItemUpdate, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
) -> ItemOut:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "物品が見つかりません")
    data = body.model_dump(exclude_unset=True)
    if data.get("category"):
        _check_category(db, data["category"])
    for k, v in data.items():
        if v is None and k in _NOT_NULL:
            continue
        setattr(item, k, v)
    if "owner_department_id" in data or "is_common" in data:
        try:
            _check_owner(db, item)
        except HTTPException:
            db.rollback()
            raise
    if "reorder_point" in data:
        sync_threshold(db, item)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


@router.delete("/{item_id}", status_code=204)
def deactivate_item(item_id: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> None:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "物品が見つかりません")
    item.is_active = 0
    db.commit()

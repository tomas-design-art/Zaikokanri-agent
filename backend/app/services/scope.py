"""部署の見える範囲（docs/REVIEW_2026-10-23.md の I 章）。

- 「自分の部署」（dept）：自分の部署の物品＋共通の物品。履歴・統計は自分の部署の人の操作＋自分の部署の物品への操作＋自分の操作
- 既定：一般・ゲストは dept、管理者は all。一般と管理者は切り替えられる。ゲストはいつも dept（I-03）
"""
from __future__ import annotations

from typing import Literal

from fastapi import HTTPException
from sqlalchemy import ColumnElement, false, or_, select

from app.auth import CurrentUser
from app.models import InventoryHistory, Item

Scope = Literal["dept", "all"]
OTHER_DEPARTMENT_ITEM = "ほかの部署の物品です。自分の部署の物品か共通の物品を選んでください"


def resolve(user: CurrentUser, scope: Scope | None) -> Scope:
    if user.is_guest:
        return "dept"
    return scope or ("all" if user.is_admin else "dept")


def own_items(user: CurrentUser) -> ColumnElement[bool]:
    cond = Item.is_common == 1
    if user.department_id is not None:
        cond = or_(cond, Item.owner_department_id == user.department_id)
    return cond


def item_filter(user: CurrentUser, scope: Scope | None) -> ColumnElement[bool] | None:
    """Item の絞り込み。全部署なら None。"""
    return own_items(user) if resolve(user, scope) == "dept" else None


def can_see_item(user: CurrentUser, item: Item) -> bool:
    return bool(item.is_common) or (user.department_id is not None and item.owner_department_id == user.department_id)


def require_visible_to_guest(user: CurrentUser, item: Item | None) -> None:
    """ゲストはほかの部署だけの物品を使えない（I-04）。"""
    if user.is_guest and item is not None and not can_see_item(user, item):
        raise HTTPException(403, OTHER_DEPARTMENT_ITEM)


def history_filter(user: CurrentUser, scope: Scope | None) -> ColumnElement[bool] | None:
    """InventoryHistory の絞り込み（I-05）。全部署なら None。"""
    if resolve(user, scope) == "all":
        return None
    conds = [InventoryHistory.created_by == user.id]
    if user.department_id is not None:
        conds.append(InventoryHistory.department_id == user.department_id)
        conds.append(InventoryHistory.item_id.in_(select(Item.id).where(Item.owner_department_id == user.department_id)))
    return or_(*conds)


def request_filter(user: CurrentUser, scope: Scope | None, department_col, requester_col) -> ColumnElement[bool] | None:  # noqa: ANN001
    """発注・廃棄の申請の絞り込み：自分の部署の申請＋自分の申請（I-10）。"""
    if resolve(user, scope) == "all":
        return None
    dept = department_col == user.department_id if user.department_id is not None else false()
    return or_(dept, requester_col == user.id)


def same_department(user: CurrentUser, department_id: int | None) -> bool:
    """承認・連絡の処理ができるか：管理者は全部署、一般は同じ部署だけ（I-07 / I-08）。"""
    return user.is_admin or (user.department_id is not None and user.department_id == department_id)

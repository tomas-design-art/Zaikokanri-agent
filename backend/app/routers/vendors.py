"""Master CRUD: vendors, categories, departments (all admin-only mutations).

物品は業者名・カテゴリ名を文字列で持つため、名前を変えたら物品側も同じ名前に直す（E-07）。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.models import Category, Department, Item, User, Vendor
from app.schemas.common import OptStr, ReqStr

# ---------- Vendors ----------
vendors_router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorBase(BaseModel):
    vendor_code: ReqStr = Field(max_length=32)
    vendor_name: ReqStr = Field(max_length=128)
    address: OptStr = None
    phone: OptStr = Field(default=None, max_length=32)
    email: OptStr = Field(default=None, max_length=128)


class VendorOut(VendorBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: int


class VendorUpdate(BaseModel):
    vendor_code: ReqStr | None = Field(default=None, max_length=32)
    vendor_name: ReqStr | None = Field(default=None, max_length=128)
    address: OptStr = None
    phone: OptStr = Field(default=None, max_length=32)
    email: OptStr = Field(default=None, max_length=128)
    is_active: Literal[0, 1] | None = None


@vendors_router.get("", response_model=list[VendorOut])
def list_vendors(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[VendorOut]:
    q = db.query(Vendor)
    if not include_inactive:
        q = q.filter(Vendor.is_active == 1)
    return [VendorOut.model_validate(v) for v in q.order_by(Vendor.is_active.desc(), Vendor.vendor_name).all()]


@vendors_router.post("", response_model=VendorOut, status_code=201)
def create_vendor(body: VendorBase, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> VendorOut:
    v = Vendor(**body.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return VendorOut.model_validate(v)


@vendors_router.patch("/{vid}", response_model=VendorOut)
def update_vendor(
    vid: int, body: VendorUpdate, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
) -> VendorOut:
    v = db.get(Vendor, vid)
    if not v:
        raise HTTPException(404, "見つかりません")
    data = body.model_dump(exclude_unset=True)
    new_name = data.get("vendor_name")
    if new_name and new_name != v.vendor_name:
        db.query(Item).filter(Item.vendor_name == v.vendor_name).update({"vendor_name": new_name}, synchronize_session=False)
    for k, val in data.items():
        if val is None and k in {"vendor_code", "vendor_name", "is_active"}:
            continue
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return VendorOut.model_validate(v)



# ---------- Categories ----------
categories_router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryIn(BaseModel):
    name: ReqStr = Field(max_length=64)


class MasterUpdate(BaseModel):
    name: ReqStr | None = Field(default=None, max_length=64)
    is_active: Literal[0, 1] | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: int


@categories_router.get("", response_model=list[CategoryOut])
def list_categories(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[CategoryOut]:
    q = db.query(Category)
    if not include_inactive:
        q = q.filter(Category.is_active == 1)
    return [CategoryOut.model_validate(v) for v in q.order_by(Category.is_active.desc(), Category.name).all()]


@categories_router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> CategoryOut:
    c = Category(name=body.name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return CategoryOut.model_validate(c)


@categories_router.delete("/{cid}", status_code=204)
def deactivate_category(cid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> None:
    c = db.get(Category, cid)
    if not c:
        raise HTTPException(404, "見つかりません")
    c.is_active = 0
    db.commit()


# ---------- Departments ----------
departments_router = APIRouter(prefix="/departments", tags=["departments"])


class DepartmentIn(BaseModel):
    name: ReqStr = Field(max_length=64)


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: int


@departments_router.get("", response_model=list[DepartmentOut])
def list_departments(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[DepartmentOut]:
    q = db.query(Department)
    if not include_inactive:
        q = q.filter(Department.is_active == 1)
    return [DepartmentOut.model_validate(v) for v in q.order_by(Department.is_active.desc(), Department.name).all()]


@departments_router.post("", response_model=DepartmentOut, status_code=201)
def create_department(body: DepartmentIn, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> DepartmentOut:
    d = Department(name=body.name)
    db.add(d)
    db.commit()
    db.refresh(d)
    return DepartmentOut.model_validate(d)


@departments_router.delete("/{did}", status_code=204)
def deactivate_department(did: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> None:
    d = db.get(Department, did)
    if not d:
        raise HTTPException(404, "見つかりません")
    d.is_active = 0
    db.commit()


@categories_router.patch("/{cid}", response_model=CategoryOut)
def update_category(cid: int, body: MasterUpdate, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> CategoryOut:
    c = db.get(Category, cid)
    if not c:
        raise HTTPException(404, "カテゴリが見つかりません")
    if body.name and body.name != c.name:
        db.query(Item).filter(Item.category == c.name).update({"category": body.name}, synchronize_session=False)
        c.name = body.name
    if body.is_active is not None:
        c.is_active = body.is_active
    db.commit()
    db.refresh(c)
    return CategoryOut.model_validate(c)


@departments_router.patch("/{did}", response_model=DepartmentOut)
def update_department(did: int, body: MasterUpdate, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> DepartmentOut:
    d = db.get(Department, did)
    if not d:
        raise HTTPException(404, "部署が見つかりません")
    if body.name and body.name != d.name:
        db.query(User).filter(User.department_id == d.id).update({"department": body.name}, synchronize_session=False)
        d.name = body.name
    if body.is_active is not None:
        d.is_active = body.is_active
    db.commit()
    db.refresh(d)
    return DepartmentOut.model_validate(d)

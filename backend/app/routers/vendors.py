"""Master CRUD: vendors, categories, departments (all admin-only mutations)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.models import Category, Department, Vendor

# ---------- Vendors ----------
vendors_router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorBase(BaseModel):
    vendor_code: str
    vendor_name: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class VendorOut(VendorBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: int


class VendorUpdate(BaseModel):
    vendor_code: str | None = None
    vendor_name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: int | None = None


@vendors_router.get("", response_model=list[VendorOut])
def list_vendors(
    is_active: int | None = 1,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[VendorOut]:
    q = db.query(Vendor)
    if is_active is not None:
        q = q.filter(Vendor.is_active == is_active)
    return [VendorOut.model_validate(v) for v in q.order_by(Vendor.vendor_name).all()]


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
        raise HTTPException(404, "Not found")
    for k, val in body.model_dump(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return VendorOut.model_validate(v)


router = vendors_router  # exported as `router` for main.py


# ---------- Categories ----------
categories_router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryIn(BaseModel):
    name: str


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: int


@categories_router.get("", response_model=list[CategoryOut])
def list_categories(
    is_active: int | None = 1,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[CategoryOut]:
    q = db.query(Category)
    if is_active is not None:
        q = q.filter(Category.is_active == is_active)
    return [CategoryOut.model_validate(c) for c in q.order_by(Category.name).all()]


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
        raise HTTPException(404, "Not found")
    c.is_active = 0
    db.commit()


# ---------- Departments ----------
departments_router = APIRouter(prefix="/departments", tags=["departments"])


class DepartmentIn(BaseModel):
    name: str


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: int


@departments_router.get("", response_model=list[DepartmentOut])
def list_departments(
    is_active: int | None = 1,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[DepartmentOut]:
    q = db.query(Department)
    if is_active is not None:
        q = q.filter(Department.is_active == is_active)
    return [DepartmentOut.model_validate(d) for d in q.order_by(Department.name).all()]


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
        raise HTTPException(404, "Not found")
    d.is_active = 0
    db.commit()

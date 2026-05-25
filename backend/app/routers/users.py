"""Users router — admin-only management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, hash_password, require_admin
from app.db import get_db
from app.models import Department, User

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=4, max_length=128)
    display_name: str
    user_role: str
    department: str | None = None
    department_id: int | None = None


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=4, max_length=128)
    display_name: str | None = None
    user_role: str | None = None
    department: str | None = None
    department_id: int | None = None
    is_active: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    user_role: str
    department: str | None
    department_id: int | None
    is_active: int


def _resolve_department(db: Session, dept_id: int | None, dept_name: str | None) -> tuple[int | None, str | None]:
    if dept_id is not None:
        d = db.get(Department, dept_id)
        if not d:
            raise HTTPException(400, "department_id 不正")
        return d.id, d.name
    if dept_name:
        d = db.query(Department).filter(Department.name == dept_name).first()
        if not d:
            raise HTTPException(400, "department 名が存在しません")
        return d.id, d.name
    return None, None


@router.get("", response_model=list[UserOut])
def list_users(
    is_active: int | None = 1,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
) -> list[UserOut]:
    q = db.query(User)
    if is_active is not None:
        q = q.filter(User.is_active == is_active)
    return [UserOut.model_validate(u) for u in q.order_by(User.username).all()]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
) -> UserOut:
    if body.user_role not in {"GUEST", "USER", "ADMIN"}:
        raise HTTPException(400, "user_role must be GUEST/USER/ADMIN")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "username 重複")
    did, dname = _resolve_department(db, body.department_id, body.department)
    u = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        user_role=body.user_role,
        department=dname,
        department_id=did,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.patch("/{uid}", response_model=UserOut)
def update_user(
    uid: int, body: UserUpdate, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)
) -> UserOut:
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        u.password_hash = hash_password(data.pop("password"))
    if "user_role" in data and data["user_role"] not in {"GUEST", "USER", "ADMIN"}:
        raise HTTPException(400, "user_role invalid")
    if "department" in data or "department_id" in data:
        did, dname = _resolve_department(db, data.pop("department_id", None), data.pop("department", None))
        u.department = dname
        u.department_id = did
    for k, v in data.items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return UserOut.model_validate(u)


@router.delete("/{uid}", status_code=204)
def deactivate_user(uid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> None:
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    u.is_active = 0
    db.commit()

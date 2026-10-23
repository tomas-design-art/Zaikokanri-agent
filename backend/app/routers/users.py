"""Users router — admin-only management (A-02 / A-03 / A-05 / A-06)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, hash_password, require_admin
from app.auth.deps import revoke_sessions
from app.db import get_db
from app.models import Department, User
from app.schemas.common import NewPassword, OptStr, ReqStr
from app.security_log import security_event
from app.utils.datetime import jst_now

router = APIRouter(prefix="/users", tags=["users"])

Role = Literal["GUEST", "USER", "ADMIN"]


class UserCreate(BaseModel):
    username: ReqStr = Field(max_length=64)
    password: NewPassword
    display_name: ReqStr = Field(max_length=64)
    user_role: Role
    department: OptStr = None
    department_id: int | None = None


class UserUpdate(BaseModel):
    password: NewPassword | None = None
    display_name: ReqStr | None = None
    user_role: Role | None = None
    department: OptStr = None
    department_id: int | None = None
    is_active: Literal[0, 1] | None = None
    unlock: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    user_role: str
    department: str | None
    department_id: int | None
    is_active: int
    must_change_password: int = 0
    locked: bool = False


def _out(u: User) -> UserOut:
    return UserOut.model_validate(u).model_copy(update={"locked": bool(u.locked_until and u.locked_until > jst_now())})


def _resolve_department(db: Session, dept_id: int | None, dept_name: str | None) -> tuple[int | None, str | None]:
    if dept_id is not None:
        d = db.get(Department, dept_id)
        if not d:
            raise HTTPException(400, "部署が見つかりません")
        return d.id, d.name
    if dept_name:
        d = db.query(Department).filter(Department.name == dept_name).first()
        if not d:
            raise HTTPException(400, "部署が登録されていません")
        return d.id, d.name
    return None, None


def _active_admin_count(db: Session) -> int:
    return db.query(User).filter(User.user_role == "ADMIN", User.is_active == 1).count()


def _guard_admin_loss(db: Session, target: User, me: CurrentUser, *, removing: bool) -> None:
    """自分自身の無効化・降格と、有効な管理者が0人になる変更を止める（A-02）。"""
    if not removing:
        return
    if target.id == me.id:
        raise HTTPException(400, "自分自身を無効化・降格することはできません")
    if target.user_role == "ADMIN" and target.is_active and _active_admin_count(db) <= 1:
        raise HTTPException(400, "有効な管理者が1人もいなくなるため変更できません")


@router.get("", response_model=list[UserOut])
def list_users(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
) -> list[UserOut]:
    q = db.query(User)
    if not include_inactive:
        q = q.filter(User.is_active == 1)
    return [_out(u) for u in q.order_by(User.is_active.desc(), User.username).all()]


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), me: CurrentUser = Depends(require_admin)) -> UserOut:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "このユーザー名はすでに登録されています")
    did, dname = _resolve_department(db, body.department_id, body.department)
    u = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        user_role=body.user_role,
        department=dname,
        department_id=did,
        must_change_password=1,  # 管理者が決めた仮パスワードは本人が変える（A-03）
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    security_event("user_created", actor=me.username, target=u.username, role=u.user_role)
    return _out(u)


@router.patch("/{uid}", response_model=UserOut)
def update_user(
    uid: int, body: UserUpdate, db: Session = Depends(get_db), me: CurrentUser = Depends(require_admin)
) -> UserOut:
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "ユーザーが見つかりません")
    data = body.model_dump(exclude_unset=True)
    demoting = "user_role" in data and data["user_role"] != "ADMIN" and u.user_role == "ADMIN"
    deactivating = data.get("is_active") == 0 and u.is_active == 1
    _guard_admin_loss(db, u, me, removing=demoting or deactivating)
    if data.get("password"):
        u.password_hash = hash_password(data.pop("password"))
        u.must_change_password = 0 if u.id == me.id else 1
        u.failed_login_count, u.locked_until = 0, None
        revoke_sessions(u)  # ほかの端末のログインも無効にする（G-03）
        security_event("password_reset", actor=me.username, target=u.username)
    data.pop("password", None)
    if data.pop("unlock", False):
        u.failed_login_count, u.locked_until = 0, None
        security_event("account_unlocked", actor=me.username, target=u.username)
    if deactivating:
        revoke_sessions(u)
    if "user_role" in data and data["user_role"] != u.user_role:
        security_event("role_changed", actor=me.username, target=u.username, role=data["user_role"])
    if "department" in data or "department_id" in data:
        u.department_id, u.department = _resolve_department(db, data.pop("department_id", None), data.pop("department", None))
    for k, v in data.items():
        if v is not None:
            setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return _out(u)


@router.delete("/{uid}", status_code=204)
def deactivate_user(uid: int, db: Session = Depends(get_db), me: CurrentUser = Depends(require_admin)) -> None:
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "ユーザーが見つかりません")
    _guard_admin_loss(db, u, me, removing=True)
    u.is_active = 0
    revoke_sessions(u)
    db.commit()
    security_event("user_deactivated", actor=me.username, target=u.username)

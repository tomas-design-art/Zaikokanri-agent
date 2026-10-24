"""Disposal requests (廃棄申請) router（C-01 / C-03）と、ゲストの「部署への連絡」（I-08）。

廃棄申請は一般以上の仕事。ゲストは同じ部署の一般へ「これ廃棄が要りそう」と連絡し、
一般が正式な申請に上げるか、対応不要にする。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, aliased

from app.auth import CurrentUser, get_current_user, require_admin, require_user
from app.db import get_db
from app.models import Department, DisposalNotice, DisposalRequest, Inventory, Item, User
from app.schemas.common import OptStr, Page, ReqStr
from app.services.scope import Scope, request_filter, require_visible_to_guest, resolve, same_department
from app.services.stock_service import StockError, actor_of, check_outbound, lock_inventory, process_dispose
from app.services.workflow import claim, require_reason
from app.utils.datetime import jst_now

router = APIRouter(prefix="/disposal-requests", tags=["disposal-requests"])


class DRCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    reason: ReqStr = Field(max_length=512)


class DRApprove(BaseModel):
    approve: bool
    reject_reason: OptStr = None


class DROut(BaseModel):
    id: int
    item_id: int
    item_name: str
    unit: str
    quantity: int
    reason: str
    requester: str
    requester_id: int
    department: str | None = None
    status: str
    reject_reason: str | None
    created_at: str


def _rows(db: Session):
    return (
        db.query(DisposalRequest, Item.item_name, Item.unit, User.display_name, Department.name)
        .join(Item, Item.id == DisposalRequest.item_id)
        .join(User, User.id == DisposalRequest.requester_id)
        .outerjoin(Department, Department.id == DisposalRequest.department_id)
    )


def _out(row) -> DROut:  # noqa: ANN001
    d, name, unit, who, dept = row
    return DROut(
        id=d.id, item_id=d.item_id, item_name=name, unit=unit or "個", quantity=d.quantity, reason=d.reason,
        requester=who, requester_id=d.requester_id, department=dept, status=d.status, reject_reason=d.reject_reason,
        created_at=d.created_at.isoformat(timespec="seconds") if d.created_at else "",
    )


def _new_request(db: Session, user: CurrentUser, *, item_id: int, quantity: int, reason: str,
                 department_id: int | None) -> DisposalRequest:
    """申請の時点で在庫・有効性を確かめる（C-03）。"""
    try:
        item, inv = lock_inventory(db, item_id)
        check_outbound(item, inv, quantity, verb="廃棄")
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    d = DisposalRequest(
        item_id=item_id, quantity=quantity, reason=reason, requester_id=user.id, department_id=department_id,
        status="PENDING", created_at=jst_now(),
    )
    db.add(d)
    db.flush()
    return d


@router.get("", response_model=Page[DROut])
def list_dr(
    status: str | None = None,
    mine: bool = False,
    scope: Scope | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_user),
) -> Page[DROut]:
    """一般の既定は自分の部署の申請＋自分の申請、切り替えで全部署（I-10）。"""
    q = _rows(db)
    cond = request_filter(user, scope, DisposalRequest.department_id, DisposalRequest.requester_id)
    if cond is not None:
        q = q.filter(cond)
    if status:
        q = q.filter(DisposalRequest.status == status)
    if mine:
        q = q.filter(DisposalRequest.requester_id == user.id)
    total = q.count()
    rows = q.order_by(DisposalRequest.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return Page[DROut](items=[_out(r) for r in rows], total=total, page=page, per_page=per_page)


@router.post("", response_model=DROut, status_code=201)
def create_dr(body: DRCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> DROut:
    """廃棄申請は一般以上。ゲストは「部署への連絡」を使う（I-08）。"""
    d = _new_request(db, user, item_id=body.item_id, quantity=body.quantity, reason=body.reason,
                     department_id=user.department_id)
    db.commit()
    return _out(_rows(db).filter(DisposalRequest.id == d.id).one())


@router.delete("/{dr_id}", status_code=204)
def cancel_dr(dr_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    """申請者本人（または管理者）が保留中の申請を取り下げる。"""
    d = db.get(DisposalRequest, dr_id)
    if not d:
        raise HTTPException(404, "申請が見つかりません")
    if d.requester_id != user.id and not user.is_admin:
        raise HTTPException(403, "本人の申請だけ取り下げられます")
    claim(db, DisposalRequest, dr_id, to_status="CANCELLED")
    db.commit()


@router.post("/{dr_id}/approve", response_model=DROut)
def approve_dr(dr_id: int, body: DRApprove, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)) -> DROut:
    d = db.get(DisposalRequest, dr_id)
    if not d:
        raise HTTPException(404, "申請が見つかりません")
    require_reason(body.approve, body.reject_reason)
    claim(db, DisposalRequest, dr_id, to_status="APPROVED" if body.approve else "REJECTED")
    if body.approve:
        try:
            process_dispose(db, actor_of(user), item_id=d.item_id, quantity=d.quantity,
                            reason=f"廃棄申請 #{d.id}：{d.reason}", ref=("DR", d.id))
        except StockError as e:
            db.rollback()
            raise HTTPException(400, str(e)) from e
    else:
        d.reject_reason = body.reject_reason
    d.approved_by = user.id
    d.approved_at = jst_now()
    db.commit()
    return _out(_rows(db).filter(DisposalRequest.id == dr_id).one())


# ---------- ゲストから部署への連絡（I-08） ----------
notices_router = APIRouter(prefix="/disposal-notices", tags=["disposal-notices"])


class NoticeCreate(BaseModel):
    item_id: int
    quantity: int = Field(ge=1)
    reason: ReqStr = Field(max_length=512)


class NoticePromote(BaseModel):
    """正式な申請に上げるときに直せる。空なら連絡の内容のまま。"""

    quantity: int | None = Field(default=None, ge=1)
    reason: OptStr = Field(default=None, max_length=512)


class NoticeDismiss(BaseModel):
    comment: OptStr = Field(default=None, max_length=512)


class NoticeOut(BaseModel):
    id: int
    item_id: int
    item_name: str
    unit: str
    quantity: int
    current_stock: int
    reason: str
    reporter: str
    reporter_id: int
    department_id: int
    department: str | None
    status: str
    handled_by: str | None
    handled_comment: str | None
    disposal_request_id: int | None
    created_at: str
    handled_at: str | None


def _notice_rows(db: Session):
    handler = aliased(User)
    return (
        db.query(DisposalNotice, Item.item_name, Item.unit, Inventory.quantity, User.display_name, Department.name,
                 handler.display_name)
        .join(Item, Item.id == DisposalNotice.item_id)
        .outerjoin(Inventory, Inventory.item_id == DisposalNotice.item_id)
        .join(User, User.id == DisposalNotice.reporter_id)
        .outerjoin(Department, Department.id == DisposalNotice.department_id)
        .outerjoin(handler, handler.id == DisposalNotice.handled_by)
    )


def _notice_out(row) -> NoticeOut:  # noqa: ANN001
    n, name, unit, stock, reporter, dept, handler = row
    return NoticeOut(
        id=n.id, item_id=n.item_id, item_name=name, unit=unit or "個", quantity=n.quantity, current_stock=stock or 0,
        reason=n.reason, reporter=reporter, reporter_id=n.reporter_id, department_id=n.department_id, department=dept,
        status=n.status, handled_by=handler, handled_comment=n.handled_comment, disposal_request_id=n.disposal_request_id,
        created_at=n.created_at.isoformat(timespec="seconds") if n.created_at else "",
        handled_at=n.handled_at.isoformat(timespec="seconds") if n.handled_at else None,
    )


def _notice_one(db: Session, nid: int) -> NoticeOut:
    return _notice_out(_notice_rows(db).filter(DisposalNotice.id == nid).one())


def _get_notice(db: Session, nid: int) -> DisposalNotice:
    n = db.get(DisposalNotice, nid)
    if not n:
        raise HTTPException(404, "連絡が見つかりません")
    return n


def _check_handler(user: CurrentUser, n: DisposalNotice) -> None:
    if not same_department(user, n.department_id):
        raise HTTPException(403, "ほかの部署への連絡は処理できません")


@notices_router.get("", response_model=Page[NoticeOut])
def list_notices(
    status: str | None = None,
    scope: Scope | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Page[NoticeOut]:
    """ゲストは本人の連絡、一般は自分の部署への連絡、管理者は全部署（切り替えで自分の部署）。"""
    q = _notice_rows(db)
    if user.is_guest:
        q = q.filter(DisposalNotice.reporter_id == user.id)
    elif not user.is_admin or resolve(user, scope) == "dept":
        q = q.filter(DisposalNotice.department_id == user.department_id)
    if status:
        q = q.filter(DisposalNotice.status == status)
    total = q.count()
    rows = (
        q.order_by(DisposalNotice.created_at.desc(), DisposalNotice.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return Page[NoticeOut](items=[_notice_out(r) for r in rows], total=total, page=page, per_page=per_page)


@notices_router.post("", response_model=NoticeOut, status_code=201)
def create_notice(body: NoticeCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> NoticeOut:
    if not user.is_guest:
        raise HTTPException(403, "部署への連絡はゲスト用です。廃棄申請を使ってください")
    if user.department_id is None:
        raise HTTPException(400, "部署が設定されていないため連絡できません。管理者に部署の設定を依頼してください")
    require_visible_to_guest(user, db.get(Item, body.item_id))
    try:
        item, inv = lock_inventory(db, body.item_id)
        check_outbound(item, inv, body.quantity, verb="廃棄")
    except StockError as e:
        raise HTTPException(400, str(e)) from e
    n = DisposalNotice(
        item_id=body.item_id, quantity=body.quantity, reason=body.reason, reporter_id=user.id,
        department_id=user.department_id, status="OPEN", created_at=jst_now(),
    )
    db.add(n)
    db.commit()
    return _notice_one(db, n.id)


@notices_router.post("/{nid}/promote", response_model=NoticeOut)
def promote_notice(nid: int, body: NoticePromote, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> NoticeOut:
    """正式な廃棄申請に上げる。申請者＝上げた人、部署＝連絡したゲストの部署。"""
    n = _get_notice(db, nid)
    _check_handler(user, n)
    claim(db, DisposalNotice, nid, to_status="PROMOTED", from_statuses=("OPEN",))
    d = _new_request(db, user, item_id=n.item_id, quantity=body.quantity or n.quantity, reason=body.reason or n.reason,
                     department_id=n.department_id)
    n.disposal_request_id = d.id
    n.handled_by = user.id
    n.handled_at = jst_now()
    db.commit()
    return _notice_one(db, nid)


@notices_router.post("/{nid}/dismiss", response_model=NoticeOut)
def dismiss_notice(nid: int, body: NoticeDismiss, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> NoticeOut:
    n = _get_notice(db, nid)
    _check_handler(user, n)
    claim(db, DisposalNotice, nid, to_status="DISMISSED", from_statuses=("OPEN",))
    n.handled_by = user.id
    n.handled_at = jst_now()
    n.handled_comment = body.comment
    db.commit()
    return _notice_one(db, nid)


@notices_router.delete("/{nid}", status_code=204)
def withdraw_notice(nid: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    """連絡したゲスト本人が、未対応の間だけ取り下げる。"""
    n = _get_notice(db, nid)
    if n.reporter_id != user.id:
        raise HTTPException(403, "本人の連絡だけ取り下げられます")
    claim(db, DisposalNotice, nid, to_status="CANCELLED", from_statuses=("OPEN",))
    db.commit()

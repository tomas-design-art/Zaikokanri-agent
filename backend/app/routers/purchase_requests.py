"""Purchase requests (発注申請) router（C-04〜C-08）。

状態：PENDING(保留中) → APPROVED(承認済) → ORDERED(発注済・一部受領) → RECEIVED(受領済)
      PENDING / ON_HOLD(保留) / APPROVED の間は REJECTED(却下) にもできる。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin, require_user
from app.db import get_db
from app.models import Department, Inventory, Item, PurchaseCandidate, PurchaseRequest, User
from app.schemas.common import OptDate, OptStr, Page
from app.services.scope import Scope, request_filter
from app.utils.datetime import jst_now

router = APIRouter(prefix="/purchase-requests", tags=["purchase-requests"])

Priority = Literal["LOW", "NORMAL", "HIGH", "URGENT"]
DecisionStatus = Literal["PENDING", "ON_HOLD", "APPROVED", "REJECTED"]
EDITABLE_BY_REQUESTER = {"PENDING", "ON_HOLD"}
DECIDABLE = {"PENDING", "ON_HOLD", "APPROVED"}
RECEIVABLE = ("APPROVED", "ORDERED")
BEFORE_APPROVAL = ("PENDING", "ON_HOLD")
ALREADY_DECIDED = "ほかの人が先にこの申請を処理しました。画面を更新してください"


class PRCreate(BaseModel):
    item_id: int
    requested_qty: int = Field(ge=1, le=100_000)
    priority: Priority = "NORMAL"
    due_date: OptDate = None
    note: OptStr = Field(default=None, max_length=512)


class PRBulkCreate(BaseModel):
    items: list[PRCreate] = Field(min_length=1, max_length=200)


class PRUpdate(BaseModel):
    requested_qty: int | None = Field(default=None, ge=1, le=100_000)
    priority: Priority | None = None
    due_date: OptDate = None
    note: OptStr = Field(default=None, max_length=512)
    status: DecisionStatus | None = None
    admin_comment: OptStr = Field(default=None, max_length=512)


class PROut(BaseModel):
    id: int
    item_id: int
    item_name: str
    unit: str
    vendor_name: str | None
    requested_qty: int
    priority: str
    due_date: str | None
    note: str | None
    requested_by: str
    requested_by_user_id: int
    requested_by_department: str | None
    status: str
    admin_comment: str | None
    received_qty: int
    remaining_qty: int
    received_at: str | None
    created_at: str


def _rows(db: Session):
    return (
        db.query(PurchaseRequest, Item, User.display_name)
        .join(Item, Item.id == PurchaseRequest.item_id)
        .join(User, User.id == PurchaseRequest.requested_by_user_id)
        .filter(PurchaseRequest.deleted_at.is_(None))
    )


def _out(row) -> PROut:  # noqa: ANN001
    pr, item, who = row
    received = pr.received_qty or 0
    return PROut(
        id=pr.id, item_id=pr.item_id, item_name=item.item_name, unit=item.unit or "個", vendor_name=item.vendor_name,
        requested_qty=pr.requested_qty, priority=pr.priority, due_date=pr.due_date, note=pr.note,
        requested_by=who, requested_by_user_id=pr.requested_by_user_id,
        requested_by_department=pr.requested_by_department, status=pr.status, admin_comment=pr.admin_comment,
        received_qty=received, remaining_qty=max(pr.requested_qty - received, 0),
        received_at=pr.received_at.isoformat(timespec="seconds") if pr.received_at else None,
        created_at=pr.created_at.isoformat(timespec="seconds") if pr.created_at else "",
    )


def _one(db: Session, pr_id: int) -> PROut:
    return _out(_rows(db).filter(PurchaseRequest.id == pr_id).one())


@router.get("", response_model=Page[PROut])
def list_pr(
    status: str | None = None,
    mine: bool = False,
    receivable: bool = False,
    scope: Scope | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_user),
) -> Page[PROut]:
    """一般の既定は自分の部署の申請＋自分の申請、切り替えで全部署（I-10）。ゲストは使えない（業者が載るため：I-09）。"""
    query = _rows(db)
    cond = request_filter(user, scope, PurchaseRequest.department_id, PurchaseRequest.requested_by_user_id)
    if cond is not None:
        query = query.filter(cond)
    if status:
        query = query.filter(PurchaseRequest.status == status)
    if receivable:
        query = query.filter(PurchaseRequest.status.in_(RECEIVABLE))
    if mine:
        query = query.filter(PurchaseRequest.requested_by_user_id == user.id)
    total = query.count()
    rows = query.order_by(PurchaseRequest.created_at.desc(), PurchaseRequest.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return Page[PROut](items=[_out(r) for r in rows], total=total, page=page, per_page=per_page)


def _create(db: Session, user: CurrentUser, body: PRCreate) -> PurchaseRequest:
    item = db.get(Item, body.item_id)
    if not item or not item.is_active:
        raise HTTPException(400, "対象の物品が見つからないか、無効になっています")
    pr = PurchaseRequest(
        item_id=body.item_id, requested_qty=body.requested_qty, priority=body.priority, due_date=body.due_date,
        note=body.note, requested_by_user_id=user.id, requested_by_department=user.department,
        department_id=user.department_id, status="PENDING", received_qty=0, created_at=jst_now(),
    )
    db.add(pr)
    db.flush()
    return pr


@router.post("", response_model=PROut, status_code=201)
def create_pr(body: PRCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> PROut:
    pr = _create(db, user, body)
    db.commit()
    return _one(db, pr.id)


@router.post("/bulk", response_model=list[PROut], status_code=201)
def bulk_create_pr(body: PRBulkCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> list[PROut]:
    """アラートの在庫不足からまとめて申請する（C-08）。"""
    ids = [_create(db, user, line).id for line in body.items]
    db.commit()
    return [_one(db, i) for i in ids]


class SummaryDept(BaseModel):
    department: str
    qty: int


class SummaryGroup(BaseModel):
    item_id: int
    item_name: str
    unit: str
    vendor_name: str | None
    current_stock: int
    total_qty: int
    departments: list[SummaryDept]
    requests: list[PROut]


@router.get("/summary", response_model=list[SummaryGroup])
def summary(db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> list[SummaryGroup]:
    """同じ物品の申請のまとめ（I-11）：承認前の申請を物品ごとに、合計・部署別の内訳・今の在庫。"""
    rows = _rows(db).filter(PurchaseRequest.status.in_(BEFORE_APPROVAL)).order_by(PurchaseRequest.created_at, PurchaseRequest.id).all()
    stock = dict(db.query(Inventory.item_id, Inventory.quantity).filter(Inventory.item_id.in_({r[1].id for r in rows})).all())
    depts = dict(db.query(Department.id, Department.name).all())
    groups: dict[int, SummaryGroup] = {}
    by_dept: dict[int, dict[str, int]] = {}
    for row in rows:
        pr, item, _who = row
        g = groups.get(item.id)
        if g is None:
            g = groups[item.id] = SummaryGroup(
                item_id=item.id, item_name=item.item_name, unit=item.unit or "個", vendor_name=item.vendor_name,
                current_stock=stock.get(item.id, 0), total_qty=0, departments=[], requests=[],
            )
            by_dept[item.id] = {}
        g.total_qty += pr.requested_qty
        g.requests.append(_out(row))
        name = depts.get(pr.department_id) or pr.requested_by_department or "(未設定)"
        by_dept[item.id][name] = by_dept[item.id].get(name, 0) + pr.requested_qty
    for item_id, g in groups.items():
        g.departments = [SummaryDept(department=k, qty=v) for k, v in by_dept[item_id].items()]
    # 部署が多い（まとめる意味がある）物品から
    return sorted(groups.values(), key=lambda g: (-len(g.departments), -len(g.requests), g.item_name))


class BulkDecide(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    status: Literal["APPROVED", "REJECTED"]
    admin_comment: OptStr = Field(default=None, max_length=512)


@router.post("/bulk-decide", response_model=list[PROut])
def bulk_decide(body: BulkDecide, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)) -> list[PROut]:
    """選んだ申請をまとめて承認・却下する（I-11）。1件でも処理済み・見つからなければ全部取りやめ（409）。"""
    ids = sorted(set(body.ids))
    values = {"status": body.status, "approved_by": user.id, "approved_at": jst_now(), "updated_at": jst_now()}
    if body.admin_comment:
        values["admin_comment"] = body.admin_comment
    res = db.execute(
        update(PurchaseRequest)
        .where(PurchaseRequest.id.in_(ids), PurchaseRequest.status.in_(BEFORE_APPROVAL), PurchaseRequest.deleted_at.is_(None))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != len(ids):
        db.rollback()
        raise HTTPException(409, ALREADY_DECIDED)
    db.commit()
    return [_one(db, i) for i in ids]


@router.patch("/{pr_id}", response_model=PROut)
def update_pr(pr_id: int, body: PRUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> PROut:
    pr = db.get(PurchaseRequest, pr_id)
    if not pr or pr.deleted_at:
        raise HTTPException(404, "申請が見つかりません")
    data = body.model_dump(exclude_unset=True)
    if not user.is_admin:
        if "status" in data or "admin_comment" in data:
            raise HTTPException(403, "承認・却下は管理者だけができます")
        if pr.requested_by_user_id != user.id:
            raise HTTPException(403, "他の人の申請は編集できません")
        if pr.status not in EDITABLE_BY_REQUESTER:
            raise HTTPException(400, "承認された後の申請は編集できません")
    elif pr.status not in DECIDABLE:
        raise HTTPException(400, "発注済・受領済・却下済の申請は変更できません")
    values = {k: v for k, v in data.items() if not (v is None and k in {"requested_qty", "priority", "status"})}
    if values.get("status") in {"APPROVED", "REJECTED"}:
        values |= {"approved_by": user.id, "approved_at": jst_now()}
    if values:
        # 読んだ時点の状態のままのときだけ更新する（申請者の編集と管理者の承認が同時でも食い違わない：H-06）
        allowed_now = DECIDABLE if user.is_admin else EDITABLE_BY_REQUESTER
        res = db.execute(
            update(PurchaseRequest)
            .where(PurchaseRequest.id == pr_id, PurchaseRequest.status.in_(allowed_now))
            .values(**values, updated_at=jst_now())
            .execution_options(synchronize_session=False)
        )
        if res.rowcount != 1:
            db.rollback()
            raise HTTPException(409, ALREADY_DECIDED)
    db.commit()
    return _one(db, pr_id)


@router.delete("/{pr_id}", status_code=204)
def delete_pr(pr_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> None:
    pr = db.get(PurchaseRequest, pr_id)
    if not pr or pr.deleted_at:
        raise HTTPException(404, "申請が見つかりません")
    if not user.is_admin and pr.requested_by_user_id != user.id:
        raise HTTPException(403, "本人の申請だけ取り下げられます")
    allowed = DECIDABLE | {"REJECTED"} if user.is_admin else EDITABLE_BY_REQUESTER
    if pr.status not in allowed:
        raise HTTPException(400, "発注済・受領済の申請は取り下げられません")
    pr.deleted_at = jst_now()
    pr.deleted_by = user.id
    db.commit()


# ---------- Candidates (admin・画面なし。旧版から残している API) ----------
class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    item_name: str
    auto_reason: str | None
    selected_for_order: int
    deferred: int
    priority: str
    recommended_qty: int | None
    note: str | None
    status: str


class CandidateUpdate(BaseModel):
    selected_for_order: int | None = None
    deferred: int | None = None
    priority: Priority | None = None
    recommended_qty: int | None = Field(default=None, ge=0)
    note: OptStr = None
    status: Literal["OPEN", "SELECTED", "DEFERRED", "ORDERED"] | None = None


candidates_router = APIRouter(prefix="/purchase-candidates", tags=["purchase-candidates"])


def _cand_out(c: PurchaseCandidate, name: str) -> CandidateOut:
    return CandidateOut(
        id=c.id, item_id=c.item_id, item_name=name, auto_reason=c.auto_reason, selected_for_order=c.selected_for_order,
        deferred=c.deferred, priority=c.priority, recommended_qty=c.recommended_qty, note=c.note, status=c.status,
    )


@candidates_router.get("", response_model=list[CandidateOut])
def list_candidates(status: str | None = "OPEN", db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> list[CandidateOut]:
    query = db.query(PurchaseCandidate, Item.item_name).join(Item, Item.id == PurchaseCandidate.item_id)
    if status:
        query = query.filter(PurchaseCandidate.status == status)
    return [_cand_out(c, name) for c, name in query.all()]


@candidates_router.patch("/{cid}", response_model=CandidateOut)
def update_candidate(cid: int, body: CandidateUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)) -> CandidateOut:
    c = db.get(PurchaseCandidate, cid)
    if not c:
        raise HTTPException(404, "候補が見つかりません")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_by_user_id = user.id
    db.commit()
    db.refresh(c)
    item = db.get(Item, c.item_id)
    return _cand_out(c, item.item_name if item else "")

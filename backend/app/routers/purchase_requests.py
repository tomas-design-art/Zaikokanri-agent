"""Purchase requests (発注申請) router — request + admin approval + candidate selection."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin, require_user
from app.db import get_db
from app.models import Item, PurchaseCandidate, PurchaseRequest, User
from app.schemas.common import Page
from app.utils.datetime import jst_now

router = APIRouter(prefix="/purchase-requests", tags=["purchase-requests"])


class PRCreate(BaseModel):
    item_id: int
    requested_qty: int = Field(ge=1)
    priority: str = "NORMAL"
    due_date: str | None = None
    note: str | None = None


class PRUpdate(BaseModel):
    requested_qty: int | None = Field(default=None, ge=1)
    priority: str | None = None
    due_date: str | None = None
    note: str | None = None
    status: str | None = None
    admin_comment: str | None = None


class PROut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    item_name: str
    requested_qty: int
    priority: str
    due_date: str | None
    note: str | None
    requested_by: str
    requested_by_department: str | None
    status: str
    admin_comment: str | None
    received_qty: int
    received_at: str | None
    created_at: str


def _to_out(pr: PurchaseRequest, item_name: str, requester_name: str) -> PROut:
    return PROut(
        id=pr.id,
        item_id=pr.item_id,
        item_name=item_name,
        requested_qty=pr.requested_qty,
        priority=pr.priority,
        due_date=pr.due_date,
        note=pr.note,
        requested_by=requester_name,
        requested_by_department=pr.requested_by_department,
        status=pr.status,
        admin_comment=pr.admin_comment,
        received_qty=pr.received_qty or 0,
        received_at=pr.received_at.isoformat() if pr.received_at else None,
        created_at=pr.created_at.isoformat() if pr.created_at else "",
    )


@router.get("", response_model=Page[PROut])
def list_pr(
    status: str | None = None,
    mine: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Page[PROut]:
    query = db.query(PurchaseRequest, Item.item_name, User.display_name).join(
        Item, Item.id == PurchaseRequest.item_id
    ).join(User, User.id == PurchaseRequest.requested_by_user_id).filter(
        PurchaseRequest.deleted_at == None  # noqa: E711
    )
    if status:
        query = query.filter(PurchaseRequest.status == status)
    if mine:
        query = query.filter(PurchaseRequest.requested_by_user_id == user.id)
    total = query.count()
    rows = (
        query.order_by(PurchaseRequest.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return Page[PROut](
        items=[_to_out(pr, name, who) for pr, name, who in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=PROut, status_code=201)
def create_pr(
    body: PRCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_user),
) -> PROut:
    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    pr = PurchaseRequest(
        item_id=body.item_id,
        requested_qty=body.requested_qty,
        priority=body.priority,
        due_date=body.due_date,
        note=body.note,
        requested_by_user_id=user.id,
        requested_by_department=user.department,
        status="PENDING",
        created_at=jst_now(),
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return _to_out(pr, item.item_name, user.display_name)


@router.patch("/{pr_id}", response_model=PROut)
def update_pr(
    pr_id: int,
    body: PRUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> PROut:
    pr = db.get(PurchaseRequest, pr_id)
    if not pr or pr.deleted_at:
        raise HTTPException(404, "Not found")
    # Status changes & admin_comment require ADMIN
    data = body.model_dump(exclude_unset=True)
    if ("status" in data or "admin_comment" in data) and not user.is_admin:
        raise HTTPException(403, "管理者のみ承認操作が可能です")
    if not user.is_admin and pr.requested_by_user_id != user.id:
        raise HTTPException(403, "他者の申請は編集できません")
    if "status" in data and data["status"] in {"APPROVED", "REJECTED"} and user.is_admin:
        pr.approved_by = user.id
        pr.approved_at = jst_now()
    for k, v in data.items():
        setattr(pr, k, v)
    db.commit()
    db.refresh(pr)
    item = db.get(Item, pr.item_id)
    requester = db.get(User, pr.requested_by_user_id)
    return _to_out(pr, item.item_name if item else "", requester.display_name if requester else "")


@router.delete("/{pr_id}", status_code=204)
def delete_pr(
    pr_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    pr = db.get(PurchaseRequest, pr_id)
    if not pr or pr.deleted_at:
        raise HTTPException(404, "Not found")
    if not user.is_admin and pr.requested_by_user_id != user.id:
        raise HTTPException(403, "Forbidden")
    pr.deleted_at = jst_now()
    pr.deleted_by = user.id
    db.commit()


# ---------- Candidates (admin) ----------
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
    priority: str | None = None
    recommended_qty: int | None = None
    note: str | None = None
    status: str | None = None


candidates_router = APIRouter(prefix="/purchase-candidates", tags=["purchase-candidates"])


@candidates_router.get("", response_model=list[CandidateOut])
def list_candidates(
    status: str | None = "OPEN",
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_admin),
) -> list[CandidateOut]:
    query = db.query(PurchaseCandidate, Item.item_name).join(Item, Item.id == PurchaseCandidate.item_id)
    if status:
        query = query.filter(PurchaseCandidate.status == status)
    out = []
    for c, name in query.all():
        out.append(
            CandidateOut(
                id=c.id,
                item_id=c.item_id,
                item_name=name,
                auto_reason=c.auto_reason,
                selected_for_order=c.selected_for_order,
                deferred=c.deferred,
                priority=c.priority,
                recommended_qty=c.recommended_qty,
                note=c.note,
                status=c.status,
            )
        )
    return out


@candidates_router.patch("/{cid}", response_model=CandidateOut)
def update_candidate(
    cid: int,
    body: CandidateUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
) -> CandidateOut:
    c = db.get(PurchaseCandidate, cid)
    if not c:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_by_user_id = user.id
    db.commit()
    db.refresh(c)
    item = db.get(Item, c.item_id)
    return CandidateOut(
        id=c.id,
        item_id=c.item_id,
        item_name=item.item_name if item else "",
        auto_reason=c.auto_reason,
        selected_for_order=c.selected_for_order,
        deferred=c.deferred,
        priority=c.priority,
        recommended_qty=c.recommended_qty,
        note=c.note,
        status=c.status,
    )


# `candidates_router` is exposed separately so its `/purchase-candidates` prefix is at root.

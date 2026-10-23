"""Stocktake (棚卸し) router — セッション・実数入力・確定（在庫へ反映）・Excel 出力。"""
from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin, require_user
from app.db import get_db
from app.models import StocktakeSession, User
from app.schemas.common import OptDate, OptStr, ReqStr
from app.services import stocktake_service as svc
from app.services.stock_service import actor_of
from app.services.stocktake_export import render_stocktake_excel

router = APIRouter(prefix="/stocktake", tags=["stocktake"])


class SessionCreate(BaseModel):
    name: ReqStr = Field(max_length=128)
    start_date: OptDate = None
    end_date: OptDate = None
    note: OptStr = None
    category: OptStr = None


class SummaryOut(BaseModel):
    total: int
    counted: int
    uncounted: int
    matched: int
    diff: int


class SessionOut(BaseModel):
    id: int
    name: str
    start_date: str | None
    end_date: str | None
    status: str
    note: str | None
    category: str | None
    created_by: str | None
    created_at: str
    closed_at: str | None
    summary: SummaryOut


class RecordOut(BaseModel):
    id: int
    session_id: int
    item_id: int
    item_name: str
    item_code: str | None
    category: str
    location: str | None
    unit: str
    system_qty: int
    actual_qty: int | None
    diff_qty: int | None
    status: str
    note: str | None
    counted_by: str | None
    counted_at: str | None


class RecordUpdate(BaseModel):
    # None を送ると「未カウント」に戻す。状態はサーバーが決める（D-03）
    actual_qty: int | None = Field(default=None, ge=0, le=10_000_000)
    note: OptStr = Field(default=None, max_length=512)


class ApplyResult(BaseModel):
    applied: int
    adjusted: int
    uncounted: int


def _session_out(db: Session, s: StocktakeSession) -> SessionOut:
    creator = db.get(User, s.created_by) if s.created_by else None
    return SessionOut(
        id=s.id, name=s.name, start_date=s.start_date, end_date=s.end_date, status=s.status, note=s.note,
        category=s.scope_category, created_by=creator.display_name if creator else None,
        created_at=s.created_at.isoformat(timespec="seconds") if s.created_at else "",
        closed_at=s.closed_at.isoformat(timespec="seconds") if s.closed_at else None,
        summary=SummaryOut(**asdict(svc.summarize(db, s.id))),
    )


def _record_out(row) -> RecordOut:  # noqa: ANN001
    r, item, counter = row
    return RecordOut(
        id=r.id, session_id=r.session_id, item_id=r.item_id, item_name=item.item_name, item_code=item.item_code,
        category=item.category, location=item.location_text, unit=item.unit or "個", system_qty=r.system_qty,
        actual_qty=r.actual_qty, diff_qty=r.diff_qty, status=r.status, note=r.note, counted_by=counter,
        counted_at=r.counted_at.isoformat(timespec="seconds") if r.counted_at else None,
    )


def _get_session(db: Session, sid: int) -> StocktakeSession:
    s = db.get(StocktakeSession, sid)
    if not s:
        raise HTTPException(404, "棚卸しが見つかりません")
    return s


# ---------- Sessions ----------
@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> list[SessionOut]:
    rows = db.query(StocktakeSession).order_by(StocktakeSession.id.desc()).limit(100).all()
    return [_session_out(db, s) for s in rows]


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)) -> SessionOut:
    s = svc.create_session(
        db, name=body.name, note=body.note, category=body.category, user_id=user.id,
        start_date=body.start_date, end_date=body.end_date,
    )
    db.commit()
    return _session_out(db, s)


@router.get("/sessions/{sid}", response_model=SessionOut)
def get_session(sid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> SessionOut:
    return _session_out(db, _get_session(db, sid))


@router.post("/sessions/{sid}/refresh-items")
def refresh_items(sid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> dict[str, int]:
    added = svc.refresh_items(db, sid)
    db.commit()
    return {"added": added}


@router.post("/sessions/{sid}/apply", response_model=ApplyResult)
def apply_session(sid: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)) -> ApplyResult:
    """差異を在庫に反映して完了にする（D-01）。"""
    result = svc.apply_session(db, sid, actor_of(user))
    db.commit()
    return ApplyResult(**result)


@router.post("/sessions/{sid}/cancel", response_model=SessionOut)
def cancel_session(sid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> SessionOut:
    svc.cancel_session(db, sid)
    db.commit()
    return _session_out(db, _get_session(db, sid))


# ---------- Records ----------
@router.get("/sessions/{sid}/records", response_model=list[RecordOut])
def list_records(
    sid: int,
    q: str | None = None,
    only: Literal["uncounted", "diff"] | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[RecordOut]:
    _get_session(db, sid)
    return [_record_out(r) for r in svc.list_records(db, sid, q=q, only=only)]


@router.patch("/records/{rid}", response_model=RecordOut)
def update_record(rid: int, body: RecordUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)) -> RecordOut:
    r = svc.record_count(db, rid, user_id=user.id, **body.model_dump(exclude_unset=True))
    db.commit()
    return _record_out(next(x for x in svc.list_records(db, r.session_id) if x[0].id == rid))


@router.get("/sessions/{sid}/export.xlsx")
def export_session_excel(sid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> StreamingResponse:
    sess = _get_session(db, sid)
    rows = [_record_out(r) for r in svc.list_records(db, sid)]
    summary = svc.summarize(db, sid)
    info = {
        "name": sess.name,
        "status": svc.SESSION_STATUS_LABELS.get(sess.status, sess.status),
        "started_at": sess.created_at.isoformat(sep=" ", timespec="minutes") if sess.created_at else "",
        "category": sess.scope_category or "すべて",
    }
    data = render_stocktake_excel([r.model_dump() for r in rows], info, asdict(summary))
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stocktake_{sid}.xlsx"'},
    )

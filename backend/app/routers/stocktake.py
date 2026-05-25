"""Stocktake (棚卸) router — sessions, records, templates, summary."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_admin
from app.db import get_db
from app.models import Inventory, Item, StocktakeRecord, StocktakeSession
from app.services.stocktake_export import render_stocktake_excel
from app.utils.datetime import jst_now

router = APIRouter(prefix="/stocktake", tags=["stocktake"])


# ---------- Sessions ----------
class SessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    start_date: str | None = None
    end_date: str | None = None
    note: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    start_date: str | None
    end_date: str | None
    status: str
    note: str | None


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> list[SessionOut]:
    return [SessionOut.model_validate(s) for s in db.query(StocktakeSession).order_by(StocktakeSession.id.desc()).all()]


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)
) -> SessionOut:
    s = StocktakeSession(
        name=body.name,
        start_date=body.start_date,
        end_date=body.end_date,
        note=body.note,
        status="OPEN",
        created_by=user.id,
    )
    db.add(s)
    db.flush()
    # seed records for all active inventory items
    items = (
        db.query(Item, Inventory)
        .join(Inventory, Inventory.item_id == Item.id)
        .filter(Item.is_active == 1, Item.is_inventory_target == 1)
        .all()
    )
    for it, inv in items:
        db.add(StocktakeRecord(session_id=s.id, item_id=it.id, system_qty=inv.quantity, status="PENDING"))
    db.commit()
    db.refresh(s)
    return SessionOut.model_validate(s)


@router.post("/sessions/{sid}/close", response_model=SessionOut)
def close_session(sid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> SessionOut:
    s = db.get(StocktakeSession, sid)
    if not s:
        raise HTTPException(404, "Not found")
    s.status = "CLOSED"
    s.closed_at = jst_now()
    db.commit()
    db.refresh(s)
    return SessionOut.model_validate(s)


# ---------- Records ----------
class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    item_id: int
    item_name: str
    system_qty: int
    actual_qty: int | None
    diff_qty: int | None
    status: str
    note: str | None


class RecordUpdate(BaseModel):
    actual_qty: int | None = Field(default=None, ge=0)
    note: str | None = None
    status: str | None = None


@router.get("/sessions/{sid}/records", response_model=list[RecordOut])
def list_records(
    sid: int, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)
) -> list[RecordOut]:
    rows = (
        db.query(StocktakeRecord, Item.item_name)
        .join(Item, Item.id == StocktakeRecord.item_id)
        .filter(StocktakeRecord.session_id == sid)
        .all()
    )
    return [
        RecordOut(
            id=r.id,
            session_id=r.session_id,
            item_id=r.item_id,
            item_name=name,
            system_qty=r.system_qty,
            actual_qty=r.actual_qty,
            diff_qty=r.diff_qty,
            status=r.status,
            note=r.note,
        )
        for r, name in rows
    ]


@router.patch("/records/{rid}", response_model=RecordOut)
def update_record(
    rid: int,
    body: RecordUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RecordOut:
    r = db.get(StocktakeRecord, rid)
    if not r:
        raise HTTPException(404, "Not found")
    data = body.model_dump(exclude_unset=True)
    if "actual_qty" in data:
        r.actual_qty = data["actual_qty"]
        r.diff_qty = (r.actual_qty or 0) - r.system_qty
        r.counted_by = user.id
        r.counted_at = jst_now()
    if "note" in data:
        r.note = data["note"]
    if "status" in data:
        r.status = data["status"]
    db.commit()
    db.refresh(r)
    item = db.get(Item, r.item_id)
    return RecordOut(
        id=r.id,
        session_id=r.session_id,
        item_id=r.item_id,
        item_name=item.item_name if item else "",
        system_qty=r.system_qty,
        actual_qty=r.actual_qty,
        diff_qty=r.diff_qty,
        status=r.status,
        note=r.note,
    )


@router.get("/sessions/{sid}/export.xlsx")
def export_session_excel(
    sid: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    sess = db.get(StocktakeSession, sid)
    if not sess:
        raise HTTPException(404, "Session not found")
    rows = (
        db.query(StocktakeRecord, Item.item_name)
        .join(Item, Item.id == StocktakeRecord.item_id)
        .filter(StocktakeRecord.session_id == sid)
        .all()
    )
    data_rows = [
        {
            "item_name": name,
            "system_qty": r.system_qty,
            "actual_qty": r.actual_qty,
            "diff_qty": r.diff_qty,
            "status": r.status,
            "note": r.note,
        }
        for r, name in rows
    ]
    counted = sum(1 for r in data_rows if r["actual_qty"] is not None)
    surplus = sum(1 for r in data_rows if isinstance(r["diff_qty"], int) and r["diff_qty"] > 0)
    shortage = sum(1 for r in data_rows if isinstance(r["diff_qty"], int) and r["diff_qty"] < 0)
    match = sum(1 for r in data_rows if r["diff_qty"] == 0)
    summary = {
        "total_items": len(data_rows),
        "counted": counted,
        "uncounted": len(data_rows) - counted,
        "match": match,
        "surplus": surplus,
        "shortage": shortage,
    }
    session_info = {
        "name": getattr(sess, "name", ""),
        "status": sess.status,
        "started_at": getattr(sess, "started_at", "") or getattr(sess, "created_at", ""),
    }
    data = render_stocktake_excel(data_rows, session_info, summary)
    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stocktake_{sid}.xlsx"'},
    )

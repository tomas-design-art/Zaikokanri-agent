"""発注書 (Purchase Order) 生成エンドポイント。
承認済み（または発注済）の発注申請から、業者別ペイロード/メール本文/PDF/Excel を生成する。
"""
from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import PurchaseRequest
from app.services.order_service import (
    build_payloads,
    render_email_text,
    render_excel,
    render_pdf,
)

router = APIRouter(prefix="/orders", tags=["orders"])


class IdsIn(BaseModel):
    request_ids: list[int] = Field(min_length=1)


class PayloadIn(BaseModel):
    payload: dict[str, Any]


class PayloadsIn(BaseModel):
    payloads: list[dict[str, Any]] = Field(min_length=1)


@router.post("/preview")
def preview(
    body: IdsIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    payloads = build_payloads(db, body.request_ids)
    if not payloads:
        raise HTTPException(status_code=404, detail="承認済・発注済の申請が選ばれていません")
    return {"payloads": payloads}


@router.post("/mark-ordered")
def mark_ordered(
    body: IdsIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> dict[str, int]:
    """発注書を送ったら「発注済」にする（C-06）。承認済のものだけが対象。"""
    res = db.execute(
        update(PurchaseRequest)
        .where(PurchaseRequest.id.in_(body.request_ids), PurchaseRequest.status == "APPROVED",
               PurchaseRequest.deleted_at.is_(None))
        .values(status="ORDERED")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return {"updated": res.rowcount}


@router.post("/email")
def email_text(
    body: PayloadIn,
    _: object = Depends(require_admin),
) -> dict[str, str]:
    return {"email_text": render_email_text(body.payload)}


@router.post("/pdf")
def pdf(
    body: PayloadIn,
    _: object = Depends(require_admin),
) -> StreamingResponse:
    try:
        data = render_pdf(body.payload)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    vendor = (body.payload.get("vendor") or "order").replace("/", "_")
    fname = f"order_{vendor}.pdf"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=order.pdf; filename*=UTF-8''{quote(fname)}"},
    )


@router.post("/excel")
def excel(
    body: PayloadsIn,
    _: object = Depends(require_admin),
) -> StreamingResponse:
    data = render_excel(body.payloads)
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="orders.xlsx"'},
    )

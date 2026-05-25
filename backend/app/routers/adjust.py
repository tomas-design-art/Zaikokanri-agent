"""Adjust router — ADMIN only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_admin
from app.db import get_db
from app.schemas.stock import AdjustRequest, StockResultOut
from app.services.stock_service import StockError, process_adjust

router = APIRouter(prefix="/adjust", tags=["adjust"])


@router.post("", response_model=StockResultOut)
def adjust(
    body: AdjustRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_admin),
) -> StockResultOut:
    try:
        r = process_adjust(
            db,
            item_id=body.item_id,
            new_quantity=body.new_quantity,
            user_name=user.display_name,
            department=user.department,
            reason=body.reason,
        )
        db.commit()
    except StockError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return StockResultOut(**r.__dict__)

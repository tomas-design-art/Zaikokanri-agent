"""Maintenance router — ADMIN-only DB integrity tools."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_admin
from app.db import engine, get_db
from app.models import Inventory, Item

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/schema")
def schema_check(_: CurrentUser = Depends(require_admin)) -> dict:
    insp = inspect(engine)
    return {tbl: [c["name"] for c in insp.get_columns(tbl)] for tbl in insp.get_table_names()}


@router.post("/repair-inventory")
def repair_inventory(db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> dict:
    """Ensure every active item has an inventory row."""
    missing = (
        db.query(Item.id)
        .outerjoin(Inventory, Inventory.item_id == Item.id)
        .filter(Item.is_active == 1, Inventory.id == None)  # noqa: E711
        .all()
    )
    for (iid,) in missing:
        db.add(Inventory(item_id=iid, quantity=0, threshold=10))
    db.commit()
    return {"created": len(missing)}

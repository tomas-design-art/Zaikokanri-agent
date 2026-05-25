"""Demo router — populate/clear demo data (DEMO_MODE only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_admin
from app.config import settings
from app.db import get_db
from app.models import Inventory, Item

router = APIRouter(prefix="/demo", tags=["demo"])


def _ensure_demo() -> None:
    if not settings.demo_mode:
        raise HTTPException(403, "DEMO_MODE が有効ではありません")


@router.post("/seed")
def seed_demo(db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin)) -> dict:
    _ensure_demo()
    if db.query(Item).count() > 50:
        return {"skipped": True, "reason": "items already exist"}
    created = 0
    for i in range(1, 11):
        it = Item(
            item_name=f"デモ物品{i}",
            item_code=f"DEMO-{i:03d}",
            vendor_name="V001 ○○商事",
            category="事務用品",
            unit_price=100.0 * i,
        )
        db.add(it)
        db.flush()
        db.add(Inventory(item_id=it.id, quantity=10 * i, threshold=5))
        created += 1
    db.commit()
    return {"created": created}

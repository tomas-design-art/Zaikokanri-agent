"""棚卸しの業務ロジック（D-01〜D-09）。

流れ：
  1. 管理者がセッションを作る（実施中は1つだけ・カテゴリで対象を絞れる）
  2. 担当者が実数を入れる。帳簿数は「数えた時点の在庫」で記録する（D-02）
  3. 管理者が差異を確認して確定 → 差異（実数−帳簿数）を「今の在庫」に足し、履歴に STOCKTAKE を残す
     数えた後に入出庫があっても、その分は在庫にすでに入っているので狂わない
  未カウントの物品は在庫を変えない（D-09）
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models import Inventory, Item, StocktakeRecord, StocktakeSession, User
from app.services.stock_service import Actor, apply_stocktake_diff
from app.services.workflow import claim
from app.utils.datetime import jst_now
from app.utils.text import contains

OPEN, CLOSED, CANCELLED = "OPEN", "CLOSED", "CANCELLED"
SESSION_STATUS_LABELS = {OPEN: "実施中", CLOSED: "完了", CANCELLED: "中止"}


@dataclass
class Summary:
    total: int = 0
    counted: int = 0
    uncounted: int = 0
    matched: int = 0
    diff: int = 0


def summarize(db: Session, session_id: int) -> Summary:
    s = Summary()
    for actual, diff in db.query(StocktakeRecord.actual_qty, StocktakeRecord.diff_qty).filter(StocktakeRecord.session_id == session_id):
        s.total += 1
        if actual is None:
            s.uncounted += 1
            continue
        s.counted += 1
        if diff:
            s.diff += 1
        else:
            s.matched += 1
    return s


def _target_items(db: Session, category: str | None):
    q = (
        db.query(Item, Inventory)
        .join(Inventory, Inventory.item_id == Item.id)
        .filter(Item.is_active == 1, Item.is_inventory_target == 1)
    )
    if category:
        q = q.filter(Item.category == category)
    return q


def create_session(db: Session, *, name: str, note: str | None, category: str | None, user_id: int,
                   start_date: str | None = None, end_date: str | None = None) -> StocktakeSession:
    if db.query(StocktakeSession).filter(StocktakeSession.status == OPEN).first():
        raise HTTPException(409, "実施中の棚卸しがあります。完了または中止してから新しく作ってください")
    s = StocktakeSession(
        name=name, note=note, scope_category=category, start_date=start_date, end_date=end_date,
        status=OPEN, created_by=user_id, created_at=jst_now(),
    )
    db.add(s)
    db.flush()
    rows = _target_items(db, category).all()
    if not rows:
        raise HTTPException(400, "棚卸しの対象になる物品がありません")
    for item, inv in rows:
        db.add(StocktakeRecord(session_id=s.id, item_id=item.id, system_qty=inv.quantity, status="PENDING"))
    return s


def get_open_session(db: Session, sid: int) -> StocktakeSession:
    s = db.get(StocktakeSession, sid)
    if not s:
        raise HTTPException(404, "棚卸しが見つかりません")
    if s.status != OPEN:
        raise HTTPException(409, f"この棚卸しは{SESSION_STATUS_LABELS.get(s.status, s.status)}のため変更できません")
    return s


def refresh_items(db: Session, sid: int) -> int:
    """セッション作成後に増えた物品を対象に加える（D-08）。"""
    s = get_open_session(db, sid)
    have = {i for (i,) in db.query(StocktakeRecord.item_id).filter(StocktakeRecord.session_id == sid)}
    added = 0
    for item, inv in _target_items(db, s.scope_category).all():
        if item.id not in have:
            db.add(StocktakeRecord(session_id=sid, item_id=item.id, system_qty=inv.quantity, status="PENDING"))
            added += 1
    return added


UNSET = object()  # 「送られてこなかった」を None（未カウントに戻す）と区別する


def record_count(db: Session, rid: int, *, user_id: int, actual_qty=UNSET, note=UNSET) -> StocktakeRecord:  # noqa: ANN001
    r = db.get(StocktakeRecord, rid)
    if not r:
        raise HTTPException(404, "棚卸しの行が見つかりません")
    get_open_session(db, r.session_id)
    if actual_qty is None:
        r.actual_qty = r.diff_qty = r.counted_by = r.counted_at = None
        r.status = "PENDING"
    elif actual_qty is not UNSET:
        inv = db.query(Inventory).filter(Inventory.item_id == r.item_id).first()
        r.system_qty = inv.quantity if inv else 0  # 数えた時点の帳簿数（D-02）
        r.actual_qty = actual_qty
        r.diff_qty = actual_qty - r.system_qty
        r.counted_by = user_id
        r.counted_at = jst_now()
        r.status = "COUNTED"
    if note is not UNSET:
        r.note = note
    return r


def apply_session(db: Session, sid: int, actor: Actor) -> dict[str, int]:
    """差異を在庫に反映して完了にする（D-01）。2回目は 409。"""
    s = db.get(StocktakeSession, sid)
    if not s:
        raise HTTPException(404, "棚卸しが見つかりません")
    claim(db, StocktakeSession, sid, to_status=CLOSED, from_statuses=(OPEN,))
    adjusted = 0
    counted = db.query(StocktakeRecord).filter(StocktakeRecord.session_id == sid, StocktakeRecord.status == "COUNTED").all()
    for r in counted:
        if r.diff_qty:
            res = apply_stocktake_diff(
                db, actor, item_id=r.item_id, diff=r.diff_qty, session_id=sid,
                note=f"棚卸し「{s.name}」（帳簿 {r.system_qty} → 実数 {r.actual_qty}）",
            )
            adjusted += 1 if res else 0
        r.status = "APPLIED"
        r.approved_by = actor.user_id
        r.approved_at = jst_now()
    uncounted = db.query(StocktakeRecord).filter(StocktakeRecord.session_id == sid, StocktakeRecord.actual_qty.is_(None)).count()
    s.closed_at = jst_now()
    return {"applied": len(counted), "adjusted": adjusted, "uncounted": uncounted}


def cancel_session(db: Session, sid: int) -> None:
    get_open_session(db, sid)
    claim(db, StocktakeSession, sid, to_status=CANCELLED, from_statuses=(OPEN,))
    db.get(StocktakeSession, sid).closed_at = jst_now()


def list_records(db: Session, sid: int, *, q: str | None = None, only: str | None = None):
    query = (
        db.query(StocktakeRecord, Item, User.display_name)
        .join(Item, Item.id == StocktakeRecord.item_id)
        .outerjoin(User, User.id == StocktakeRecord.counted_by)
        .filter(StocktakeRecord.session_id == sid)
    )
    if q and q.strip():
        query = query.filter(contains(Item.item_name, q.strip()) | contains(Item.item_code, q.strip()))
    if only == "uncounted":
        query = query.filter(StocktakeRecord.actual_qty.is_(None))
    elif only == "diff":
        query = query.filter(StocktakeRecord.diff_qty.is_not(None), StocktakeRecord.diff_qty != 0)
    # 歩く順：保管場所 → 物品名（保管場所が未設定のものは最後）（D-04）
    return query.order_by(case((Item.location_text.is_(None), 1), else_=0), Item.location_text, Item.item_name).all()

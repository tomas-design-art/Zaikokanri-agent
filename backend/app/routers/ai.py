"""AI router — natural-language inventory query and order suggestion.

AI が作った SQL の実行可否はコードのルールで判定する（app/services/ai_query.py）。
AI の画面は一般以上（ゲストは使えない：I-09。AI の SQL は部署の絞り込みを通らないため）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_user
from app.config import settings
from app.db import get_db
from app.models import Inventory, Item
from app.services.ai_query import is_safe_sql, run_readonly_query
from app.services.scope import Scope, item_filter

router = APIRouter(prefix="/ai", tags=["ai"])


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class QueryResponse(BaseModel):
    answer: str
    sql: str | None = None
    rows: list[dict] | None = None


def _ai_unavailable() -> QueryResponse:
    return QueryResponse(
        answer="AI機能は無効化されています。OPENAI_API_KEY を設定し AI_ENABLED=true にしてください。",
    )


@router.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_user),
) -> QueryResponse:
    if not settings.ai_enabled or not settings.openai_api_key:
        return _ai_unavailable()
    try:
        from openai import OpenAI  # lazy import
    except ImportError:  # pragma: no cover
        return _ai_unavailable()

    client = OpenAI(api_key=settings.openai_api_key)
    schema_hint = (
        "Tables: items(id, item_name, item_code, vendor_name, category, expiry_date, is_active), "
        "inventory(id, item_id, quantity, threshold, location), "
        "inventory_history(id, item_id, change_type, quantity, user_name, department, created_at), "
        "departments(id, name)."
    )
    prompt = (
        f"You are a SQL assistant for an inventory system. {schema_hint}\n"
        f"Generate a single safe SELECT-only SQL (no semicolons, no DML) to answer the question. "
        f"Return ONLY the SQL.\n\nQuestion: {body.question}"
    )
    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        sql = (completion.choices[0].message.content or "").strip()
        sql = sql.strip("`").replace("```sql", "").replace("```", "").strip()
    except Exception as e:  # pragma: no cover
        raise HTTPException(502, "AIの呼び出しに失敗しました。時間をおいてお試しください") from e

    if not is_safe_sql(sql):
        return QueryResponse(answer="安全でないSQLが生成されたため実行を拒否しました。", sql=sql)
    try:
        rows = run_readonly_query(db, sql)
    except Exception as e:  # noqa: BLE001
        return QueryResponse(answer=f"SQLを実行できませんでした（{type(e).__name__}）", sql=sql)
    return QueryResponse(answer=f"結果 {len(rows)} 件（最大200件まで表示）", sql=sql, rows=rows)


class OrderSuggestion(BaseModel):
    item_id: int
    item_name: str
    current_quantity: int
    threshold: int
    suggested_qty: int
    reason: str


@router.get("/order-suggest", response_model=list[OrderSuggestion])
def order_suggest(
    scope: Scope | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)
) -> list[OrderSuggestion]:
    query = (
        db.query(Item, Inventory)
        .join(Inventory, Inventory.item_id == Item.id)
        .filter(Item.is_active == 1, Inventory.quantity <= Inventory.threshold)
    )
    visible = item_filter(user, scope)
    if visible is not None:
        query = query.filter(visible)
    rows = query.order_by(Inventory.quantity).all()
    out = []
    for it, inv in rows:
        suggested = max(it.reorder_point or inv.threshold * 2, inv.threshold * 2) - inv.quantity
        out.append(
            OrderSuggestion(
                item_id=it.id,
                item_name=it.item_name,
                current_quantity=inv.quantity,
                threshold=inv.threshold,
                suggested_qty=max(1, suggested),
                reason="在庫が閾値以下" if inv.quantity <= inv.threshold else "発注推奨",
            )
        )
    return out

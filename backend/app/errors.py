"""利用者に見せるエラーメッセージ（B-05 / B-06 / E-06）。

画面はサーバーの `detail` をそのまま表示するので、ここで日本語の一文にそろえる。
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

GENERIC_ERROR_MESSAGE = "サーバーでエラーが発生しました。時間をおいてもう一度お試しください。"

FIELD_LABELS = {
    "item_id": "物品", "item_name": "物品名", "item_code": "物品コード", "category": "カテゴリ",
    "quantity": "数量", "new_quantity": "新しい数量", "requested_qty": "数量", "received_qty": "受領数",
    "actual_qty": "実数", "initial_quantity": "初期在庫", "unit": "単位", "unit_price": "単価",
    "reorder_point": "発注点", "reason": "理由", "reject_reason": "却下理由", "note": "備考",
    "username": "ユーザー名", "password": "パスワード", "new_password": "新しいパスワード",
    "current_password": "今のパスワード", "display_name": "表示名", "user_role": "ロール",
    "vendor_code": "業者コード", "vendor_name": "業者名", "name": "名称", "expiry_date": "有効期限",
    "due_date": "希望納期", "priority": "優先度", "status": "状態", "date_from": "開始日",
    "date_to": "終了日", "items": "明細", "request_ids": "申請", "question": "質問",
    "purchase_request_id": "発注申請", "months": "月数", "email": "メール",
}


def _label(loc: tuple | list) -> str:
    for part in reversed(loc):
        if isinstance(part, str) and part not in {"body", "query", "path"}:
            return FIELD_LABELS.get(part, part)
    return "入力"


def _message(err: dict[str, Any]) -> str:
    label = _label(err.get("loc", ()))
    t = err.get("type", "")
    ctx = err.get("ctx") or {}
    if t == "missing":
        return f"{label}は必須です"
    if t == "greater_than_equal":
        return f"{label}は{ctx.get('ge')}以上で入力してください"
    if t == "greater_than":
        return f"{label}は{ctx.get('gt')}より大きい値で入力してください"
    if t == "less_than_equal":
        return f"{label}は{ctx.get('le')}以下で入力してください"
    if t == "string_too_short":
        n = ctx.get("min_length", 1)
        return f"{label}を入力してください" if n == 1 else f"{label}は{n}文字以上で入力してください"
    if t == "string_too_long":
        return f"{label}は{ctx.get('max_length')}文字以内で入力してください"
    if t == "too_short":
        return f"{label}を1件以上指定してください"
    if t in {"int_parsing", "int_type", "float_parsing", "float_type", "int_from_float"}:
        return f"{label}は数値で入力してください"
    if t in {"literal_error", "enum"}:
        return f"{label}の値が正しくありません"
    if t == "value_error":
        return str(err.get("msg", "")).removeprefix("Value error, ")
    if t in {"json_invalid", "model_attributes_type", "dict_type"}:
        return "送信内容の形式が正しくありません"
    if t in {"date_from_datetime_parsing", "date_parsing", "date_type"}:
        return f"{label}は YYYY-MM-DD の形式で入力してください（日付）"
    return f"{label}の入力内容が正しくありません"


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    messages = list(dict.fromkeys(_message(e) for e in errors))
    simple = [{"loc": e.get("loc"), "type": e.get("type"), "message": _message(e)} for e in errors]
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": " / ".join(messages[:3]), "errors": simple}),
    )


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    if getattr(orig, "sqlstate", None) == "23505":  # psycopg3
        return True
    text = str(orig).lower()
    return "unique" in text or "duplicate" in text


async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    if _is_unique_violation(exc):
        return JSONResponse(status_code=409, content={"detail": "同じ内容がすでに登録されています（重複）"})
    return JSONResponse(status_code=400, content={"detail": "関連するデータと矛盾するため保存できませんでした"})

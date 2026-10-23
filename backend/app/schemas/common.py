"""Common Pydantic schemas and reusable field types."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from app.utils.text import blank_to_none

T = TypeVar("T")


def _check_iso_date(v: str | None) -> str | None:
    if v is None:
        return None
    try:
        date.fromisoformat(v)
    except ValueError as e:
        raise ValueError("日付は YYYY-MM-DD の形式で入力してください") from e
    return v


# 空文字は None にそろえる任意の文字列（B-01）
OptStr = Annotated[str | None, BeforeValidator(blank_to_none)]
# 空文字は None、それ以外は YYYY-MM-DD だけを通す日付文字列（B-01）
OptDate = Annotated[str | None, BeforeValidator(blank_to_none), AfterValidator(_check_iso_date)]
# 前後の空白を除いた必須の文字列
ReqStr = Annotated[str, BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v), Field(min_length=1)]


def _check_password_bytes(v: str) -> str:
    # bcrypt は 72 バイトまでしか扱えない（それ以上は 500 になっていた：G-05）
    if len(v.encode("utf-8")) > 72:
        raise ValueError("パスワードは72バイト以内にしてください（英数字なら72文字、日本語なら24文字まで）")
    return v


# 新しく設定するパスワード（A-06 / G-05）
NewPassword = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_check_password_bytes)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int


class Message(BaseModel):
    detail: str


class OkResponse(BaseModel):
    ok: bool = True

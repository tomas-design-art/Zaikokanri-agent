"""申請の状態遷移の共通処理。"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

ALREADY_PROCESSED = "この申請はすでに処理されています。画面を更新してください"


def claim(db: Session, model, obj_id: int, *, to_status: str, from_statuses: tuple[str, ...] = ("PENDING",)) -> None:  # noqa: ANN001
    """「保留中なら次の状態にする」を1文の条件付き UPDATE で行う（C-01）。

    2人が同時に承認しても、行を更新できるのは先の1人だけ。後の人は 409。
    在庫の処理が失敗したら呼び出し側の rollback でこの更新も戻る。
    """
    res = db.execute(
        update(model)
        .where(model.id == obj_id, model.status.in_(from_statuses))
        .values(status=to_status)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        raise HTTPException(409, ALREADY_PROCESSED)


def require_reason(approve: bool, reason: str | None) -> None:
    if not approve and not reason:
        raise HTTPException(400, "却下理由を入力してください")

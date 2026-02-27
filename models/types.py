"""
共通データ型定義

DB操作やサービス層の戻り値に使うTypedDictを定義。
dataclass にしない理由: 既存コードが dict ベースのため互換性を優先。
"""

from typing import TypedDict, Optional, List


class OperationResult(TypedDict, total=False):
    """DB操作結果の共通型"""
    success: bool
    message: str


class OutboundResult(OperationResult, total=False):
    remaining_quantity: int


class InboundResult(OperationResult, total=False):
    new_quantity: int


class AdjustResult(OperationResult, total=False):
    old_quantity: int
    new_quantity: int


class UndoResult(OperationResult):
    pass


class ReceiveResult(OperationResult, total=False):
    item_name: str
    new_quantity: int
    history_id: int


class ItemInsertResult(OperationResult, total=False):
    item_id: int


class DemoDataResult(OperationResult, total=False):
    counts: dict


class QuantityValidation(TypedDict, total=False):
    valid: bool
    warning: str
    error: str


class PurchaseRequestCounts(TypedDict, total=False):
    pending: int
    approved: int
    on_hold: int
    rejected: int
    ordered: int


class CandidateCounts(TypedDict, total=False):
    open: int
    selected: int
    deferred: int
    ordered: int

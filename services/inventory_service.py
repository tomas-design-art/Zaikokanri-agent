"""
在庫サービス

出庫・入庫・調整の複合操作を提供する。
将来的にリポジトリからビジネスロジックを移行するための拡張ポイント。
"""

from utils.exceptions import ValidationError, InsufficientStockError, NotFoundError, ok, ng  # noqa: F401
from repositories.inventory_repo import (
    process_outbound,
    process_outbound_pending,
    process_inbound,
    get_item_by_id,
)
from repositories.history_repo import (
    process_adjust,
    process_undo,
    process_undo_pending,
)
from repositories.inventory_query import (
    get_inventory_list,
    get_total_count,
    get_categories,
    get_all_items_for_outbound,
    get_all_items_for_inbound,
    get_all_items_for_adjust,
)

__all__ = [
    'process_outbound',
    'process_outbound_pending',
    'process_inbound',
    'get_item_by_id',
    'process_adjust',
    'process_undo',
    'process_undo_pending',
    'get_inventory_list',
    'get_total_count',
    'get_categories',
    'get_all_items_for_outbound',
    'get_all_items_for_inbound',
    'get_all_items_for_adjust',
]

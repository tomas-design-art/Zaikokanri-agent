"""
在庫操作リポジトリ

出庫・入庫・在庫参照などの在庫テーブル操作を集約。
"""

from db import (
    process_outbound,
    process_outbound_pending,
    get_item_by_id,
    process_inbound,
)

__all__ = [
    'process_outbound',
    'process_outbound_pending',
    'get_item_by_id',
    'process_inbound',
]

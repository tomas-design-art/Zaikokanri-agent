"""
アラートリポジトリ

在庫不足・期限切れのアラート取得を集約。
"""

from db import (
    get_stock_alerts,
    get_expiry_alerts,
)

__all__ = [
    'get_stock_alerts',
    'get_expiry_alerts',
]

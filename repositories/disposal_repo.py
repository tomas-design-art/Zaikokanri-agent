"""
廃棄申請リポジトリ

廃棄申請のCRUD・承認/却下操作を集約。
"""

from db import (
    create_disposal_request,
    get_disposal_requests,
    approve_disposal_request,
    reject_disposal_request,
    get_disposal_count,
)

__all__ = [
    'create_disposal_request',
    'get_disposal_requests',
    'approve_disposal_request',
    'reject_disposal_request',
    'get_disposal_count',
]

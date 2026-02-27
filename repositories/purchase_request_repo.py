"""
発注申請リポジトリ

発注申請のライフサイクル管理
（PENDING → APPROVED → ORDERED → RECEIVED）を集約。
"""

from db import (
    create_purchase_request,
    get_purchase_requests,
    check_items_pending_requests,
    check_items_ordered_status,
    get_purchase_request_counts,
    approve_purchase_request,
    hold_purchase_request,
    reject_purchase_request,
    reset_purchase_request_to_pending,
    delete_purchase_request,
    get_approved_requests_for_order,
    mark_requests_ordered,
    get_ordered_purchase_requests,
    receive_purchase_order,
)

__all__ = [
    'create_purchase_request',
    'get_purchase_requests',
    'check_items_pending_requests',
    'check_items_ordered_status',
    'get_purchase_request_counts',
    'approve_purchase_request',
    'hold_purchase_request',
    'reject_purchase_request',
    'reset_purchase_request_to_pending',
    'delete_purchase_request',
    'get_approved_requests_for_order',
    'mark_requests_ordered',
    'get_ordered_purchase_requests',
    'receive_purchase_order',
]

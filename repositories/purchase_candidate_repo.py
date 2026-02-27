"""
発注候補リポジトリ

自動発注候補の同期・選択・発注操作を集約。
"""

from db import (
    get_reorder_candidates,
    get_reorder_candidates_count,
    sync_purchase_candidates,
    sync_requests_to_candidates,
    get_purchase_candidates,
    update_candidate_selection,
    update_candidate_deferred,
    update_candidate_qty,
    update_candidate_note,
    mark_candidates_ordered,
    get_selected_candidates_for_order,
    get_candidate_counts,
)

__all__ = [
    'get_reorder_candidates',
    'get_reorder_candidates_count',
    'sync_purchase_candidates',
    'sync_requests_to_candidates',
    'get_purchase_candidates',
    'update_candidate_selection',
    'update_candidate_deferred',
    'update_candidate_qty',
    'update_candidate_note',
    'mark_candidates_ordered',
    'get_selected_candidates_for_order',
    'get_candidate_counts',
]

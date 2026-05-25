"""
棚卸しデータ型定義

棚卸しセッション・記録・テンプレートの型定義。
"""

from typing import TypedDict, Optional, List


class StocktakeSession(TypedDict, total=False):
    """棚卸しセッション"""
    id: int
    name: str
    start_date: str
    end_date: Optional[str]
    status: str  # OPEN, CLOSED
    note: str
    created_by: Optional[int]
    creator_name: Optional[str]
    created_at: str
    closed_at: Optional[str]


class StocktakeRecord(TypedDict, total=False):
    """棚卸し記録"""
    id: int
    session_id: int
    item_id: int
    item_name: str
    item_code: str
    category: str
    department_tags: str
    system_qty: int
    actual_qty: Optional[int]
    diff_qty: int
    counted_by: Optional[int]
    counted_by_name: Optional[str]
    counted_at: Optional[str]
    verified_by: Optional[int]
    verified_by_name: Optional[str]
    verified_at: Optional[str]
    approved_by: Optional[int]
    approved_by_name: Optional[str]
    approved_at: Optional[str]
    note: str
    status: str  # PENDING, COUNTED, VERIFIED, APPROVED, APPLIED


class StocktakeSummary(TypedDict, total=False):
    """棚卸しサマリー"""
    total_items: int
    pending_count: int
    counted_count: int
    verified_count: int
    approved_count: int
    applied_count: int
    diff_count: int
    total_surplus: int
    total_shortage: int


class StocktakeTemplate(TypedDict, total=False):
    """棚卸しテンプレート"""
    id: int
    name: str
    description: str
    file_type: str
    is_active: int
    created_at: str
    updated_at: str


class StocktakeTemplateMapping(TypedDict, total=False):
    """棚卸しテンプレートマッピング"""
    id: int
    template_id: int
    field_name: str
    excel_cell: str
    display_label: str
    sort_order: int


class StocktakeOperationResult(TypedDict, total=False):
    """棚卸し操作結果"""
    success: bool
    message: str
    session_id: Optional[int]
    count: Optional[int]
    adjusted_count: Optional[int]
    diff_qty: Optional[int]
    template_id: Optional[int]

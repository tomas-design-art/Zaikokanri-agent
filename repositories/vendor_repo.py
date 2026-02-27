"""
業者リポジトリ

業者マスターのCRUD操作を集約。
"""

from db import (
    list_vendors,
    count_vendors,
    get_vendor_names,
    get_vendor_by_id,
    get_vendor_by_name,
    insert_vendor,
    update_vendor,
    deactivate_vendor,
    activate_vendor,
)

__all__ = [
    'list_vendors',
    'count_vendors',
    'get_vendor_names',
    'get_vendor_by_id',
    'get_vendor_by_name',
    'insert_vendor',
    'update_vendor',
    'deactivate_vendor',
    'activate_vendor',
]

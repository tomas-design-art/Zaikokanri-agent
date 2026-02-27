"""
カテゴリリポジトリ

カテゴリマスターのCRUD操作を集約。
"""

from db import (
    list_categories,
    get_category_names,
    insert_category,
)

__all__ = [
    'list_categories',
    'get_category_names',
    'insert_category',
]

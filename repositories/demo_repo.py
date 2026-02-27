"""
デモデータリポジトリ

デモデータの投入・リセット・件数取得を集約。
"""

from db import (
    insert_demo_data,
    reset_demo_data,
    get_demo_data_counts,
)

__all__ = [
    'insert_demo_data',
    'reset_demo_data',
    'get_demo_data_counts',
]

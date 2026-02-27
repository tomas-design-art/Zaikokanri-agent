"""
データベース基盤モジュール

接続管理、スキーマ初期化、パスワードハッシュなど
基盤的なDB操作を提供する。
"""

# db.py の基盤関数をファサードとして公開
# 将来的にはここにコードを移行し、db.py への依存を解消する
from db import (
    get_db_path,
    get_db_connection,
    init_tables,
    drop_all_tables,
    hash_password,
    verify_password,
)

# 日時ユーティリティは utils に移行済み
from utils.date_utils import get_jst_now_str

__all__ = [
    'get_db_path',
    'get_db_connection',
    'init_tables',
    'drop_all_tables',
    'hash_password',
    'verify_password',
    'get_jst_now_str',
]

"""
ユーザーリポジトリ

認証・ユーザーCRUD操作を集約。
"""

from db import (
    authenticate_user,
    get_user_by_id,
    create_user,
    get_all_users,
    list_users,
    count_users,
    update_user_status,
    update_user_role,
    update_user_full,
)

__all__ = [
    'authenticate_user',
    'get_user_by_id',
    'create_user',
    'get_all_users',
    'list_users',
    'count_users',
    'update_user_status',
    'update_user_role',
    'update_user_full',
]

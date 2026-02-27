"""
部署リポジトリ

部署マスターのCRUD操作を集約。
"""

from db import (
    get_all_departments,
    list_departments,
    count_departments,
    get_department_by_id,
    get_department_by_name,
    create_department,
    migrate_users_department_to_id,
    update_department_name,
    update_department_status,
)

__all__ = [
    'get_all_departments',
    'list_departments',
    'count_departments',
    'get_department_by_id',
    'get_department_by_name',
    'create_department',
    'migrate_users_department_to_id',
    'update_department_name',
    'update_department_status',
]

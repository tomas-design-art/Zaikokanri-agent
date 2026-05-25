"""
部署リポジトリ

部署マスターのCRUD操作を集約。
"""

import sqlite3
from typing import Optional
from repositories.base import get_db_connection

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


def get_all_departments(active_only: bool = True) -> list:
    """全部署一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute("SELECT id, name, is_active FROM departments WHERE is_active = 1 ORDER BY id ASC")
            else:
                cursor.execute("SELECT id, name, is_active FROM departments ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def list_departments(include_inactive: bool = False, search_query: str = "",
                     limit: int = 50, offset: int = 0) -> list:
    """部署一覧を取得（検索・ページング対応）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, name, is_active FROM departments WHERE 1=1"
            params = []
            if not include_inactive:
                query += " AND is_active = 1"
            if search_query:
                query += " AND name LIKE ?"
                params.append(f"%{search_query}%")
            query += " ORDER BY id ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ 部署一覧取得エラー: {e}")
        return []


def count_departments(include_inactive: bool = False, search_query: str = "") -> int:
    """部署の総件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) as count FROM departments WHERE 1=1"
            params = []
            if not include_inactive:
                query += " AND is_active = 1"
            if search_query:
                query += " AND name LIKE ?"
                params.append(f"%{search_query}%")
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ 部署件数取得エラー: {e}")
        return 0


def get_department_by_id(dept_id: int) -> Optional[dict]:
    """部署IDから部署情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, is_active FROM departments WHERE id = ?", (dept_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def get_department_by_name(name: str) -> Optional[dict]:
    """部署名から部署情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, is_active FROM departments WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def create_department(name: str) -> dict:
    """新規部署を作成"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO departments (name) VALUES (?)", (name,))
            conn.commit()
            return {"success": True, "message": f"✅ 部署「{name}」を作成しました"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"❌ 部署名「{name}」は既に存在します"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def migrate_users_department_to_id():
    """既存ユーザーのdepartment（TEXT）をdepartment_idに移行"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, department FROM users WHERE department_id IS NULL")
            users_to_migrate = cursor.fetchall()
            if not users_to_migrate:
                return {"success": True, "message": "移行対象のユーザーはありません"}

            cursor.execute("SELECT id FROM departments WHERE name = '未設定'")
            unset_row = cursor.fetchone()
            if not unset_row:
                cursor.execute("INSERT INTO departments (name) VALUES ('未設定')")
                unset_id = cursor.lastrowid
            else:
                unset_id = unset_row["id"]

            migrated_count = 0
            for user in users_to_migrate:
                cursor.execute("SELECT id FROM departments WHERE name = ?", (user["department"],))
                dept_row = cursor.fetchone()
                dept_id = dept_row["id"] if dept_row else unset_id
                cursor.execute("UPDATE users SET department_id = ? WHERE id = ?", (dept_id, user["id"]))
                migrated_count += 1

            conn.commit()
            return {"success": True, "message": f"✅ {migrated_count}件のユーザーを移行しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_department_name(dept_id: int, new_name: str) -> dict:
    """部署名を変更"""
    if not new_name or not new_name.strip():
        return {"success": False, "message": "❌ 部署名は必須です"}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE departments SET name = ? WHERE id = ?", (new_name.strip(), dept_id))
            conn.commit()
            return {"success": True, "message": f"✅ 部署名を「{new_name.strip()}」に変更しました"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"❌ 部署名「{new_name}」は既に存在します"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_department_status(dept_id: int, is_active: int) -> dict:
    """部署の有効/無効を切り替え"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE departments SET is_active = ? WHERE id = ?", (is_active, dept_id))
            conn.commit()
            status = "有効化" if is_active else "無効化"
            return {"success": True, "message": f"✅ 部署を{status}しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}

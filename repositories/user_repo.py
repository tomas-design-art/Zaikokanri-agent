"""
ユーザーリポジトリ

認証・ユーザーCRUD操作を集約。
"""

import sqlite3
from typing import Optional

from repositories.base import get_db_connection, hash_password, verify_password

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


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    ユーザー認証
    Returns: ユーザー情報（成功時）またはNone（失敗時）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, u.password_hash, u.display_name, 
                       u.department, u.department_id, u.user_role, u.is_active,
                       d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.username = ? AND u.is_active = 1
            """, (username,))
            user = cursor.fetchone()

            if user and verify_password(password, user["password_hash"]):
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "display_name": user["display_name"],
                    "department": user["department_name"] or user["department"] or "未設定",
                    "department_id": user["department_id"],
                    "user_role": user["user_role"]
                }
            return None
    except Exception:
        return None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """ユーザーIDからユーザー情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, u.display_name, u.department, u.department_id, 
                       u.user_role, u.is_active, d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.id = ?
            """, (user_id,))
            user = cursor.fetchone()
            if user:
                return dict(user)
            return None
    except Exception:
        return None


def create_user(username: str, password: str, display_name: str,
                department_id: int, user_role: str) -> dict:
    """
    新規ユーザーを作成
    user_role: 'ADMIN', 'USER', 'GUEST'
    department_id: 部署ID（departmentsテーブルへの外部キー）
    """
    if user_role not in ['ADMIN', 'USER', 'GUEST']:
        return {"success": False, "message": "❌ 無効なユーザー区分です"}

    try:
        password_hash, _ = hash_password(password)
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM departments WHERE id = ?", (department_id,))
            dept = cursor.fetchone()
            dept_name = dept["name"] if dept else "未設定"

            cursor.execute("""
                INSERT INTO users (username, password_hash, display_name, department, department_id, user_role)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (username, password_hash, display_name, dept_name, department_id, user_role))
            conn.commit()
            return {"success": True, "message": f"✅ ユーザー '{username}' を作成しました"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"❌ ユーザー名 '{username}' は既に使用されています"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_all_users() -> list:
    """全ユーザー一覧を取得（パスワードハッシュ除く、部署名も取得）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, u.display_name, u.department, u.department_id,
                       u.user_role, u.is_active, u.created_at, u.updated_at,
                       d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                ORDER BY u.id ASC
            """)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def list_users(include_inactive: bool = False, search_query: str = "",
               role_filter: str = "", department_filter: str = "",
               limit: int = 50, offset: int = 0) -> list:
    """
    ユーザー一覧を取得（検索・フィルタ・ページング対応）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT u.id, u.username, u.display_name, u.department, u.department_id,
                       u.user_role, u.is_active, u.created_at, u.updated_at,
                       d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE 1=1
            """
            params = []

            if not include_inactive:
                query += " AND u.is_active = 1"

            if search_query:
                query += """ AND (
                    u.username LIKE ? OR
                    u.display_name LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param])

            if role_filter and role_filter != "すべて":
                query += " AND u.user_role = ?"
                params.append(role_filter)

            if department_filter and department_filter != "すべて":
                query += " AND d.name = ?"
                params.append(department_filter)

            query += " ORDER BY u.id ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ ユーザー一覧取得エラー: {e}")
        return []


def count_users(include_inactive: bool = False, search_query: str = "",
                role_filter: str = "", department_filter: str = "") -> int:
    """ユーザーの総件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT COUNT(*) as count
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE 1=1
            """
            params = []

            if not include_inactive:
                query += " AND u.is_active = 1"

            if search_query:
                query += """ AND (
                    u.username LIKE ? OR
                    u.display_name LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param])

            if role_filter and role_filter != "すべて":
                query += " AND u.user_role = ?"
                params.append(role_filter)

            if department_filter and department_filter != "すべて":
                query += " AND d.name = ?"
                params.append(department_filter)

            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ ユーザー件数取得エラー: {e}")
        return 0


def update_user_status(user_id: int, is_active: int) -> dict:
    """ユーザーの有効/無効を切り替え"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET is_active = ?, updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (is_active, user_id))
            conn.commit()
            status = "有効化" if is_active else "無効化"
            return {"success": True, "message": f"✅ ユーザーを{status}しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_user_role(user_id: int, new_role: str) -> dict:
    """ユーザーの権限を変更"""
    if new_role not in ['ADMIN', 'USER', 'GUEST']:
        return {"success": False, "message": "❌ 無効な権限です"}

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET user_role = ?, updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (new_role, user_id))
            conn.commit()
            role_labels = {'ADMIN': '管理者', 'USER': '一般ユーザー', 'GUEST': 'ゲスト'}
            return {"success": True, "message": f"✅ 権限を「{role_labels[new_role]}」に変更しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_user_full(user_id: int, display_name: str, department_id: int,
                     user_role: str, is_active: int, new_password: str = None) -> dict:
    """ユーザー情報を一括更新（ADMIN専用）"""
    if not display_name or not display_name.strip():
        return {"success": False, "message": "❌ 表示名は必須です"}

    if user_role not in ['ADMIN', 'USER', 'GUEST']:
        return {"success": False, "message": "❌ 無効な権限です"}

    if is_active not in [0, 1]:
        return {"success": False, "message": "❌ 有効/無効の値が不正です"}

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if new_password and new_password.strip():
                password_hash, _ = hash_password(new_password)
                cursor.execute("""
                    UPDATE users 
                    SET display_name = ?, department_id = ?, user_role = ?, 
                        is_active = ?, password_hash = ?, updated_at = datetime('now', '+09:00')
                    WHERE id = ?
                """, (display_name.strip(), department_id, user_role, is_active, password_hash, user_id))
            else:
                cursor.execute("""
                    UPDATE users 
                    SET display_name = ?, department_id = ?, user_role = ?, 
                        is_active = ?, updated_at = datetime('now', '+09:00')
                    WHERE id = ?
                """, (display_name.strip(), department_id, user_role, is_active, user_id))

            conn.commit()
            return {"success": True, "message": "✅ ユーザー情報を更新しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}

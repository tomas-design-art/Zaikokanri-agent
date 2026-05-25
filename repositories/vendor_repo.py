"""
業者リポジトリ

業者マスターのCRUD操作を集約。
"""

from repositories.base import get_db_connection

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


def list_vendors(include_inactive: bool = False, search_query: str = "",
                 limit: int = 50, offset: int = 0) -> list:
    """業者一覧を取得（検索・ページング対応）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM vendors WHERE 1=1"
            params = []
            if not include_inactive:
                query += " AND is_active = 1"
            if search_query:
                query += " AND (vendor_name LIKE ? OR vendor_code LIKE ? OR phone LIKE ? OR email LIKE ?)"
                search_param = f"%{search_query}%"
                params.extend([search_param] * 4)
            query += " ORDER BY id ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ 業者一覧取得エラー: {e}")
        return []


def count_vendors(include_inactive: bool = False, search_query: str = "") -> int:
    """業者の総件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) as count FROM vendors WHERE 1=1"
            params = []
            if not include_inactive:
                query += " AND is_active = 1"
            if search_query:
                query += " AND (vendor_name LIKE ? OR vendor_code LIKE ? OR phone LIKE ? OR email LIKE ?)"
                search_param = f"%{search_query}%"
                params.extend([search_param] * 4)
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ 業者件数取得エラー: {e}")
        return 0


def get_vendor_names() -> list:
    """有効な業者名のリストを取得（プルダウン用）"""
    vendors = list_vendors(include_inactive=False)
    return [vendor['vendor_name'] for vendor in vendors]


def get_vendor_by_id(vendor_id: int) -> dict:
    """業者IDから業者情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"❌ 業者取得エラー: {e}")
        return None


def get_vendor_by_name(vendor_name: str) -> dict:
    """業者名から業者情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE vendor_name = ?", (vendor_name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"❌ 業者取得エラー: {e}")
        return None


def insert_vendor(vendor_code: str, vendor_name: str, address: str = "",
                 phone: str = "", email: str = "") -> dict:
    """新規業者を登録"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM vendors WHERE vendor_code = ?", (vendor_code,))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者コード「{vendor_code}」は既に登録されています"}
            cursor.execute("SELECT COUNT(*) as count FROM vendors WHERE vendor_name = ?", (vendor_name,))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者名「{vendor_name}」は既に登録されています"}
            cursor.execute("""
                INSERT INTO vendors (vendor_code, vendor_name, address, phone, email)
                VALUES (?, ?, ?, ?, ?)
            """, (vendor_code, vendor_name, address or None, phone or None, email or None))
            conn.commit()
            return {"success": True, "message": f"✅ 業者「{vendor_name}」を登録しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_vendor(vendor_id: int, vendor_code: str, vendor_name: str,
                 address: str = "", phone: str = "", email: str = "") -> dict:
    """業者情報を更新"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            if not cursor.fetchone():
                return {"success": False, "message": "業者が見つかりません"}
            cursor.execute("SELECT COUNT(*) as count FROM vendors WHERE vendor_code = ? AND id != ?", (vendor_code, vendor_id))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者コード「{vendor_code}」は既に使用されています"}
            cursor.execute("SELECT COUNT(*) as count FROM vendors WHERE vendor_name = ? AND id != ?", (vendor_name, vendor_id))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者名「{vendor_name}」は既に使用されています"}
            cursor.execute("""
                UPDATE vendors SET vendor_code = ?, vendor_name = ?, address = ?,
                    phone = ?, email = ?, updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (vendor_code, vendor_name, address or None, phone or None, email or None, vendor_id))
            conn.commit()
            return {"success": True, "message": f"✅ 業者「{vendor_name}」を更新しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def deactivate_vendor(vendor_id: int) -> dict:
    """業者を無効化（論理削除）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "業者が見つかりません"}
            cursor.execute("UPDATE vendors SET is_active = 0, updated_at = datetime('now', '+09:00') WHERE id = ?", (vendor_id,))
            conn.commit()
            return {"success": True, "message": f"✅ 業者「{row['vendor_name']}」を無効化しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def activate_vendor(vendor_id: int) -> dict:
    """業者を有効化"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "業者が見つかりません"}
            cursor.execute("UPDATE vendors SET is_active = 1, updated_at = datetime('now', '+09:00') WHERE id = ?", (vendor_id,))
            conn.commit()
            return {"success": True, "message": f"✅ 業者「{row['vendor_name']}」を有効化しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}

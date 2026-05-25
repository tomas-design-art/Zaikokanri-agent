"""
カテゴリリポジトリ

カテゴリマスターのCRUD操作を集約。
"""

from repositories.base import get_db_connection

__all__ = [
    'list_categories',
    'get_category_names',
    'insert_category',
]


def list_categories(include_inactive: bool = False) -> list:
    """
    カテゴリ一覧を取得

    Args:
        include_inactive: True の場合、無効化されたカテゴリも含める

    Returns:
        カテゴリリスト（dict の list）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if include_inactive:
                query = "SELECT * FROM categories ORDER BY name"
            else:
                query = "SELECT * FROM categories WHERE is_active = 1 ORDER BY name"
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ カテゴリ一覧取得エラー: {e}")
        return []


def get_category_names() -> list:
    """有効なカテゴリ名のリストを取得（プルダウン用）"""
    categories = list_categories(include_inactive=False)
    return [cat['name'] for cat in categories]


def insert_category(name: str) -> dict:
    """
    新規カテゴリを登録

    Args:
        name: カテゴリ名

    Returns:
        成功/失敗メッセージを含むdict
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM categories WHERE name = ?", (name,))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ カテゴリ「{name}」は既に登録されています"}
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (name,))
            conn.commit()
            return {"success": True, "message": f"✅ カテゴリ「{name}」を登録しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}

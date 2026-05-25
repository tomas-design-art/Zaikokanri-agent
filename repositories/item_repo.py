"""
物品マスターリポジトリ

物品マスターのCRUD操作を集約。
"""

from repositories.base import get_db_connection

__all__ = [
    'list_items',
    'count_items',
    'get_item_master_by_id',
    'insert_item',
    'update_item',
    'deactivate_item',
    'activate_item',
]


def list_items(include_inactive: bool = False, search_query: str = "",
               category_filter: str = "", asset_filter: str = "すべて",
               department_tag_filter: str = "", limit: int = 50, offset: int = 0) -> list:
    """物品一覧を取得（検索・フィルタ・ページング対応）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT 
                    i.*,
                    d.name as owner_department_name,
                    CASE 
                        WHEN i.is_common = 1 THEN '全社'
                        WHEN i.department_tags IS NULL OR i.department_tags = '' THEN '未設定'
                        ELSE i.department_tags
                    END as display_department_tags
                FROM items i
                LEFT JOIN departments d ON i.owner_department_id = d.id
                WHERE 1=1
            """
            params = []

            if not include_inactive:
                query += " AND i.is_active = 1"

            if search_query:
                query += """ AND (
                    i.item_name LIKE ? OR
                    i.item_code LIKE ? OR
                    i.vendor_name LIKE ? OR
                    i.vendor_item_code LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_param, search_param])

            if category_filter and category_filter != "すべて":
                query += " AND i.category = ?"
                params.append(category_filter)

            if asset_filter == "消耗品":
                query += " AND i.is_asset = 0"
            elif asset_filter == "資産":
                query += " AND i.is_asset = 1"

            if department_tag_filter and department_tag_filter != "すべて":
                if department_tag_filter == "全社":
                    query += " AND i.is_common = 1"
                elif department_tag_filter == "未設定":
                    query += " AND (i.department_tags IS NULL OR i.department_tags = '') AND i.is_common = 0"
                else:
                    query += " AND i.department_tags LIKE ?"
                    params.append(f"%{department_tag_filter}%")

            query += " ORDER BY i.updated_at DESC, i.item_name LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ 物品一覧取得エラー: {e}")
        return []


def count_items(include_inactive: bool = False, search_query: str = "",
                category_filter: str = "", asset_filter: str = "すべて",
                department_tag_filter: str = "") -> int:
    """物品の総件数を取得（検索・フィルタ条件に一致するもの）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT COUNT(*) as count FROM items i WHERE 1=1"
            params = []

            if not include_inactive:
                query += " AND i.is_active = 1"

            if search_query:
                query += """ AND (
                    i.item_name LIKE ? OR
                    i.item_code LIKE ? OR
                    i.vendor_name LIKE ? OR
                    i.vendor_item_code LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_param, search_param])

            if category_filter and category_filter != "すべて":
                query += " AND i.category = ?"
                params.append(category_filter)

            if asset_filter == "消耗品":
                query += " AND i.is_asset = 0"
            elif asset_filter == "資産":
                query += " AND i.is_asset = 1"

            if department_tag_filter and department_tag_filter != "すべて":
                if department_tag_filter == "全社":
                    query += " AND i.is_common = 1"
                elif department_tag_filter == "未設定":
                    query += " AND (i.department_tags IS NULL OR i.department_tags = '') AND i.is_common = 0"
                else:
                    query += " AND i.department_tags LIKE ?"
                    params.append(f"%{department_tag_filter}%")

            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ 物品件数取得エラー: {e}")
        return 0


def get_item_master_by_id(item_id: int) -> dict:
    """物品IDで物品マスター情報を取得（在庫情報なし）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"❌ 物品取得エラー: {e}")
        return None


def insert_item(item_name: str, category: str, item_code: str = None,
               vendor_name: str = None, vendor_item_code: str = None,
               department_tags: str = None, unit_price: float = 0,
               is_asset: int = 0, frequency_tag: str = None,
               expiry_date: str = None, owner_department_id: int = None,
               is_common: int = 0) -> dict:
    """新規物品を登録"""
    try:
        if not item_name or not category:
            return {"success": False, "message": "品目名とカテゴリは必須です"}

        if not item_code:
            if not vendor_name or not vendor_item_code:
                return {"success": False, "message": "品目コードがない場合は業者名と業者品番が必須です"}

        with get_db_connection() as conn:
            cursor = conn.cursor()

            if item_code:
                cursor.execute("SELECT id FROM items WHERE item_code = ?", (item_code,))
                if cursor.fetchone():
                    return {"success": False, "message": f"品目コード「{item_code}」は既に登録されています"}

            if vendor_name and vendor_item_code:
                cursor.execute(
                    "SELECT id FROM items WHERE vendor_name = ? AND vendor_item_code = ?",
                    (vendor_name, vendor_item_code)
                )
                if cursor.fetchone():
                    return {"success": False, "message": f"業者名「{vendor_name}」+ 業者品番「{vendor_item_code}」は既に登録されています"}

            cursor.execute("""
                INSERT INTO items (
                    item_name, item_code, vendor_name, vendor_item_code,
                    category, department_tags, unit_price, is_asset,
                    frequency_tag, expiry_date, is_active, owner_department_id, is_common
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (item_name, item_code, vendor_name, vendor_item_code,
                  category, department_tags, unit_price, is_asset,
                  frequency_tag, expiry_date, owner_department_id, is_common))

            item_id = cursor.lastrowid
            conn.commit()

            return {"success": True, "message": f"✅ 物品「{item_name}」を登録しました", "item_id": item_id}

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_item(item_id: int, item_name: str, category: str, item_code: str = None,
               vendor_name: str = None, vendor_item_code: str = None,
               department_tags: str = None, unit_price: float = 0,
               is_asset: int = 0, frequency_tag: str = None,
               expiry_date: str = None, owner_department_id: int = None,
               is_common: int = 0, is_inventory_target: int = 1) -> dict:
    """物品情報を更新"""
    try:
        if not item_name or not category:
            return {"success": False, "message": "品目名とカテゴリは必須です"}

        if not item_code:
            if not vendor_name or not vendor_item_code:
                return {"success": False, "message": "品目コードがない場合は業者名と業者品番が必須です"}

        with get_db_connection() as conn:
            cursor = conn.cursor()

            if item_code:
                cursor.execute("SELECT id FROM items WHERE item_code = ? AND id != ?", (item_code, item_id))
                if cursor.fetchone():
                    return {"success": False, "message": f"品目コード「{item_code}」は既に他の物品で使用されています"}

            if vendor_name and vendor_item_code:
                cursor.execute(
                    "SELECT id FROM items WHERE vendor_name = ? AND vendor_item_code = ? AND id != ?",
                    (vendor_name, vendor_item_code, item_id)
                )
                if cursor.fetchone():
                    return {"success": False, "message": f"業者名「{vendor_name}」+ 業者品番「{vendor_item_code}」は既に他の物品で使用されています"}

            cursor.execute("""
                UPDATE items SET
                    item_name = ?, item_code = ?, vendor_name = ?, vendor_item_code = ?,
                    category = ?, department_tags = ?, unit_price = ?, is_asset = ?,
                    frequency_tag = ?, expiry_date = ?, owner_department_id = ?, is_common = ?,
                    is_inventory_target = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (item_name, item_code, vendor_name, vendor_item_code,
                  category, department_tags, unit_price, is_asset,
                  frequency_tag, expiry_date, owner_department_id, is_common,
                  is_inventory_target, item_id))

            conn.commit()

            return {"success": True, "message": f"✅ 物品「{item_name}」を更新しました"}

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def deactivate_item(item_id: int) -> dict:
    """物品を無効化（論理削除）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT item_name FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "物品が見つかりません"}

            item_name = row["item_name"]

            cursor.execute("""
                UPDATE items SET
                    is_active = 0,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (item_id,))

            conn.commit()

            return {"success": True, "message": f"✅ 物品「{item_name}」を無効化しました"}

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def activate_item(item_id: int) -> dict:
    """物品を有効化"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT item_name FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "物品が見つかりません"}

            item_name = row["item_name"]

            cursor.execute("""
                UPDATE items SET
                    is_active = 1,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (item_id,))

            conn.commit()

            return {"success": True, "message": f"✅ 物品「{item_name}」を有効化しました"}

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}

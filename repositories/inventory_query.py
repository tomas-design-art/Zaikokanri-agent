"""
在庫クエリリポジトリ

app.py に定義されていた SQL クエリ関数を集約。
在庫一覧・出庫/入庫候補・調整候補のクエリを提供する。
"""

import pandas as pd
from db import get_db_connection


def get_inventory_list(search_query="", category_filter="", asset_filter="すべて",
                       limit=100, offset=0, department_name=None):
    """
    在庫一覧を取得（検索・フィルタ対応）
    数千件対応のため、LIMIT/OFFSETでページネーション
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                i.id, i.item_name, i.item_code, i.vendor_name, i.vendor_item_code,
                i.category, i.unit_price, i.is_asset, i.department_tags,
                i.frequency_tag, i.expiry_date,
                inv.quantity, inv.threshold, inv.location,
                CASE WHEN inv.quantity <= inv.threshold THEN '⚠️' ELSE '✅' END as alert_status
            FROM items i
            LEFT JOIN inventory inv ON i.id = inv.item_id
            WHERE 1=1
        """
        params = []

        if asset_filter == "消耗品":
            query += " AND i.is_asset = 0"
        elif asset_filter == "資産":
            query += " AND i.is_asset = 1"

        if search_query:
            query += """ AND (i.item_name LIKE ? OR i.item_code LIKE ?
                         OR i.vendor_name LIKE ? OR i.vendor_item_code LIKE ?)"""
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern] * 4)

        if category_filter and category_filter != "すべて":
            query += " AND i.category = ?"
            params.append(category_filter)

        if department_name:
            query += """ AND (
                (',' || i.department_tags || ',') LIKE ?
                OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                OR i.department_tags IS NULL
                OR TRIM(i.department_tags) = ''
            )"""
            params.append(f'%,{department_name},%')

        query += " ORDER BY i.item_name LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        if rows:
            return pd.DataFrame([dict(row) for row in rows])
        else:
            return pd.DataFrame()


def get_total_count(search_query="", category_filter="", asset_filter="すべて",
                    department_name=None):
    """検索条件に一致する総件数を取得"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT COUNT(*) as count FROM items i WHERE 1=1"
        params = []

        if asset_filter == "消耗品":
            query += " AND i.is_asset = 0"
        elif asset_filter == "資産":
            query += " AND i.is_asset = 1"

        if search_query:
            query += """ AND (i.item_name LIKE ? OR i.item_code LIKE ?
                         OR i.vendor_name LIKE ? OR i.vendor_item_code LIKE ?)"""
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern] * 4)

        if category_filter and category_filter != "すべて":
            query += " AND i.category = ?"
            params.append(category_filter)

        if department_name:
            query += """ AND (
                (',' || i.department_tags || ',') LIKE ?
                OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                OR i.department_tags IS NULL
                OR TRIM(i.department_tags) = ''
            )"""
            params.append(f'%,{department_name},%')

        cursor.execute(query, params)
        result = cursor.fetchone()
        return result["count"] if result else 0


def get_categories():
    """カテゴリ一覧を取得"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM items ORDER BY category")
        rows = cursor.fetchall()
        return [row["category"] for row in rows]


def get_all_items_for_outbound(search_query="", category_filter="すべて",
                               department_id=None, include_assets=False,
                               department_name=None):
    """出庫可能な物品一覧を取得（在庫数 > 0、デフォルトは消耗品のみ）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if include_assets:
            sql = """
                SELECT i.id, i.item_name, i.item_code, i.category,
                       inv.quantity, inv.location, i.vendor_name
                FROM items i LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE inv.quantity > 0
            """
        else:
            sql = """
                SELECT i.id, i.item_name, i.item_code, i.category,
                       inv.quantity, inv.location, i.vendor_name
                FROM items i LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE inv.quantity > 0 AND i.is_asset = 0
            """
        params = []

        if search_query and search_query.strip():
            sql += """ AND (i.item_name LIKE ? OR i.item_code LIKE ?
                       OR i.vendor_name LIKE ? OR i.vendor_item_code LIKE ?)"""
            search_param = f"%{search_query.strip()}%"
            params.extend([search_param] * 4)

        if category_filter and category_filter != "すべて":
            sql += " AND i.category = ?"
            params.append(category_filter)

        if department_name:
            sql += " AND i.department_tags LIKE ?"
            params.append(f'%{department_name}%')

        sql += " ORDER BY i.item_name"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_items_for_inbound(search_query="", category_filter="すべて",
                               department_id=None, include_assets=False):
    """入庫可能な物品一覧を取得（デフォルトは消耗品のみ）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if include_assets:
            sql = """
                SELECT i.id, i.item_name, i.item_code, i.category,
                       inv.quantity, inv.location, i.vendor_name
                FROM items i LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE 1=1
            """
        else:
            sql = """
                SELECT i.id, i.item_name, i.item_code, i.category,
                       inv.quantity, inv.location, i.vendor_name
                FROM items i LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.is_asset = 0
            """
        params = []

        if search_query and search_query.strip():
            sql += """ AND (i.item_name LIKE ? OR i.item_code LIKE ?
                       OR i.vendor_name LIKE ? OR i.vendor_item_code LIKE ?)"""
            search_param = f"%{search_query.strip()}%"
            params.extend([search_param] * 4)

        if category_filter and category_filter != "すべて":
            sql += " AND i.category = ?"
            params.append(category_filter)

        sql += " ORDER BY i.item_name"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_items_for_adjust():
    """在庫調整用の全物品リストを取得"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.id, i.item_name, i.item_code, i.category,
                   inv.quantity, inv.location
            FROM items i
            LEFT JOIN inventory inv ON i.id = inv.item_id
            ORDER BY i.item_name
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

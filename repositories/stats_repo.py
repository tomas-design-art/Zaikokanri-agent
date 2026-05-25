"""
統計・KPIリポジトリ

月次出庫数・在庫回転率・出庫トレンドなど
統計・分析関連のクエリを集約。
"""

from repositories.base import get_db_connection

__all__ = [
    'get_monthly_outbound_total',
    'get_stock_alert_count',
    'get_expired_count',
    'get_outbound_trend_data',
    'get_item_kpi',
    'get_top_outbound_items',
]


def get_monthly_outbound_total(department_name: str = None) -> int:
    """今月の出庫数量合計を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if department_name:
                cursor.execute("""
                    SELECT SUM(ABS(ih.quantity)) as total
                    FROM inventory_history ih
                    JOIN items i ON ih.item_id = i.id
                    WHERE ih.change_type = '出庫'
                      AND strftime('%Y-%m', ih.created_at) = strftime('%Y-%m', 'now')
                      AND (
                          (',' || i.department_tags || ',') LIKE '%,' || ? || ',%'
                          OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                          OR i.department_tags IS NULL
                          OR TRIM(i.department_tags) = ''
                      )
                """, (department_name,))
            else:
                cursor.execute("""
                    SELECT SUM(ABS(quantity)) as total
                    FROM inventory_history
                    WHERE change_type = '出庫'
                      AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
                """)

            result = cursor.fetchone()
            return result["total"] if result and result["total"] else 0
    except Exception:
        return 0


def get_stock_alert_count(department_name: str = None) -> int:
    """在庫不足件数を取得（在庫 <= 発注点）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if department_name:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM inventory inv
                    JOIN items i ON inv.item_id = i.id
                    WHERE inv.quantity <= i.reorder_point
                      AND i.reorder_point IS NOT NULL
                      AND i.department_tags LIKE ?
                """, (f'%{department_name}%',))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE inv.quantity <= i.reorder_point
                      AND i.reorder_point IS NOT NULL
                """)

            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception:
        return 0


def get_expired_count(department_name: str = None) -> int:
    """期限切れ件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if department_name:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM items i
                    WHERE i.expiry_date IS NOT NULL
                      AND i.expiry_date < date('now')
                      AND (
                          (',' || i.department_tags || ',') LIKE '%,' || ? || ',%'
                          OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                          OR i.department_tags IS NULL
                          OR TRIM(i.department_tags) = ''
                      )
                """, (department_name,))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM items
                    WHERE expiry_date IS NOT NULL
                      AND expiry_date < date('now')
                """)

            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception:
        return 0


def get_outbound_trend_data(item_ids: list, months: int = 6, department_name: str = None) -> list:
    """出庫量の月別推移データを取得（折れ線グラフ用）"""
    try:
        if not item_ids:
            return []

        with get_db_connection() as conn:
            cursor = conn.cursor()

            placeholders = ','.join('?' * len(item_ids))

            if department_name:
                query = f"""
                    SELECT 
                        strftime('%Y-%m', ih.created_at) as ym,
                        ih.item_id,
                        i.item_name,
                        SUM(ABS(ih.quantity)) as qty
                    FROM inventory_history ih
                    JOIN items i ON ih.item_id = i.id
                    WHERE ih.change_type = '出庫'
                      AND ih.created_at >= date('now', '-{months} months')
                      AND ih.item_id IN ({placeholders})
                      AND (
                          (',' || i.department_tags || ',') LIKE '%,' || ? || ',%'
                          OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                          OR i.department_tags IS NULL
                          OR TRIM(i.department_tags) = ''
                      )
                    GROUP BY ym, ih.item_id, i.item_name
                    ORDER BY ym, ih.item_id
                """
                params = list(item_ids) + [department_name]
            else:
                query = f"""
                    SELECT 
                        strftime('%Y-%m', ih.created_at) as ym,
                        ih.item_id,
                        i.item_name,
                        SUM(ABS(ih.quantity)) as qty
                    FROM inventory_history ih
                    JOIN items i ON ih.item_id = i.id
                    WHERE ih.change_type = '出庫'
                      AND ih.created_at >= date('now', '-{months} months')
                      AND ih.item_id IN ({placeholders})
                    GROUP BY ym, ih.item_id, i.item_name
                    ORDER BY ym, ih.item_id
                """
                params = item_ids

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_outbound_trend_data: {e}")
        return []


def get_item_kpi(item_ids: list, department_name: str = None) -> dict:
    """選択した物品のKPIを取得"""
    try:
        if not item_ids:
            return {"monthly_out": 0, "weekly_out": 0, "items": []}

        with get_db_connection() as conn:
            cursor = conn.cursor()

            placeholders = ','.join('?' * len(item_ids))

            # 今月の出庫数量
            if department_name:
                cursor.execute(f"""
                    SELECT SUM(ABS(ih.quantity)) as total
                    FROM inventory_history ih
                    JOIN items i ON ih.item_id = i.id
                    WHERE ih.change_type = '出庫'
                      AND strftime('%Y-%m', ih.created_at) = strftime('%Y-%m', 'now')
                      AND ih.item_id IN ({placeholders})
                      AND (
                          (',' || i.department_tags || ',') LIKE '%,' || ? || ',%'
                          OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                          OR i.department_tags IS NULL
                          OR TRIM(i.department_tags) = ''
                      )
                """, list(item_ids) + [department_name])
            else:
                cursor.execute(f"""
                    SELECT SUM(ABS(quantity)) as total
                    FROM inventory_history
                    WHERE change_type = '出庫'
                      AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
                      AND item_id IN ({placeholders})
                """, item_ids)

            monthly_result = cursor.fetchone()
            monthly_out = monthly_result["total"] if monthly_result and monthly_result["total"] else 0

            # 直近7日の出庫数量
            if department_name:
                cursor.execute(f"""
                    SELECT SUM(ABS(ih.quantity)) as total
                    FROM inventory_history ih
                    JOIN items i ON ih.item_id = i.id
                    WHERE ih.change_type = '出庫'
                      AND ih.created_at >= date('now', '-7 days')
                      AND ih.item_id IN ({placeholders})
                      AND (
                          (',' || i.department_tags || ',') LIKE '%,' || ? || ',%'
                          OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                          OR i.department_tags IS NULL
                          OR TRIM(i.department_tags) = ''
                      )
                """, list(item_ids) + [department_name])
            else:
                cursor.execute(f"""
                    SELECT SUM(ABS(quantity)) as total
                    FROM inventory_history
                    WHERE change_type = '出庫'
                      AND created_at >= date('now', '-7 days')
                      AND item_id IN ({placeholders})
                """, item_ids)

            weekly_result = cursor.fetchone()
            weekly_out = weekly_result["total"] if weekly_result and weekly_result["total"] else 0

            # 現在庫と発注点
            if department_name:
                cursor.execute(f"""
                    SELECT 
                        i.id as item_id,
                        i.item_name,
                        inv.quantity,
                        inv.threshold
                    FROM items i
                    LEFT JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.id IN ({placeholders})
                      AND (
                          (',' || i.department_tags || ',') LIKE '%,' || ? || ',%'
                          OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                          OR i.department_tags IS NULL
                          OR TRIM(i.department_tags) = ''
                      )
                """, list(item_ids) + [department_name])
            else:
                cursor.execute(f"""
                    SELECT 
                        i.id as item_id,
                        i.item_name,
                        inv.quantity,
                        inv.threshold
                    FROM items i
                    LEFT JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.id IN ({placeholders})
                """, item_ids)

            items_data = [dict(row) for row in cursor.fetchall()]

            return {
                "monthly_out": monthly_out,
                "weekly_out": weekly_out,
                "items": items_data
            }
    except Exception as e:
        print(f"Error in get_item_kpi: {e}")
        return {"monthly_out": 0, "weekly_out": 0, "items": []}


def get_top_outbound_items(
    category: str = None,
    keyword: str = None,
    department_name: str = None,
    limit: int = 10
) -> list:
    """今月の出庫量が多い物品TOP Nを取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            where_clauses = ["ih.change_type = '出庫'"]
            where_clauses.append("strftime('%Y-%m', ih.created_at) = strftime('%Y-%m', 'now')")
            params = []

            if category and category != "すべて":
                where_clauses.append("i.category = ?")
                params.append(category)

            if keyword and keyword.strip():
                where_clauses.append("(i.item_name LIKE ? OR i.item_code LIKE ?)")
                keyword_param = f"%{keyword.strip()}%"
                params.extend([keyword_param, keyword_param])

            if department_name:
                where_clauses.append(
                    """(
                        (',' || i.department_tags || ',') LIKE ?
                        OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                        OR i.department_tags IS NULL
                        OR TRIM(i.department_tags) = ''
                    )"""
                )
                params.append(f"%,{department_name},%")

            where_sql = " AND ".join(where_clauses)

            query = f"""
                SELECT 
                    i.id as item_id,
                    i.item_name,
                    i.item_code,
                    i.category,
                    SUM(ABS(ih.quantity)) as monthly_out,
                    inv.quantity,
                    inv.threshold
                FROM inventory_history ih
                JOIN items i ON ih.item_id = i.id
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE {where_sql}
                GROUP BY i.id, i.item_name, i.item_code, i.category, inv.quantity, inv.threshold
                ORDER BY monthly_out DESC
                LIMIT ?
            """

            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_top_outbound_items: {e}")
        return []

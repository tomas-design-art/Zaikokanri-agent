"""
アラートリポジトリ

在庫不足・期限切れのアラート取得を集約。
"""

from repositories.base import get_db_connection, JST

__all__ = [
    'get_stock_alerts',
    'get_expiry_alerts',
]


def get_stock_alerts(department_name: str = None) -> list:
    """
    在庫アラートを取得
    inventory.quantity <= items.reorder_point の物品を返す
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if department_name:
                cursor.execute("""
                    SELECT i.id, i.item_name, i.item_code, i.category,
                           i.vendor_name, i.reorder_point, inv.quantity, inv.location
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.reorder_point IS NOT NULL
                      AND inv.quantity <= i.reorder_point
                      AND i.is_active = 1
                      AND i.department_tags LIKE ?
                    ORDER BY inv.quantity ASC, i.item_name
                """, (f'%{department_name}%',))
            else:
                cursor.execute("""
                    SELECT i.id, i.item_name, i.item_code, i.category,
                           i.vendor_name, i.reorder_point, inv.quantity, inv.location
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.reorder_point IS NOT NULL
                      AND inv.quantity <= i.reorder_point
                      AND i.is_active = 1
                    ORDER BY inv.quantity ASC, i.item_name
                """)
            results = cursor.fetchall()
            return [dict(row) for row in results]
    except Exception as e:
        print(f"❌ 在庫アラート取得エラー: {e}")
        return []


def get_expiry_alerts(department_name: str = None) -> dict:
    """
    期限アラートを取得
    expiry_date が今日以前 or 30日以内の物品を返す
    """
    try:
        from datetime import datetime, timedelta

        today = datetime.now(JST).date()
        threshold_date = today + timedelta(days=30)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            if department_name:
                cursor.execute("""
                    SELECT i.id, i.item_name, i.item_code, i.category,
                           i.vendor_name, i.expiry_date, inv.quantity, inv.location
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.expiry_date IS NOT NULL AND i.expiry_date != ''
                      AND i.is_active = 1 AND i.department_tags LIKE ?
                    ORDER BY i.expiry_date ASC, i.item_name
                """, (f'%{department_name}%',))
            else:
                cursor.execute("""
                    SELECT i.id, i.item_name, i.item_code, i.category,
                           i.vendor_name, i.expiry_date, inv.quantity, inv.location
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.expiry_date IS NOT NULL AND i.expiry_date != ''
                      AND i.is_active = 1
                    ORDER BY i.expiry_date ASC, i.item_name
                """)

            results = cursor.fetchall()
            expired = []
            expiring_soon = []

            for row in results:
                row_dict = dict(row)
                try:
                    expiry_str = row_dict['expiry_date']
                    if len(expiry_str) == 7:
                        expiry_date = datetime.strptime(expiry_str + "-01", "%Y-%m-%d").date()
                    else:
                        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                    row_dict['expiry_date_parsed'] = expiry_date
                    if expiry_date < today:
                        expired.append(row_dict)
                    elif expiry_date <= threshold_date:
                        expiring_soon.append(row_dict)
                except Exception:
                    continue

            return {"expired": expired, "expiring_soon": expiring_soon}
    except Exception as e:
        print(f"❌ 期限アラート取得エラー: {e}")
        return {"expired": [], "expiring_soon": []}

"""
在庫操作リポジトリ

出庫・入庫・在庫参照などの在庫テーブル操作を集約。
"""

from typing import Optional

from repositories.base import get_db_connection

__all__ = [
    'process_outbound',
    'process_outbound_pending',
    'get_item_by_id',
    'process_inbound',
]


def process_outbound(item_id: int, quantity: int, user_name: str,
                     department: str = "", note: str = "") -> dict:
    """出庫処理を実行（在庫減算 + 履歴記録）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT i.item_name, inv.quantity, inv.threshold
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.id = ?
            """, (item_id,))

            result = cursor.fetchone()

            if not result:
                return {
                    "success": False,
                    "message": "❌ 指定された物品が見つかりません",
                    "remaining_quantity": 0
                }

            item_name = result["item_name"]
            current_quantity = result["quantity"] if result["quantity"] is not None else 0
            threshold = result["threshold"] if result["threshold"] is not None else 0

            if current_quantity < quantity:
                return {
                    "success": False,
                    "message": f"❌ 在庫不足: 現在 {current_quantity} 個、要求 {quantity} 個",
                    "remaining_quantity": current_quantity
                }

            new_quantity = current_quantity - quantity
            cursor.execute("""
                UPDATE inventory
                SET quantity = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))

            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, 
                    user_name, department, status, note, created_at
                ) VALUES (?, 'OUT', ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, quantity, user_name, department, note))

            alert_msg = ""
            if new_quantity <= threshold:
                alert_msg = f" ⚠️ 在庫が閾値({threshold})以下になりました"

            return {
                "success": True,
                "message": f"✅ 出庫完了: {item_name} × {quantity} 個{alert_msg}",
                "remaining_quantity": new_quantity
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"❌ エラーが発生しました: {str(e)}",
            "remaining_quantity": 0
        }


def process_outbound_pending(item_id: int, quantity: int, user_name: str,
                              department: str = "", note: str = "") -> dict:
    """ゲストユーザー用の仮出庫処理（在庫は変更せず、履歴のみ記録）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT i.item_name, inv.quantity
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.id = ?
            """, (item_id,))

            result = cursor.fetchone()

            if not result:
                return {"success": False, "message": "❌ 指定された物品が見つかりません"}

            item_name = result["item_name"]
            current_quantity = result["quantity"] if result["quantity"] is not None else 0

            if quantity > current_quantity:
                return {
                    "success": False,
                    "message": f"❌ 在庫不足です（現在: {current_quantity}個、申請: {quantity}個）"
                }

            pending_note = f"[仮入力] {note}" if note else "[仮入力]"
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, 
                    user_name, department, status, note, created_at
                ) VALUES (?, 'OUT', ?, ?, ?, 'PENDING', ?, datetime('now', '+09:00'))
            """, (item_id, quantity, user_name, department, pending_note))

            conn.commit()

            return {
                "success": True,
                "message": f"📝 仮入力完了: {item_name} × {quantity} 個（管理者の承認待ち）"
            }

    except Exception as e:
        return {"success": False, "message": f"❌ エラーが発生しました: {str(e)}"}


def get_item_by_id(item_id: int) -> Optional[dict]:
    """物品情報と在庫情報をIDで取得（在庫情報付き）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    i.id, i.item_name, i.item_code, i.category,
                    i.vendor_name, i.vendor_item_code, i.unit_price,
                    i.is_asset, i.frequency_tag, i.expiry_date,
                    i.department_tags, i.is_active, i.owner_department_id, i.is_common,
                    inv.quantity, inv.threshold, inv.location
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.id = ?
            """, (item_id,))

            result = cursor.fetchone()
            if result:
                row_dict = dict(result)
                if row_dict.get('quantity') is None:
                    row_dict['quantity'] = 0
                if row_dict.get('threshold') is None:
                    row_dict['threshold'] = 0
                return row_dict
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def process_inbound(item_id: int, quantity: int, user_name: str,
                    department: str = "", note: str = "") -> dict:
    """入庫処理を実行（在庫加算 + 履歴記録）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT i.item_name, inv.quantity, inv.threshold
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.id = ?
            """, (item_id,))

            result = cursor.fetchone()

            if not result:
                return {
                    "success": False,
                    "message": "❌ 指定された物品が見つかりません",
                    "new_quantity": 0
                }

            item_name = result["item_name"]
            current_quantity = result["quantity"] if result["quantity"] is not None else 0

            new_quantity = current_quantity + quantity
            cursor.execute("""
                UPDATE inventory
                SET quantity = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))

            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, 
                    user_name, department, status, note, created_at
                ) VALUES (?, 'IN', ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, quantity, user_name, department, note))

            return {
                "success": True,
                "message": f"✅ 入庫完了: {item_name} × {quantity} 個",
                "new_quantity": new_quantity
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"❌ エラーが発生しました: {str(e)}",
            "new_quantity": 0
        }

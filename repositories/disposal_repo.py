"""
廃棄申請リポジトリ

廃棄申請のCRUD・承認/却下操作を集約。
"""

from repositories.base import get_db_connection

__all__ = [
    'create_disposal_request',
    'get_disposal_requests',
    'approve_disposal_request',
    'reject_disposal_request',
    'get_disposal_count',
]


def create_disposal_request(item_id: int, quantity: int, reason: str, requester_id: int) -> dict:
    """廃棄申請を作成"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT i.item_name, inv.quantity
                FROM items i JOIN inventory inv ON i.id = inv.item_id
                WHERE i.id = ?
            """, (item_id,))
            result = cursor.fetchone()
            if not result:
                return {"success": False, "message": "❌ 物品が見つかりません"}
            if quantity > result["quantity"]:
                return {"success": False, "message": f"❌ 在庫数（{result['quantity']}）を超えて廃棄することはできません"}
            cursor.execute("""
                INSERT INTO disposal_requests
                (item_id, quantity, reason, requester_id, status, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', datetime('now', '+09:00'))
            """, (item_id, quantity, reason, requester_id))
            conn.commit()
            return {"success": True, "message": f"✅ {result['item_name']} の廃棄申請を登録しました（{quantity}個）"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_disposal_requests(status: str = None, requester_id: int = None) -> list:
    """廃棄申請一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT dr.id, dr.item_id, i.item_name, i.item_code, i.category,
                       i.unit_price, dr.quantity, dr.reason, dr.status,
                       u.display_name as requester_name, dr.created_at,
                       dr.approved_at, approver.display_name as approver_name,
                       dr.reject_reason
                FROM disposal_requests dr
                JOIN items i ON dr.item_id = i.id
                JOIN users u ON dr.requester_id = u.id
                LEFT JOIN users approver ON dr.approved_by = approver.id
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND dr.status = ?"
                params.append(status)
            if requester_id:
                query += " AND dr.requester_id = ?"
                params.append(requester_id)
            query += " ORDER BY dr.created_at DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ 廃棄申請取得エラー: {e}")
        return []


def approve_disposal_request(request_id: int, approver_id: int) -> dict:
    """廃棄申請を承認して在庫を減算"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT dr.*, i.item_name, u.display_name as requester_name
                FROM disposal_requests dr
                JOIN items i ON dr.item_id = i.id
                JOIN users u ON dr.requester_id = u.id
                WHERE dr.id = ?
            """, (request_id,))
            request = cursor.fetchone()
            if not request:
                return {"success": False, "message": "❌ 申請が見つかりません"}
            if request["status"] != "PENDING":
                return {"success": False, "message": "❌ この申請は既に処理済みです"}

            item_id, quantity = request["item_id"], request["quantity"]
            cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
            inv_result = cursor.fetchone()
            if not inv_result:
                return {"success": False, "message": "❌ 在庫情報が見つかりません"}
            current_qty = inv_result["quantity"]
            if quantity > current_qty:
                return {"success": False, "message": f"❌ 在庫数（{current_qty}）が不足しています"}

            cursor.execute("""
                UPDATE disposal_requests SET status = 'APPROVED',
                    approved_by = ?, approved_at = datetime('now', '+09:00')
                WHERE id = ? AND status = 'PENDING'
            """, (approver_id, request_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "⚠️ この申請は既に処理済みです"}

            new_quantity = current_qty - quantity
            cursor.execute("UPDATE inventory SET quantity = ?, updated_at = datetime('now', '+09:00') WHERE item_id = ?",
                          (new_quantity, item_id))
            cursor.execute("""
                INSERT INTO inventory_history
                (item_id, change_type, quantity, user_name, note, created_at)
                VALUES (?, 'DISPOSE', ?, ?, ?, datetime('now', '+09:00'))
            """, (item_id, -quantity, request["requester_name"], f"廃棄承認（理由: {request['reason']}）"))
            conn.commit()
            return {"success": True, "message": f"✅ {request['item_name']} の廃棄を承認しました（{quantity}個廃棄、残: {new_quantity}）"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def reject_disposal_request(request_id: int, approver_id: int, reject_reason: str) -> dict:
    """廃棄申請を却下"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT dr.*, i.item_name FROM disposal_requests dr
                JOIN items i ON dr.item_id = i.id WHERE dr.id = ?
            """, (request_id,))
            request = cursor.fetchone()
            if not request:
                return {"success": False, "message": "❌ 申請が見つかりません"}
            if request["status"] != "PENDING":
                return {"success": False, "message": "❌ この申請は既に処理済みです"}
            cursor.execute("""
                UPDATE disposal_requests SET status = 'REJECTED',
                    approved_by = ?, approved_at = datetime('now', '+09:00'),
                    reject_reason = ?
                WHERE id = ? AND status = 'PENDING'
            """, (approver_id, reject_reason, request_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "⚠️ この申請は既に処理済みです"}
            conn.commit()
            return {"success": True, "message": f"✅ {request['item_name']} の廃棄申請を却下しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_disposal_count(status: str = "PENDING") -> int:
    """廃棄申請の件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM disposal_requests WHERE status = ?", (status,))
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception:
        return 0

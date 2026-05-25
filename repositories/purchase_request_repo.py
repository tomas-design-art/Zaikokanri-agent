"""
発注申請リポジトリ

発注申請のライフサイクル管理
（PENDING → APPROVED → ORDERED → RECEIVED）を集約。
"""

from repositories.base import get_db_connection
from utils.date_utils import get_jst_now_str

__all__ = [
    'create_purchase_request',
    'get_purchase_requests',
    'check_items_pending_requests',
    'check_items_ordered_status',
    'get_purchase_request_counts',
    'approve_purchase_request',
    'hold_purchase_request',
    'reject_purchase_request',
    'reset_purchase_request_to_pending',
    'delete_purchase_request',
    'get_approved_requests_for_order',
    'mark_requests_ordered',
    'get_ordered_purchase_requests',
    'receive_purchase_order',
]


def create_purchase_request(
    item_id: int,
    requested_qty: int,
    user_id: int,
    department: str,
    priority: str = "normal",
    due_date: str = None,
    note: str = None
) -> dict:
    """発注申請を作成（USER/ADMIN用）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO purchase_requests 
                (item_id, requested_qty, priority, due_date, note, 
                 requested_by_user_id, requested_by_department, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """, (item_id, requested_qty, priority, due_date, note, user_id, department))
            new_id = cursor.lastrowid
            conn.commit()
            return {"success": True, "message": "発注申請を登録しました", "id": new_id}
    except Exception as e:
        print(f"Error in create_purchase_request: {e}")
        return {"success": False, "message": str(e), "id": None}


def get_purchase_requests(
    status: str = None,
    requester_id: int = None,
    department: str = None
) -> list:
    """発注申請一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            where_clauses = ["pr.deleted_at IS NULL"]
            params = []

            if status:
                where_clauses.append("pr.status = ?")
                params.append(status)
            if requester_id:
                where_clauses.append("pr.requested_by_user_id = ?")
                params.append(requester_id)
            if department:
                where_clauses.append("pr.requested_by_department = ?")
                params.append(department)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            query = f"""
                SELECT 
                    pr.id, pr.item_id, i.item_name, i.item_code, i.vendor_name,
                    i.unit_price,
                    IFNULL(inv.quantity, 0) as current_stock,
                    IFNULL(inv.threshold, 0) as threshold,
                    pr.requested_qty, pr.priority, pr.due_date, pr.note,
                    pr.requested_by_user_id, pr.requested_by_department,
                    u.display_name as requester_name,
                    pr.status, pr.admin_comment, pr.approved_by, pr.approved_at,
                    pr.created_at, pr.updated_at
                FROM purchase_requests pr
                JOIN items i ON pr.item_id = i.id
                LEFT JOIN inventory inv ON i.id = inv.item_id
                LEFT JOIN users u ON pr.requested_by_user_id = u.id
                {where_sql}
                ORDER BY 
                    CASE pr.priority WHEN 'urgent' THEN 0 ELSE 1 END,
                    pr.created_at DESC
            """
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_purchase_requests: {e}")
        return []


def check_items_pending_requests(item_ids: list) -> dict:
    """複数のitem_idについて申請中（PENDING/APPROVED/ON_HOLD）かチェック"""
    if not item_ids:
        return {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            query = f"""
                SELECT DISTINCT item_id
                FROM purchase_requests
                WHERE item_id IN ({placeholders})
                  AND status IN ('PENDING', 'APPROVED', 'ON_HOLD')
            """
            cursor.execute(query, item_ids)
            rows = cursor.fetchall()
            pending_items = {row['item_id'] for row in rows}
            return {item_id: (item_id in pending_items) for item_id in item_ids}
    except Exception as e:
        print(f"Error in check_items_pending_requests: {e}")
        return {item_id: False for item_id in item_ids}


def check_items_ordered_status(item_ids: list) -> dict:
    """複数のitem_idについて発注済み（ORDERED/RECEIVED）かチェック"""
    if not item_ids:
        return {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(item_ids))
            query = f"""
                SELECT item_id, status, requested_qty
                FROM purchase_requests
                WHERE item_id IN ({placeholders})
                  AND status IN ('PENDING', 'APPROVED', 'ON_HOLD', 'ORDERED', 'RECEIVED')
                ORDER BY 
                    CASE status 
                        WHEN 'RECEIVED' THEN 1
                        WHEN 'ORDERED' THEN 2
                        WHEN 'APPROVED' THEN 3
                        WHEN 'PENDING' THEN 4
                        WHEN 'ON_HOLD' THEN 5
                    END
            """
            cursor.execute(query, item_ids)
            rows = cursor.fetchall()

            status_map = {}
            for row in rows:
                item_id = row['item_id']
                status = row['status']
                qty = row['requested_qty']
                if item_id not in status_map:
                    if status == 'RECEIVED':
                        status_map[item_id] = {'status': 'received', 'qty': qty}
                    elif status == 'ORDERED':
                        status_map[item_id] = {'status': 'ordered', 'qty': qty}
                    elif status in ('PENDING', 'APPROVED', 'ON_HOLD'):
                        status_map[item_id] = {'status': 'pending', 'qty': qty}

            return {item_id: status_map.get(item_id) for item_id in item_ids}
    except Exception as e:
        print(f"Error in check_items_ordered_status: {e}")
        return {item_id: None for item_id in item_ids}


def get_purchase_request_counts() -> dict:
    """発注申請のステータス別件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN status = 'ON_HOLD' THEN 1 ELSE 0 END) as on_hold,
                    SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) as rejected,
                    SUM(CASE WHEN status = 'ORDERED' THEN 1 ELSE 0 END) as ordered
                FROM purchase_requests
            """)
            row = cursor.fetchone()
            if row:
                return {
                    "pending": row["pending"] or 0,
                    "approved": row["approved"] or 0,
                    "on_hold": row["on_hold"] or 0,
                    "rejected": row["rejected"] or 0,
                    "ordered": row["ordered"] or 0
                }
            return {"pending": 0, "approved": 0, "on_hold": 0, "rejected": 0, "ordered": 0}
    except Exception as e:
        print(f"Error in get_purchase_request_counts: {e}")
        return {"pending": 0, "approved": 0, "on_hold": 0, "rejected": 0, "ordered": 0}


def approve_purchase_request(request_id: int, admin_user_id: int, comment: str = None) -> dict:
    """発注申請を承認"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM purchase_requests WHERE id = ?", (request_id,))
            result = cursor.fetchone()
            if not result:
                return {"success": False, "message": "申請が見つかりません", "error_code": "NOT_FOUND"}
            current_status = result[0]
            if current_status == 'ORDERED':
                return {"success": False, "message": "この申請は既に発注済みです",
                        "error_code": "ALREADY_ORDERED", "current_status": current_status}
            elif current_status == 'APPROVED':
                return {"success": False, "message": "この申請は既に承認済みです",
                        "error_code": "ALREADY_APPROVED", "current_status": current_status}

            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'APPROVED', approved_by = ?, approved_at = ?,
                    admin_comment = ?, updated_at = ?
                WHERE id = ? AND status IN ('PENDING', 'ON_HOLD', 'REJECTED') AND deleted_at IS NULL
            """, (admin_user_id, now_jst, comment, now_jst, request_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました",
                        "error_code": "UPDATE_FAILED", "current_status": current_status}
            conn.commit()
            return {"success": True, "message": "申請を承認しました"}
    except Exception as e:
        print(f"Error in approve_purchase_request: {e}")
        return {"success": False, "message": str(e), "error_code": "EXCEPTION"}


def hold_purchase_request(request_id: int, admin_user_id: int, comment: str) -> dict:
    """発注申請を保留"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM purchase_requests WHERE id = ?", (request_id,))
            result = cursor.fetchone()
            if not result:
                return {"success": False, "message": "申請が見つかりません", "error_code": "NOT_FOUND"}
            current_status = result[0]
            if current_status == 'ORDERED':
                return {"success": False, "message": "この申請は既に発注済みです",
                        "error_code": "ALREADY_ORDERED", "current_status": current_status}

            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'ON_HOLD', approved_by = ?, approved_at = ?,
                    admin_comment = ?, updated_at = ?
                WHERE id = ? AND status IN ('PENDING', 'ON_HOLD', 'APPROVED', 'REJECTED') AND deleted_at IS NULL
            """, (admin_user_id, now_jst, comment, now_jst, request_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました",
                        "error_code": "UPDATE_FAILED", "current_status": current_status}
            conn.commit()
            return {"success": True, "message": "申請を保留にしました"}
    except Exception as e:
        print(f"Error in hold_purchase_request: {e}")
        return {"success": False, "message": str(e), "error_code": "EXCEPTION"}


def reject_purchase_request(request_id: int, admin_user_id: int, comment: str) -> dict:
    """発注申請を却下"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM purchase_requests WHERE id = ?", (request_id,))
            result = cursor.fetchone()
            if not result:
                return {"success": False, "message": "申請が見つかりません", "error_code": "NOT_FOUND"}
            current_status = result[0]
            if current_status == 'ORDERED':
                return {"success": False, "message": "この申請は既に発注済みです",
                        "error_code": "ALREADY_ORDERED", "current_status": current_status}

            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'REJECTED', approved_by = ?, approved_at = ?,
                    admin_comment = ?, updated_at = ?
                WHERE id = ? AND status IN ('PENDING', 'ON_HOLD', 'APPROVED', 'REJECTED') AND deleted_at IS NULL
            """, (admin_user_id, now_jst, comment, now_jst, request_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました",
                        "error_code": "UPDATE_FAILED", "current_status": current_status}
            conn.commit()
            return {"success": True, "message": "申請を却下しました"}
    except Exception as e:
        print(f"Error in reject_purchase_request: {e}")
        return {"success": False, "message": str(e), "error_code": "EXCEPTION"}


def reset_purchase_request_to_pending(request_id: int, admin_user_id: int, comment: str = None) -> dict:
    """発注申請を承認待ち（PENDING）に戻す"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM purchase_requests WHERE id = ?", (request_id,))
            result = cursor.fetchone()
            if not result:
                return {"success": False, "message": "申請が見つかりません"}
            current_status = result[0]
            if current_status == 'ORDERED':
                return {"success": False, "message": "発注済みの申請は承認待ちに戻せません",
                        "error_code": "ALREADY_ORDERED"}

            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'PENDING', admin_comment = ?, updated_at = ?
                WHERE id = ? AND status IN ('REJECTED', 'ON_HOLD', 'APPROVED') AND deleted_at IS NULL
            """, (comment, now_jst, request_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました（既にPENDINGまたは削除済み）",
                        "error_code": "UPDATE_FAILED"}
            conn.commit()
            return {"success": True, "message": "申請を承認待ちに戻しました"}
    except Exception as e:
        print(f"Error in reset_purchase_request_to_pending: {e}")
        return {"success": False, "message": str(e)}


def delete_purchase_request(request_id: int, deleted_by_user_id: int = None) -> dict:
    """発注申請を削除（論理削除）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, deleted_at FROM purchase_requests WHERE id = ?
            """, (request_id,))
            result = cursor.fetchone()
            if not result:
                return {"success": False, "message": "申請が見つかりません"}
            current_status = result[0]
            deleted_at = result[1]
            if deleted_at:
                return {"success": False, "message": "この申請は既に削除済みです"}
            if current_status == 'ORDERED':
                return {"success": False, "message": "発注済みの申請は削除できません"}

            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET deleted_at = ?, deleted_by = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
            """, (now_jst, deleted_by_user_id, now_jst, request_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "削除に失敗しました"}
            conn.commit()
            return {"success": True, "message": "申請を削除しました"}
    except Exception as e:
        print(f"Error in delete_purchase_request: {e}")
        return {"success": False, "message": str(e)}


def get_approved_requests_for_order() -> list:
    """発注書作成対象（APPROVED）の申請を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    pr.id, pr.item_id, i.item_name, i.item_code, i.vendor_name,
                    i.unit_price, pr.requested_qty, pr.priority, pr.due_date, pr.note,
                    pr.requested_by_department,
                    u.display_name as requester_name
                FROM purchase_requests pr
                JOIN items i ON pr.item_id = i.id
                LEFT JOIN users u ON pr.requested_by_user_id = u.id
                WHERE pr.status = 'APPROVED'
                ORDER BY i.vendor_name, i.item_name
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_approved_requests_for_order: {e}")
        return []


def mark_requests_ordered(request_ids: list, admin_user_id: int,
                          order_channel: str = None, document_name: str = None) -> dict:
    """承認済み申請を発注済み(ORDERED)に更新し、inventory_historyに発注記録を追加"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if not request_ids:
                return {"success": False, "count": 0, "message": "対象がありません"}

            placeholders = ",".join(["?" for _ in request_ids])
            now_jst = get_jst_now_str()

            cursor.execute(f"""
                UPDATE purchase_requests 
                SET status = 'ORDERED', ordered_at = ?, order_channel = ?,
                    generated_document_name = ?, updated_at = ?
                WHERE id IN ({placeholders}) AND status = 'APPROVED' AND deleted_at IS NULL
            """, [now_jst, order_channel, document_name, now_jst] + request_ids)
            count = cursor.rowcount

            cursor.execute(f"""
                SELECT 
                    pr.id, pr.item_id, pr.requested_qty, pr.requested_by_department,
                    pr.requested_by_user_id, i.item_name, i.vendor_name, i.unit_price,
                    u.display_name as requester_name
                FROM purchase_requests pr
                LEFT JOIN items i ON pr.item_id = i.id
                LEFT JOIN users u ON pr.requested_by_user_id = u.id
                WHERE pr.id IN ({placeholders})
            """, request_ids)
            requests = cursor.fetchall()

            for req in requests:
                item_id = req['item_id']
                quantity = req['requested_qty']
                unit_price = req['unit_price'] or 0
                total_price = quantity * unit_price
                vendor_name = req['vendor_name']
                department = req['requested_by_department']
                user_name = req['requester_name'] if req['requester_name'] else 'Unknown'
                cursor.execute("""
                    INSERT INTO inventory_history (
                        item_id, change_type, quantity, user_name, department,
                        status, vendor_name, unit_price, total_price,
                        created_by, note, created_at
                    ) VALUES (?, 'ORDER', ?, ?, ?, 'CONFIRMED', ?, ?, ?, ?, ?, ?)
                """, (item_id, quantity, user_name, department, vendor_name,
                      unit_price, total_price, admin_user_id,
                      f"発注確定（{order_channel or '不明'}）", now_jst))

            conn.commit()
            return {"success": True, "count": count,
                    "message": f"{count}件を発注済みにし、履歴に記録しました"}
    except Exception as e:
        print(f"Error in mark_requests_ordered: {e}")
        return {"success": False, "count": 0, "message": str(e)}


def get_ordered_purchase_requests(department_name=None) -> list:
    """発注済み（ORDERED）で入庫待ちの申請を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    pr.id, pr.item_id, i.item_name, i.item_code, i.vendor_name,
                    i.unit_price, pr.requested_qty, pr.priority, pr.due_date, pr.note,
                    pr.requested_by_department, pr.ordered_at, pr.order_channel,
                    pr.generated_document_name,
                    u.display_name as requester_name,
                    approver.display_name as approver_name
                FROM purchase_requests pr
                JOIN items i ON pr.item_id = i.id
                LEFT JOIN users u ON pr.requested_by_user_id = u.id
                LEFT JOIN users approver ON pr.approved_by = approver.id
                WHERE pr.status = 'ORDERED' AND pr.deleted_at IS NULL
            """
            params = []
            if department_name:
                query += " AND pr.requested_by_department = ?"
                params.append(department_name)
            query += " ORDER BY pr.ordered_at DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_ordered_purchase_requests: {e}")
        return []


def receive_purchase_order(request_id: int, received_qty: int,
                           received_note: str, user_id: int) -> dict:
    """発注品の入庫処理を実行"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    pr.item_id, pr.requested_qty, pr.requested_by_department,
                    i.item_name, i.item_code,
                    inv.quantity as current_stock, i.unit_price, i.vendor_name,
                    u.display_name as receiver_name
                FROM purchase_requests pr
                JOIN items i ON pr.item_id = i.id
                LEFT JOIN inventory inv ON i.id = inv.item_id
                LEFT JOIN users u ON u.id = ?
                WHERE pr.id = ? AND pr.status = 'ORDERED' AND pr.deleted_at IS NULL
            """, (user_id, request_id))
            request_info = cursor.fetchone()
            if not request_info:
                return {"success": False, "message": "対象の発注申請が見つかりません"}

            item_id = request_info['item_id']
            item_name = request_info['item_name']
            current_stock = request_info['current_stock'] or 0
            unit_price = request_info['unit_price'] or 0
            vendor_name = request_info['vendor_name']
            department = request_info['requested_by_department']
            receiver_name = request_info['receiver_name']

            new_quantity = current_stock + received_qty
            now_jst = get_jst_now_str()

            cursor.execute("""
                UPDATE inventory SET quantity = ?, updated_at = ? WHERE item_id = ?
            """, (new_quantity, now_jst, item_id))

            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'RECEIVED', received_at = ?, received_by = ?,
                    received_qty = ?, received_note = ?, updated_at = ?
                WHERE id = ?
            """, (now_jst, user_id, received_qty, received_note, now_jst, request_id))

            total_price = received_qty * unit_price
            note_text = f"発注品入庫（申請ID: {request_id}）"
            if received_note:
                note_text += f" - {received_note}"

            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, user_name, department,
                    status, vendor_name, unit_price, total_price,
                    created_by, note, created_at
                ) VALUES (?, 'IN', ?, ?, ?, 'CONFIRMED', ?, ?, ?, ?, ?, ?)
            """, (item_id, received_qty, receiver_name or 'Unknown', department,
                  vendor_name, unit_price, total_price, user_id, note_text, now_jst))
            history_id = cursor.lastrowid

            conn.commit()
            return {
                "success": True,
                "message": f"{item_name} を {received_qty} 個入庫しました",
                "item_name": item_name,
                "new_quantity": new_quantity,
                "history_id": history_id
            }
    except Exception as e:
        print(f"Error in receive_purchase_order: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"エラー: {str(e)}"}

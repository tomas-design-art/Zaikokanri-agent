"""
承認待ちリポジトリ

ゲストユーザーの承認待ちトランザクション操作を集約。
"""

from repositories.base import get_db_connection

__all__ = [
    'validate_quantity_for_order',
    'create_pending_transaction',
    'get_pending_transactions',
    'get_pending_count',
    'approve_pending_transaction',
    'reject_pending_transaction',
    'get_my_pending_transactions',
    'cancel_pending_transaction',
    'get_pending_for_history',
]

QUANTITY_LIMITS = {
    "outbound_max": 1000,
    "inbound_max": 10000,
    "warning_threshold": 100,
}


def validate_quantity_for_order(change_type: str, quantity: int, item_id: int = None) -> dict:
    """数量の妥当性チェック（将来の自動発注連携用フック）"""
    result = {"valid": True, "warning": None, "error": None}

    if change_type == 'OUT' and quantity > QUANTITY_LIMITS["outbound_max"]:
        result["valid"] = False
        result["error"] = f"出庫数量が上限（{QUANTITY_LIMITS['outbound_max']}個）を超えています"
        return result

    if change_type == 'IN' and quantity > QUANTITY_LIMITS["inbound_max"]:
        result["valid"] = False
        result["error"] = f"入庫数量が上限（{QUANTITY_LIMITS['inbound_max']}個）を超えています"
        return result

    if quantity > QUANTITY_LIMITS["warning_threshold"]:
        result["warning"] = f"数量が{QUANTITY_LIMITS['warning_threshold']}個を超えています。入力ミスでないかご確認ください。"

    return result


def create_pending_transaction(change_type: str, item_id: int, quantity: int,
                                actor_name: str, note: str, guest_user_id: int,
                                department_id: int) -> dict:
    """ゲストユーザーの申請を作成（PENDING状態）"""
    if change_type not in ['IN', 'OUT']:
        return {"success": False, "message": "❌ 無効な処理種別です"}

    if not actor_name or actor_name.strip() == "":
        return {"success": False, "message": "❌ 実行者名は必須です"}

    qty_validation = validate_quantity_for_order(change_type, quantity, item_id)
    if not qty_validation["valid"]:
        return {"success": False, "message": f"❌ {qty_validation['error']}"}

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT item_name FROM items WHERE id = ?", (item_id,))
            item = cursor.fetchone()
            if not item:
                return {"success": False, "message": "❌ 物品が見つかりません"}

            item_name = item["item_name"]

            if change_type == 'OUT':
                cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
                inv = cursor.fetchone()
                current_qty = inv["quantity"] if inv else 0
                if quantity > current_qty:
                    return {"success": False, "message": f"❌ 在庫不足です（現在: {current_qty}個）"}

            cursor.execute("""
                INSERT INTO pending_transactions 
                (change_type, item_id, quantity, actor_name, note, guest_user_id, department_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', datetime('now', '+09:00'))
            """, (change_type, item_id, quantity, actor_name.strip(), note, guest_user_id, department_id))

            conn.commit()

            type_label = "入庫" if change_type == "IN" else "出庫"
            return {
                "success": True,
                "message": f"📝 {type_label}申請完了: {item_name} × {quantity} 個（承認待ち）"
            }
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_pending_transactions(department_id: int = None, status: str = "PENDING") -> list:
    """申請一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT 
                    pt.id, pt.change_type, pt.item_id, pt.quantity, 
                    pt.actor_name, pt.note, pt.guest_user_id, pt.department_id,
                    pt.status, pt.approved_by, pt.approved_at, pt.reject_reason,
                    pt.created_at,
                    i.item_name, i.item_code,
                    d.name as department_name,
                    u.display_name as guest_display_name
                FROM pending_transactions pt
                JOIN items i ON pt.item_id = i.id
                JOIN departments d ON pt.department_id = d.id
                JOIN users u ON pt.guest_user_id = u.id
                WHERE pt.status = ?
            """
            params = [status]

            if department_id is not None:
                query += " AND pt.department_id = ?"
                params.append(department_id)

            query += " ORDER BY pt.created_at DESC"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def get_pending_count(department_id: int = None) -> int:
    """PENDING状態の申請件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if department_id is not None:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM pending_transactions 
                    WHERE status = 'PENDING' AND department_id = ?
                """, (department_id,))
            else:
                cursor.execute("SELECT COUNT(*) as count FROM pending_transactions WHERE status = 'PENDING'")

            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception:
        return 0


def approve_pending_transaction(pending_id: int, approver_user_id: int) -> dict:
    """申請を承認し、在庫を更新・履歴に記録"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT pt.*, i.item_name, u.display_name as approver_name
                FROM pending_transactions pt
                JOIN items i ON pt.item_id = i.id
                JOIN users u ON u.id = ?
                WHERE pt.id = ? AND pt.status = 'PENDING'
            """, (approver_user_id, pending_id))
            pending = cursor.fetchone()

            if not pending:
                return {"success": False, "message": "❌ 申請が見つかりません（既に処理済みの可能性があります）"}

            item_id = pending["item_id"]
            item_name = pending["item_name"]
            change_type = pending["change_type"]
            quantity = pending["quantity"]
            actor_name = pending["actor_name"]
            department_id = pending["department_id"]
            note = pending["note"] or ""
            approver_name = pending["approver_name"]

            cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
            inv = cursor.fetchone()
            current_qty = inv["quantity"] if inv else 0

            if change_type == "OUT":
                new_qty = current_qty - quantity
                if new_qty < 0:
                    return {"success": False, "message": f"❌ 在庫不足です（現在: {current_qty}個）"}
            else:
                new_qty = current_qty + quantity

            cursor.execute("""
                UPDATE inventory SET quantity = ?, updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_qty, item_id))

            cursor.execute("SELECT name FROM departments WHERE id = ?", (department_id,))
            dept = cursor.fetchone()
            dept_name = dept["name"] if dept else ""

            history_note = f"[承認済] {note} (実行者: {actor_name}, 承認者: {approver_name})"
            cursor.execute("""
                INSERT INTO inventory_history 
                (item_id, change_type, quantity, user_name, department, status, note, created_at)
                VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, change_type, quantity, actor_name, dept_name, history_note))

            cursor.execute("""
                UPDATE pending_transactions 
                SET status = 'APPROVED', approved_by = ?, approved_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (approver_user_id, pending_id))

            conn.commit()

            type_label = "入庫" if change_type == "IN" else "出庫"
            return {
                "success": True,
                "message": f"✅ 承認完了: {item_name} {type_label} {quantity} 個（在庫: {new_qty}個）"
            }
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def reject_pending_transaction(pending_id: int, approver_user_id: int, reason: str = "") -> dict:
    """申請を却下"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT pt.*, i.item_name
                FROM pending_transactions pt
                JOIN items i ON pt.item_id = i.id
                WHERE pt.id = ? AND pt.status = 'PENDING'
            """, (pending_id,))
            pending = cursor.fetchone()

            if not pending:
                return {"success": False, "message": "❌ 申請が見つかりません"}

            item_name = pending["item_name"]
            change_type = pending["change_type"]
            quantity = pending["quantity"]

            cursor.execute("""
                UPDATE pending_transactions 
                SET status = 'REJECTED', approved_by = ?, approved_at = datetime('now', '+09:00'),
                    reject_reason = ?
                WHERE id = ?
            """, (approver_user_id, reason, pending_id))

            conn.commit()

            type_label = "入庫" if change_type == "IN" else "出庫"
            return {
                "success": True,
                "message": f"❌ 却下完了: {item_name} {type_label} {quantity} 個"
            }
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_my_pending_transactions(user_id: int = None, department_id: int = None,
                                 change_type: str = None, user_role: str = "GUEST") -> list:
    """自分/自部署の申請一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT pt.id, pt.change_type, pt.item_id, pt.quantity,
                    pt.actor_name, pt.note, pt.guest_user_id, pt.department_id,
                    pt.status, pt.approved_by, pt.approved_at, pt.reject_reason,
                    pt.created_at,
                    i.item_name, i.item_code,
                    d.name as department_name
                FROM pending_transactions pt
                JOIN items i ON pt.item_id = i.id
                LEFT JOIN departments d ON pt.department_id = d.id
                WHERE pt.status = 'PENDING'
            """
            params = []

            if user_role == "GUEST" and user_id is not None:
                query += " AND pt.guest_user_id = ?"
                params.append(user_id)
            elif user_role == "USER" and department_id is not None:
                query += " AND pt.department_id = ?"
                params.append(department_id)

            if change_type:
                query += " AND pt.change_type = ?"
                params.append(change_type)

            query += " ORDER BY pt.created_at DESC LIMIT 10"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def cancel_pending_transaction(pending_id: int, user_id: int, actor_name: str = None) -> dict:
    """申請を取り下げ（CANCELLED に更新）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT pt.*, i.item_name
                FROM pending_transactions pt
                JOIN items i ON pt.item_id = i.id
                WHERE pt.id = ? AND pt.status = 'PENDING'
            """, (pending_id,))
            pending = cursor.fetchone()

            if not pending:
                return {"success": False, "message": "❌ 申請が見つかりません（既に処理済みの可能性があります）"}

            if pending["guest_user_id"] != user_id:
                return {"success": False, "message": "❌ この申請を取り下げる権限がありません（ユーザーID不一致）"}

            if actor_name is None or pending["actor_name"] != actor_name:
                return {"success": False, "message": "❌ この申請を取り下げる権限がありません（申請者名不一致）"}

            item_name = pending["item_name"]
            change_type = pending["change_type"]
            quantity = pending["quantity"]

            cursor.execute("""
                UPDATE pending_transactions 
                SET status = 'CANCELLED', approved_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (pending_id,))

            conn.commit()

            type_label = "入庫" if change_type == "IN" else "出庫"
            return {
                "success": True,
                "message": f"✅ 申請を取り下げました: {item_name} {type_label} {quantity} 個"
            }
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_pending_for_history(user_id: int = None, department_id: int = None,
                            user_role: str = "GUEST") -> list:
    """履歴ページ用の申請一覧を取得（PENDING状態のもの）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT pt.id, pt.change_type, pt.item_id, pt.quantity,
                    pt.actor_name, pt.note, pt.guest_user_id, pt.department_id,
                    pt.status, pt.approved_by, pt.approved_at, pt.reject_reason,
                    pt.created_at,
                    i.item_name, i.item_code,
                    d.name as department_name
                FROM pending_transactions pt
                JOIN items i ON pt.item_id = i.id
                LEFT JOIN departments d ON pt.department_id = d.id
                WHERE pt.status = 'PENDING'
            """
            params = []

            if user_role == "GUEST" and user_id is not None:
                query += " AND pt.guest_user_id = ?"
                params.append(user_id)
            elif user_role == "USER" and department_id is not None:
                query += " AND pt.department_id = ?"
                params.append(department_id)

            query += " ORDER BY pt.created_at DESC"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []

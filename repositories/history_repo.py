"""
履歴リポジトリ

入出庫履歴の参照・取消（undo）・在庫調整を集約。
"""

from collections import Counter
from typing import Optional

from repositories.base import get_db_connection
from utils.date_utils import get_jst_now_str

__all__ = [
    'get_history_list',
    'get_recent_history_for_undo',
    'can_undo_history',
    'is_history_undone',
    'get_history_by_id',
    'process_undo',
    'process_undo_pending',
    'process_adjust',
]


def get_history_list(period_days: Optional[int] = None,
                     change_type: str = "すべて",
                     search_query: str = "") -> list:
    """履歴一覧を取得（フィルタ対応）"""
    print(f"[DEBUG] get_history_list called: period_days={period_days}, change_type='{change_type}', search_query='{search_query}'")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        where_clauses = ["1=1"]
        params = []

        if period_days is not None:
            where_clauses.append("h.created_at >= datetime('now', '+09:00', ?)")
            params.append(f'-{period_days} days')

        if change_type and change_type != "すべて":
            where_clauses.append("h.change_type = ?")
            params.append(change_type)

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT 
                h.id,
                h.item_id,
                h.change_type,
                h.quantity,
                h.user_name,
                h.department,
                h.status,
                h.note,
                h.created_at,
                h.vendor_name,
                h.unit_price,
                h.total_price
            FROM inventory_history h
            WHERE {where_sql}
            ORDER BY h.created_at DESC
        """

        cursor.execute(sql, params)
        history_rows = cursor.fetchall()

        print(f"[DEBUG] SQL executed, fetched {len(history_rows)} rows with change_type filter: {change_type}")
        if len(history_rows) > 0:
            print(f"[DEBUG] First 3 rows change_types: {[dict(r)['change_type'] for r in history_rows[:3]]}")

        result = []
        for row in history_rows:
            record = dict(row)

            cursor.execute("""
                SELECT item_name, item_code FROM items WHERE id = ?
            """, (record['item_id'],))
            item_info = cursor.fetchone()

            if item_info:
                record['item_name'] = item_info['item_name']
                record['item_code'] = item_info['item_code']

                if search_query and search_query.strip():
                    search_param = search_query.strip().lower()
                    if (search_param not in (item_info['item_name'] or '').lower() and
                        search_param not in (item_info['item_code'] or '').lower()):
                        continue
            else:
                record['item_name'] = '不明'
                record['item_code'] = '不明'

            cursor.execute("""
                SELECT location FROM inventory WHERE item_id = ? LIMIT 1
            """, (record['item_id'],))
            inv_info = cursor.fetchone()
            record['location'] = inv_info['location'] if inv_info else None

            result.append(record)

        print(f"[DEBUG] Returning {len(result)} records after item/location join")
        if len(result) > 0:
            print(f"[DEBUG] Result change_types: {Counter([r['change_type'] for r in result])}")

        return result


def get_recent_history_for_undo(change_type: str, limit: int = 5) -> list:
    """直近の履歴を取得（取消UI表示用、取消済みは除外）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                h.id, h.item_id, h.change_type, h.quantity, 
                h.user_name, h.department, h.note, h.created_at,
                i.item_name, i.item_code
            FROM inventory_history h
            LEFT JOIN items i ON h.item_id = i.id
            WHERE h.change_type = ?
              AND h.note NOT LIKE '%[UNDO]%'
              AND h.id NOT IN (
                  SELECT CAST(SUBSTR(note, INSTR(note, 'tx_id=') + 6, 
                         INSTR(SUBSTR(note, INSTR(note, 'tx_id=') + 6), ']') - 1) AS INTEGER)
                  FROM inventory_history 
                  WHERE note LIKE '%[UNDO of tx_id=%'
              )
            ORDER BY h.created_at DESC
            LIMIT ?
        """, (change_type, limit))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def can_undo_history(history_id: int, minutes: int = 10) -> tuple:
    """履歴が取消可能かどうかをチェック"""
    if is_history_undone(history_id):
        return (False, "取消済み")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT created_at FROM inventory_history WHERE id = ?
        """, (history_id,))
        row = cursor.fetchone()

        if not row:
            return (False, "取引が見つかりません")

        cursor.execute("""
            SELECT CASE 
                WHEN datetime(?) >= datetime('now', '+09:00', ?) 
                THEN 1 ELSE 0 
            END as can_undo
        """, (row["created_at"], f'-{minutes} minutes'))

        result = cursor.fetchone()
        if result["can_undo"] == 1:
            return (True, "取消可能")
        else:
            return (False, "10分以上経過")


def is_history_undone(history_id: int) -> bool:
    """指定の履歴が既に取り消し済みかどうかをチェック"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM inventory_history 
            WHERE note LIKE ?
        """, (f"%[UNDO of tx_id={history_id}]%",))
        result = cursor.fetchone()
        return result["cnt"] > 0


def get_history_by_id(history_id: int) -> Optional[dict]:
    """履歴IDから履歴レコードを取得"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                h.id, h.item_id, h.change_type, h.quantity, 
                h.user_name, h.department, h.note, h.created_at,
                i.item_name
            FROM inventory_history h
            LEFT JOIN items i ON h.item_id = i.id
            WHERE h.id = ?
        """, (history_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def process_undo(history_id: int, undo_user_name: str) -> dict:
    """取り消し処理を実行（逆取引を追加）"""
    try:
        if is_history_undone(history_id):
            return {
                "success": False,
                "message": "❌ この取引は既に取り消し済みです"
            }

        original = get_history_by_id(history_id)
        if not original:
            return {
                "success": False,
                "message": "❌ 指定された取引が見つかりません"
            }

        item_id = original["item_id"]
        original_type = original["change_type"]
        original_quantity = original["quantity"]
        item_name = original["item_name"]

        if original_type == "OUT":
            reverse_type = "IN"
            quantity_delta = original_quantity
        else:
            reverse_type = "OUT"
            quantity_delta = -original_quantity

        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
            inv = cursor.fetchone()

            if not inv:
                return {"success": False, "message": "❌ 在庫情報が見つかりません"}

            current_quantity = inv["quantity"]
            new_quantity = current_quantity + quantity_delta

            if new_quantity < 0:
                return {
                    "success": False,
                    "message": f"❌ 取消できません（在庫不足: 現在 {current_quantity} 個）"
                }

            cursor.execute("""
                UPDATE inventory 
                SET quantity = ?, updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))

            undo_note = f"[UNDO of tx_id={history_id}] 取消操作"
            cursor.execute("""
                INSERT INTO inventory_history 
                (item_id, change_type, quantity, user_name, department, status, note, created_at)
                VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, reverse_type, original_quantity, undo_user_name,
                  original.get("department", ""), undo_note))

            # 発注品入庫の取り消しの場合、purchase_requestsのステータスをORDEREDに戻す
            if original_type == "IN" and original.get("note") and "発注品入庫（申請ID:" in original.get("note", ""):
                import re
                match = re.search(r"申請ID:\s*(\d+)", original.get("note", ""))
                if match:
                    request_id = int(match.group(1))
                    now_jst = get_jst_now_str()
                    cursor.execute("""
                        UPDATE purchase_requests 
                        SET status = 'ORDERED',
                            received_at = NULL,
                            received_by = NULL,
                            received_qty = NULL,
                            received_note = NULL,
                            updated_at = ?
                        WHERE id = ? AND status = 'RECEIVED'
                    """, (now_jst, request_id))

            conn.commit()

            type_label = "出庫" if original_type == "OUT" else "入庫"
            return {
                "success": True,
                "message": f"✅ {item_name} の{type_label} {original_quantity} 個を取り消しました（在庫: {new_quantity} 個）"
            }

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def process_undo_pending(history_id: int, undo_user_name: str, department: str = "") -> dict:
    """ゲストユーザー用の取消申請（在庫は変更せず、申請のみ記録）"""
    try:
        original = get_history_by_id(history_id)
        if not original:
            return {"success": False, "message": "❌ 履歴が見つかりません"}

        if not can_undo_history(history_id):
            return {"success": False, "message": "❌ 取消可能時間を過ぎています（10分以内）"}

        if is_history_undone(history_id):
            return {"success": False, "message": "❌ この履歴は既に取り消されています"}

        item_id = original["item_id"]
        original_type = original["change_type"]
        original_quantity = original["quantity"]
        item_name = original["item_name"]

        if original_type == "OUT":
            reverse_type = "IN"
        else:
            reverse_type = "OUT"

        with get_db_connection() as conn:
            cursor = conn.cursor()

            undo_note = f"[UNDO申請 of tx_id={history_id}] 取消申請（承認待ち）"
            cursor.execute("""
                INSERT INTO inventory_history 
                (item_id, change_type, quantity, user_name, department, status, note, created_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, datetime('now', '+09:00'))
            """, (item_id, reverse_type, original_quantity, undo_user_name, department, undo_note))

            conn.commit()

            type_label = "出庫" if original_type == "OUT" else "入庫"
            return {
                "success": True,
                "message": f"📝 取消申請完了: {item_name} の{type_label} {original_quantity} 個（管理者の承認待ち）"
            }

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def process_adjust(item_id: int, new_quantity: int, user_name: str,
                   department: str = "", reason: str = "") -> dict:
    """在庫調整を実行（管理者専用：数量を任意に設定し、差分を履歴に記録）"""
    if not reason or reason.strip() == "":
        return {"success": False, "message": "❌ 調整理由は必須です"}

    if new_quantity < 0:
        return {"success": False, "message": "❌ 数量は0以上で指定してください"}

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT i.id, i.item_name, inv.quantity
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.id = ?
            """, (item_id,))
            result = cursor.fetchone()

            if not result:
                return {"success": False, "message": "❌ 物品が見つかりません"}

            item_name = result["item_name"]
            old_quantity = result["quantity"] if result["quantity"] is not None else 0

            quantity_diff = new_quantity - old_quantity

            if quantity_diff == 0:
                return {"success": False, "message": "⚠️ 数量に変更がありません"}

            cursor.execute("""
                UPDATE inventory
                SET quantity = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))

            adjust_note = f"[ADJUST] {reason.strip()} (変更: {old_quantity} → {new_quantity})"
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, 
                    user_name, department, status, note, created_at
                ) VALUES (?, 'ADJUST', ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, abs(quantity_diff), user_name, department, adjust_note))

            conn.commit()

            direction = "増加" if quantity_diff > 0 else "減少"
            return {
                "success": True,
                "message": f"✅ 調整完了: {item_name} ({old_quantity} → {new_quantity}個, {direction}: {abs(quantity_diff)}個)",
                "old_quantity": old_quantity,
                "new_quantity": new_quantity
            }

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}

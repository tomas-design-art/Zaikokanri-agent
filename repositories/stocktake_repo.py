"""
棚卸しリポジトリ

棚卸しセッション・記録・テンプレートのCRUD操作を集約。
"""

import sqlite3
from repositories.base import get_db_connection

__all__ = [
    'create_stocktake_session',
    'get_stocktake_sessions',
    'get_stocktake_session_by_id',
    'update_stocktake_session_status',
    'initialize_stocktake_records',
    'get_stocktake_records',
    'update_stocktake_record_count',
    'verify_stocktake_record',
    'approve_stocktake_record',
    'batch_verify_stocktake_records',
    'batch_approve_stocktake_records',
    'apply_stocktake_adjustments',
    'get_stocktake_summary',
    'get_stocktake_diff_records',
    'create_stocktake_template',
    'get_stocktake_templates',
    'get_stocktake_template_by_id',
    'update_stocktake_template',
    'set_template_mappings',
    'get_template_mappings',
    'delete_stocktake_session',
]


def create_stocktake_session(name: str, start_date: str, end_date: str = None,
                              note: str = "", created_by: int = None) -> dict:
    """棚卸しセッションを作成"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stocktake_sessions (name, start_date, end_date, note, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', '+09:00'))
            """, (name, start_date, end_date, note, created_by))
            session_id = cursor.lastrowid
            conn.commit()
            return {"success": True, "message": f"✅ 棚卸しセッション「{name}」を作成しました", "session_id": session_id}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_stocktake_sessions(status: str = None) -> list:
    """棚卸しセッション一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT s.*, u.display_name as creator_name
                    FROM stocktake_sessions s
                    LEFT JOIN users u ON s.created_by = u.id
                    WHERE s.status = ?
                    ORDER BY s.created_at DESC
                """, (status,))
            else:
                cursor.execute("""
                    SELECT s.*, u.display_name as creator_name
                    FROM stocktake_sessions s
                    LEFT JOIN users u ON s.created_by = u.id
                    ORDER BY s.created_at DESC
                """)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error in get_stocktake_sessions: {e}")
        return []


def get_stocktake_session_by_id(session_id: int) -> dict:
    """棚卸しセッションを取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.*, u.display_name as creator_name
                FROM stocktake_sessions s
                LEFT JOIN users u ON s.created_by = u.id
                WHERE s.id = ?
            """, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"Error in get_stocktake_session_by_id: {e}")
        return None


def update_stocktake_session_status(session_id: int, status: str) -> dict:
    """棚卸しセッションのステータスを更新"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if status == "CLOSED":
                cursor.execute("""
                    UPDATE stocktake_sessions
                    SET status = ?, closed_at = datetime('now', '+09:00')
                    WHERE id = ?
                """, (status, session_id))
            else:
                cursor.execute("""
                    UPDATE stocktake_sessions SET status = ? WHERE id = ?
                """, (status, session_id))
            conn.commit()
            return {"success": True, "message": f"✅ セッションステータスを {status} に更新しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def initialize_stocktake_records(session_id: int) -> dict:
    """棚卸し対象物品の記録を一括生成"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO stocktake_records (session_id, item_id, system_qty, status)
                SELECT ?, i.id, COALESCE(inv.quantity, 0), 'PENDING'
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.is_active = 1
                  AND COALESCE(i.is_inventory_target, 1) = 1
            """, (session_id,))
            count = cursor.rowcount
            conn.commit()
            return {"success": True, "message": f"✅ {count}件の棚卸し記録を生成しました", "count": count}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_stocktake_records(session_id: int, status: str = None,
                           category: str = None, department: str = None,
                           search: str = None) -> list:
    """棚卸し記録一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT sr.*, i.item_name, i.item_code, i.category, i.department_tags,
                       i.vendor_name, i.unit_price, i.is_asset, i.location_text,
                       inv.location as inv_location,
                       cb.display_name as counted_by_name,
                       vb.display_name as verified_by_name,
                       ab.display_name as approved_by_name
                FROM stocktake_records sr
                JOIN items i ON sr.item_id = i.id
                LEFT JOIN inventory inv ON i.id = inv.item_id
                LEFT JOIN users cb ON sr.counted_by = cb.id
                LEFT JOIN users vb ON sr.verified_by = vb.id
                LEFT JOIN users ab ON sr.approved_by = ab.id
                WHERE sr.session_id = ?
            """
            params = [session_id]

            if status:
                query += " AND sr.status = ?"
                params.append(status)
            if category:
                query += " AND i.category = ?"
                params.append(category)
            if department:
                query += " AND i.department_tags LIKE ?"
                params.append(f"%{department}%")
            if search:
                query += " AND (i.item_name LIKE ? OR i.item_code LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])

            query += " ORDER BY i.category, i.item_name"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error in get_stocktake_records: {e}")
        return []


def update_stocktake_record_count(record_id: int, actual_qty: int,
                                    counted_by: int, note: str = "") -> dict:
    """棚卸し記録の実数を更新（現場入力）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT system_qty FROM stocktake_records WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "❌ 記録が見つかりません"}

            system_qty = row["system_qty"]
            diff_qty = actual_qty - system_qty

            cursor.execute("""
                UPDATE stocktake_records
                SET actual_qty = ?, diff_qty = ?, counted_by = ?,
                    counted_at = datetime('now', '+09:00'),
                    note = ?, status = 'COUNTED'
                WHERE id = ?
            """, (actual_qty, diff_qty, counted_by, note, record_id))
            conn.commit()
            return {"success": True, "message": "✅ 実数を記録しました", "diff_qty": diff_qty}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def verify_stocktake_record(record_id: int, verified_by: int) -> dict:
    """棚卸し記録を確認（総務確認）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE stocktake_records
                SET verified_by = ?, verified_at = datetime('now', '+09:00'),
                    status = 'VERIFIED'
                WHERE id = ? AND status = 'COUNTED'
            """, (verified_by, record_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "❌ 確認対象の記録が見つかりません（ステータス不正）"}
            conn.commit()
            return {"success": True, "message": "✅ 確認しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def approve_stocktake_record(record_id: int, approved_by: int) -> dict:
    """棚卸し記録を承認（上長承認）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE stocktake_records
                SET approved_by = ?, approved_at = datetime('now', '+09:00'),
                    status = 'APPROVED'
                WHERE id = ? AND status = 'VERIFIED'
            """, (approved_by, record_id))
            if cursor.rowcount == 0:
                return {"success": False, "message": "❌ 承認対象の記録が見つかりません（ステータス不正）"}
            conn.commit()
            return {"success": True, "message": "✅ 承認しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def batch_verify_stocktake_records(record_ids: list, verified_by: int) -> dict:
    """棚卸し記録を一括確認"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            success_count = 0
            for rid in record_ids:
                cursor.execute("""
                    UPDATE stocktake_records
                    SET verified_by = ?, verified_at = datetime('now', '+09:00'),
                        status = 'VERIFIED'
                    WHERE id = ? AND status = 'COUNTED'
                """, (verified_by, rid))
                success_count += cursor.rowcount
            conn.commit()
            return {"success": True, "message": f"✅ {success_count}件を確認しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def batch_approve_stocktake_records(record_ids: list, approved_by: int) -> dict:
    """棚卸し記録を一括承認"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            success_count = 0
            for rid in record_ids:
                cursor.execute("""
                    UPDATE stocktake_records
                    SET approved_by = ?, approved_at = datetime('now', '+09:00'),
                        status = 'APPROVED'
                    WHERE id = ? AND status = 'VERIFIED'
                """, (approved_by, rid))
                success_count += cursor.rowcount
            conn.commit()
            return {"success": True, "message": f"✅ {success_count}件を承認しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def apply_stocktake_adjustments(session_id: int, user_name: str,
                                  department: str = "") -> dict:
    """承認済み棚卸し記録を在庫に反映（差異分を調整）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sr.id, sr.item_id, sr.system_qty, sr.actual_qty, sr.diff_qty,
                       i.item_name
                FROM stocktake_records sr
                JOIN items i ON sr.item_id = i.id
                WHERE sr.session_id = ? AND sr.status = 'APPROVED' AND sr.diff_qty != 0
            """, (session_id,))
            records = cursor.fetchall()

            if not records:
                return {"success": True, "message": "⚠️ 反映対象の記録がありません（差異なし）"}

            adjusted_count = 0
            for rec in records:
                cursor.execute("""
                    UPDATE inventory SET quantity = ?, updated_at = datetime('now', '+09:00')
                    WHERE item_id = ?
                """, (rec["actual_qty"], rec["item_id"]))
                adjust_note = f"[棚卸し調整] セッションID:{session_id} ({rec['system_qty']} → {rec['actual_qty']})"
                cursor.execute("""
                    INSERT INTO inventory_history (
                        item_id, change_type, quantity,
                        user_name, department, status, note, created_at
                    ) VALUES (?, 'ADJUST', ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
                """, (rec["item_id"], abs(rec["diff_qty"]), user_name, department, adjust_note))
                cursor.execute("UPDATE stocktake_records SET status = 'APPLIED' WHERE id = ?", (rec["id"],))
                adjusted_count += 1

            conn.commit()
            return {"success": True, "message": f"✅ {adjusted_count}件の在庫調整を反映しました",
                    "adjusted_count": adjusted_count}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_stocktake_summary(session_id: int) -> dict:
    """棚卸しセッションのサマリー情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total_items,
                    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending_count,
                    SUM(CASE WHEN status = 'COUNTED' THEN 1 ELSE 0 END) as counted_count,
                    SUM(CASE WHEN status = 'VERIFIED' THEN 1 ELSE 0 END) as verified_count,
                    SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) as approved_count,
                    SUM(CASE WHEN status = 'APPLIED' THEN 1 ELSE 0 END) as applied_count,
                    SUM(CASE WHEN diff_qty != 0 AND actual_qty IS NOT NULL THEN 1 ELSE 0 END) as diff_count,
                    SUM(CASE WHEN diff_qty > 0 THEN diff_qty ELSE 0 END) as total_surplus,
                    SUM(CASE WHEN diff_qty < 0 THEN ABS(diff_qty) ELSE 0 END) as total_shortage
                FROM stocktake_records
                WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else {}
    except Exception as e:
        print(f"Error in get_stocktake_summary: {e}")
        return {}


def get_stocktake_diff_records(session_id: int) -> list:
    """差異ありの棚卸し記録を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sr.*, i.item_name, i.item_code, i.category, i.unit_price,
                       i.department_tags, i.location_text,
                       cb.display_name as counted_by_name,
                       vb.display_name as verified_by_name,
                       ab.display_name as approved_by_name
                FROM stocktake_records sr
                JOIN items i ON sr.item_id = i.id
                LEFT JOIN users cb ON sr.counted_by = cb.id
                LEFT JOIN users vb ON sr.verified_by = vb.id
                LEFT JOIN users ab ON sr.approved_by = ab.id
                WHERE sr.session_id = ? AND sr.diff_qty != 0 AND sr.actual_qty IS NOT NULL
                ORDER BY ABS(sr.diff_qty) DESC
            """, (session_id,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error in get_stocktake_diff_records: {e}")
        return []


# --- テンプレート管理 ---

def create_stocktake_template(name: str, description: str = "",
                                file_type: str = "excel") -> dict:
    """棚卸しテンプレートを作成"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stocktake_templates (name, description, file_type, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now', '+09:00'), datetime('now', '+09:00'))
            """, (name, description, file_type))
            template_id = cursor.lastrowid
            conn.commit()
            return {"success": True, "message": f"✅ テンプレート「{name}」を作成しました", "template_id": template_id}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "❌ 同名のテンプレートが既に存在します"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_stocktake_templates(active_only: bool = True) -> list:
    """棚卸しテンプレート一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute("SELECT * FROM stocktake_templates WHERE is_active = 1 ORDER BY name")
            else:
                cursor.execute("SELECT * FROM stocktake_templates ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error in get_stocktake_templates: {e}")
        return []


def get_stocktake_template_by_id(template_id: int) -> dict:
    """棚卸しテンプレートを取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stocktake_templates WHERE id = ?", (template_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        return None


def update_stocktake_template(template_id: int, name: str = None,
                                description: str = None, is_active: int = None) -> dict:
    """棚卸しテンプレートを更新"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(is_active)
            updates.append("updated_at = datetime('now', '+09:00')")
            params.append(template_id)
            cursor.execute(f"UPDATE stocktake_templates SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return {"success": True, "message": "✅ テンプレートを更新しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def set_template_mappings(template_id: int, mappings: list) -> dict:
    """テンプレートマッピングを設定（既存を削除して再作成）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stocktake_template_mappings WHERE template_id = ?", (template_id,))
            for i, m in enumerate(mappings):
                cursor.execute("""
                    INSERT INTO stocktake_template_mappings
                    (template_id, field_name, excel_cell, display_label, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                """, (template_id, m["field_name"], m["excel_cell"],
                      m.get("display_label", ""), i))
            conn.commit()
            return {"success": True, "message": f"✅ {len(mappings)}件のマッピングを設定しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_template_mappings(template_id: int) -> list:
    """テンプレートマッピングを取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM stocktake_template_mappings
                WHERE template_id = ? ORDER BY sort_order
            """, (template_id,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return []


def delete_stocktake_session(session_id: int) -> dict:
    """棚卸しセッションと関連レコードを削除"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stocktake_records WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM stocktake_sessions WHERE id = ?", (session_id,))
            conn.commit()
            return {"success": True, "message": "✅ セッションを削除しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}

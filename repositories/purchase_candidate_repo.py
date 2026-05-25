"""
発注候補リポジトリ

自動発注候補の同期・選択・発注操作を集約。
"""

from repositories.base import get_db_connection
from utils.date_utils import get_jst_now_str

__all__ = [
    'get_reorder_candidates',
    'get_reorder_candidates_count',
    'sync_purchase_candidates',
    'sync_requests_to_candidates',
    'get_purchase_candidates',
    'update_candidate_selection',
    'update_candidate_deferred',
    'update_candidate_qty',
    'update_candidate_note',
    'mark_candidates_ordered',
    'get_selected_candidates_for_order',
    'get_candidate_counts',
]


def get_reorder_candidates(department_name: str = None) -> list:
    """発注候補を取得（消耗品、在庫<=発注点、直近30日内に出庫あり、推奨発注量>0）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            where_clauses = ["i.is_asset = 0", "inv.quantity <= inv.threshold"]
            params = []

            if department_name:
                where_clauses.append(
                    "( (',' || i.department_tags || ',') LIKE ? OR (',' || i.department_tags || ',') LIKE '%,全社,%' OR i.department_tags IS NULL OR TRIM(i.department_tags) = '' )"
                )
                params.append(f"%,{department_name},%")

            where_sql = " AND ".join(where_clauses)

            query = f"""
                SELECT
                    i.id as item_id,
                    i.item_name,
                    IFNULL(inv.quantity, 0) as current_stock,
                    IFNULL(inv.threshold, 0) as threshold,
                    IFNULL(r.total_out, 0) as recent_30_out,
                    (IFNULL(r.total_out, 0) * 2) - IFNULL(inv.quantity, 0) as recommended_qty,
                    IFNULL(i.unit_price, 0) as unit_price,
                    i.vendor_name as vendor_name
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                LEFT JOIN (
                    SELECT ih.item_id, SUM(ABS(ih.quantity)) as total_out
                    FROM inventory_history ih
                    WHERE ih.change_type = '出庫'
                      AND ih.created_at >= date('now', '-30 days')
                    GROUP BY ih.item_id
                ) r ON i.id = r.item_id
                WHERE {where_sql}
                  AND r.total_out IS NOT NULL
                  AND ((IFNULL(r.total_out, 0) * 2) - IFNULL(inv.quantity, 0)) > 0
                ORDER BY ((IFNULL(r.total_out, 0) * 2) - IFNULL(inv.quantity, 0)) DESC
            """

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_reorder_candidates: {e}")
        return []


def get_reorder_candidates_count(department_name: str = None) -> int:
    """発注候補の件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            where_clauses = ["i.is_asset = 0", "inv.quantity <= inv.threshold"]
            params = []

            if department_name:
                where_clauses.append(
                    "( (',' || i.department_tags || ',') LIKE ? OR (',' || i.department_tags || ',') LIKE '%,全社,%' OR i.department_tags IS NULL OR TRIM(i.department_tags) = '' )"
                )
                params.append(f"%,{department_name},%")

            where_sql = " AND ".join(where_clauses)

            query = f"""
                SELECT COUNT(DISTINCT i.id) as count
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                LEFT JOIN (
                    SELECT ih.item_id, SUM(ABS(ih.quantity)) as total_out
                    FROM inventory_history ih
                    WHERE ih.change_type = '出庫'
                      AND ih.created_at >= date('now', '-30 days')
                    GROUP BY ih.item_id
                ) r ON i.id = r.item_id
                WHERE {where_sql}
                  AND r.total_out IS NOT NULL
                  AND ((IFNULL(r.total_out, 0) * 2) - IFNULL(inv.quantity, 0)) > 0
            """

            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"Error in get_reorder_candidates_count: {e}")
        return 0


def sync_purchase_candidates(user_id: int = None) -> dict:
    """自動候補を purchase_candidates テーブルに同期（upsert）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT 
                    i.id as item_id,
                    IFNULL(inv.quantity, 0) as current_stock,
                    IFNULL(r.total_out, 0) as monthly_out,
                    ((IFNULL(r.total_out, 0) * 2) - IFNULL(inv.quantity, 0)) as recommended_qty
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                LEFT JOIN (
                    SELECT ih.item_id, SUM(ABS(ih.quantity)) as total_out
                    FROM inventory_history ih
                    WHERE ih.change_type = '出庫'
                      AND ih.created_at >= date('now', '-30 days')
                    GROUP BY ih.item_id
                ) r ON i.id = r.item_id
                WHERE i.is_asset = 0
                  AND i.is_active = 1
                  AND inv.quantity <= inv.threshold
                  AND r.total_out IS NOT NULL
                  AND ((IFNULL(r.total_out, 0) * 2) - IFNULL(inv.quantity, 0)) > 0
            """
            cursor.execute(query)
            candidates = cursor.fetchall()

            added = 0
            updated = 0

            for row in candidates:
                item_id = row["item_id"]
                recommended_qty = max(1, int(row["recommended_qty"]))
                current_stock = row["current_stock"]

                priority = "urgent" if current_stock == 0 else "normal"

                cursor.execute("""
                    SELECT id, status, selected_for_order, deferred 
                    FROM purchase_candidates 
                    WHERE item_id = ?
                """, (item_id,))
                existing = cursor.fetchone()

                if existing:
                    if existing["status"] == "OPEN":
                        now_jst = get_jst_now_str()
                        cursor.execute("""
                            UPDATE purchase_candidates 
                            SET recommended_qty = ?, 
                                priority = ?,
                                updated_at = ?,
                                updated_by_user_id = ?
                            WHERE id = ?
                        """, (recommended_qty, priority, now_jst, user_id, existing["id"]))
                        updated += 1
                else:
                    auto_selected = 1 if current_stock == 0 else 0
                    cursor.execute("""
                        INSERT INTO purchase_candidates 
                        (item_id, auto_reason, selected_for_order, deferred, priority, 
                         recommended_qty, status, updated_by_user_id)
                        VALUES (?, 'reorder_point', ?, 0, ?, ?, 'OPEN', ?)
                    """, (item_id, auto_selected, priority, recommended_qty, user_id))
                    added += 1

            conn.commit()
            return {
                "success": True,
                "added": added,
                "updated": updated,
                "message": f"同期完了: 新規{added}件, 更新{updated}件"
            }
    except Exception as e:
        print(f"Error in sync_purchase_candidates: {e}")
        return {"success": False, "added": 0, "updated": 0, "message": str(e)}


def sync_requests_to_candidates(user_id: int = None) -> dict:
    """発注申請（PENDING/APPROVED）を発注候補テーブルに同期"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    pr.item_id,
                    pr.requested_qty,
                    pr.priority,
                    pr.note,
                    pr.requested_by_user_id,
                    u.display_name as requester_name,
                    pr.requested_by_department,
                    pr.created_at as request_date,
                    i.item_name
                FROM purchase_requests pr
                LEFT JOIN users u ON pr.requested_by_user_id = u.id
                LEFT JOIN items i ON pr.item_id = i.id
                WHERE pr.status IN ('PENDING', 'APPROVED')
                  AND pr.id IN (
                      SELECT MAX(id) 
                      FROM purchase_requests 
                      WHERE status IN ('PENDING', 'APPROVED')
                      GROUP BY item_id
                  )
            """)
            requests = cursor.fetchall()

            print(f"[DEBUG] sync_requests_to_candidates: {len(requests)}件の申請を取得")
            for req in requests:
                print(f"  - item_id={req['item_id']}, item_name={req.get('item_name', 'N/A')}, qty={req['requested_qty']}, status=PENDING/APPROVED")

            added = 0
            updated = 0

            for row in requests:
                item_id = row["item_id"]
                requested_qty = row["requested_qty"]
                priority = row["priority"]
                request_note = row["note"] or ""
                requester_name = row["requester_name"] or "不明"
                department = row["requested_by_department"] or "未設定"

                combined_note = f"【申請者】{requester_name}（{department}）\n【申請理由】{request_note}" if request_note else f"【申請者】{requester_name}（{department}）"

                cursor.execute("""
                    SELECT id, status, recommended_qty
                    FROM purchase_candidates
                    WHERE item_id = ?
                """, (item_id,))
                existing = cursor.fetchone()

                if existing:
                    if existing["status"] == "OPEN":
                        new_qty = max(existing["recommended_qty"], requested_qty)
                        cursor.execute("""
                            UPDATE purchase_candidates
                            SET recommended_qty = ?,
                                priority = ?,
                                note = ?,
                                auto_reason = 'from_request',
                                selected_for_order = 1,
                                updated_at = CURRENT_TIMESTAMP,
                                updated_by_user_id = ?
                            WHERE id = ?
                        """, (new_qty, priority, combined_note, user_id, existing["id"]))
                        updated += 1
                else:
                    cursor.execute("""
                        INSERT INTO purchase_candidates
                        (item_id, auto_reason, selected_for_order, deferred, priority,
                         recommended_qty, note, status, updated_by_user_id)
                        VALUES (?, 'from_request', 1, 0, ?, ?, ?, 'OPEN', ?)
                    """, (item_id, priority, requested_qty, combined_note, user_id))
                    added += 1

            conn.commit()
            return {
                "success": True,
                "added": added,
                "updated": updated,
                "message": f"申請同期完了: 新規{added}件, 更新{updated}件"
            }
    except Exception as e:
        print(f"Error in sync_requests_to_candidates: {e}")
        return {"success": False, "added": 0, "updated": 0, "message": str(e)}


def get_purchase_candidates(status: str = "OPEN", department_name: str = None) -> list:
    """発注候補一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            where_clauses = []
            params = []

            if status:
                where_clauses.append("pc.status = ?")
                params.append(status)

            if department_name:
                where_clauses.append(
                    "( (',' || i.department_tags || ',') LIKE ? OR (',' || i.department_tags || ',') LIKE '%,全社,%' OR i.department_tags IS NULL OR TRIM(i.department_tags) = '' )"
                )
                params.append(f"%,{department_name},%")

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            query = f"""
                SELECT 
                    pc.id,
                    pc.item_id,
                    i.item_name,
                    i.item_code,
                    i.vendor_name,
                    i.unit_price,
                    i.category,
                    IFNULL(inv.quantity, 0) as current_stock,
                    IFNULL(inv.threshold, 0) as threshold,
                    pc.auto_reason,
                    pc.selected_for_order,
                    pc.deferred,
                    pc.priority,
                    pc.recommended_qty,
                    pc.note,
                    pc.status,
                    pc.updated_by_user_id,
                    pc.updated_at,
                    pc.created_at
                FROM purchase_candidates pc
                JOIN items i ON pc.item_id = i.id
                LEFT JOIN inventory inv ON i.id = inv.item_id
                {where_sql}
                ORDER BY 
                    CASE pc.priority WHEN 'urgent' THEN 0 ELSE 1 END,
                    pc.selected_for_order DESC,
                    pc.deferred ASC,
                    i.item_name
            """

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_purchase_candidates: {e}")
        return []


def update_candidate_selection(candidate_id: int, selected: bool, user_id: int) -> dict:
    """候補の選択状態を更新"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if selected:
                cursor.execute("""
                    UPDATE purchase_candidates 
                    SET selected_for_order = 1, 
                        deferred = 0,
                        updated_by_user_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'OPEN'
                """, (user_id, candidate_id))
            else:
                cursor.execute("""
                    UPDATE purchase_candidates 
                    SET selected_for_order = 0,
                        updated_by_user_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'OPEN'
                """, (user_id, candidate_id))

            conn.commit()
            return {"success": True, "message": "選択状態を更新しました"}
    except Exception as e:
        print(f"Error in update_candidate_selection: {e}")
        return {"success": False, "message": str(e)}


def update_candidate_deferred(candidate_id: int, deferred: bool, user_id: int) -> dict:
    """候補の保留状態を更新"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if deferred:
                cursor.execute("""
                    UPDATE purchase_candidates 
                    SET deferred = 1, 
                        selected_for_order = 0,
                        updated_by_user_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'OPEN'
                """, (user_id, candidate_id))
            else:
                cursor.execute("""
                    UPDATE purchase_candidates 
                    SET deferred = 0,
                        updated_by_user_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'OPEN'
                """, (user_id, candidate_id))

            conn.commit()
            return {"success": True, "message": "保留状態を更新しました"}
    except Exception as e:
        print(f"Error in update_candidate_deferred: {e}")
        return {"success": False, "message": str(e)}


def update_candidate_qty(candidate_id: int, qty: int, user_id: int) -> dict:
    """候補の発注数量を更新（ADMIN専用）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE purchase_candidates 
                SET recommended_qty = ?,
                    updated_by_user_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'OPEN'
            """, (qty, user_id, candidate_id))

            conn.commit()
            return {"success": True, "message": "数量を更新しました"}
    except Exception as e:
        print(f"Error in update_candidate_qty: {e}")
        return {"success": False, "message": str(e)}


def update_candidate_note(candidate_id: int, note: str, user_id: int) -> dict:
    """候補のメモを更新"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE purchase_candidates 
                SET note = ?,
                    updated_by_user_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'OPEN'
            """, (note, user_id, candidate_id))

            conn.commit()
            return {"success": True, "message": "メモを更新しました"}
    except Exception as e:
        print(f"Error in update_candidate_note: {e}")
        return {"success": False, "message": str(e)}


def mark_candidates_ordered(candidate_ids: list, user_id: int) -> dict:
    """選択された候補を発注済み(ORDERED)に更新"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if not candidate_ids:
                return {"success": False, "count": 0, "message": "対象がありません"}

            placeholders = ",".join(["?" for _ in candidate_ids])
            cursor.execute(f"""
                SELECT id, item_id, auto_reason
                FROM purchase_candidates
                WHERE id IN ({placeholders}) AND status = 'OPEN' AND selected_for_order = 1
            """, candidate_ids)
            candidates = cursor.fetchall()

            if not candidates:
                return {"success": False, "count": 0, "message": "対象がありません"}

            cursor.execute(f"""
                UPDATE purchase_candidates 
                SET status = 'ORDERED',
                    updated_by_user_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders}) AND status = 'OPEN' AND selected_for_order = 1
            """, [user_id] + candidate_ids)

            count = cursor.rowcount

            request_updated = 0
            for candidate in candidates:
                if candidate['auto_reason'] == 'from_request':
                    item_id = candidate['item_id']
                    now_jst = get_jst_now_str()
                    cursor.execute("""
                        UPDATE purchase_requests
                        SET status = 'ORDERED',
                            approved_by = ?,
                            approved_at = ?,
                            updated_at = ?
                        WHERE item_id = ? AND status IN ('PENDING', 'APPROVED')
                    """, (user_id, now_jst, now_jst, item_id))
                    request_updated += cursor.rowcount

            conn.commit()

            message = f"{count}件を発注済みにしました"
            if request_updated > 0:
                message += f"（申請{request_updated}件も発注済みに更新）"

            return {"success": True, "count": count, "message": message}
    except Exception as e:
        print(f"Error in mark_candidates_ordered: {e}")
        return {"success": False, "count": 0, "message": str(e)}


def get_selected_candidates_for_order() -> list:
    """発注対象（selected_for_order=1, status=OPEN）の候補を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT 
                    pc.id,
                    pc.item_id,
                    i.item_name,
                    i.item_code,
                    i.vendor_name,
                    i.unit_price,
                    pc.recommended_qty,
                    pc.priority
                FROM purchase_candidates pc
                JOIN items i ON pc.item_id = i.id
                WHERE pc.status = 'OPEN' AND pc.selected_for_order = 1
                ORDER BY i.vendor_name, i.item_name
            """

            cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_selected_candidates_for_order: {e}")
        return []


def get_candidate_counts() -> dict:
    """候補のステータス別件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'OPEN') as open_count,
                    COUNT(*) FILTER (WHERE status = 'OPEN' AND selected_for_order = 1) as selected_count,
                    COUNT(*) FILTER (WHERE status = 'OPEN' AND deferred = 1) as deferred_count,
                    COUNT(*) FILTER (WHERE status = 'ORDERED') as ordered_count
                FROM purchase_candidates
            """)
            row = cursor.fetchone()

            if row:
                return {
                    "open": row["open_count"] or 0,
                    "selected": row["selected_count"] or 0,
                    "deferred": row["deferred_count"] or 0,
                    "ordered": row["ordered_count"] or 0
                }
            return {"open": 0, "selected": 0, "deferred": 0, "ordered": 0}
    except Exception:
        # SQLite doesn't support FILTER, use CASE WHEN instead
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_count,
                        SUM(CASE WHEN status = 'OPEN' AND selected_for_order = 1 THEN 1 ELSE 0 END) as selected_count,
                        SUM(CASE WHEN status = 'OPEN' AND deferred = 1 THEN 1 ELSE 0 END) as deferred_count,
                        SUM(CASE WHEN status = 'ORDERED' THEN 1 ELSE 0 END) as ordered_count
                    FROM purchase_candidates
                """)
                row = cursor.fetchone()

                if row:
                    return {
                        "open": row["open_count"] or 0,
                        "selected": row["selected_count"] or 0,
                        "deferred": row["deferred_count"] or 0,
                        "ordered": row["ordered_count"] or 0
                    }
                return {"open": 0, "selected": 0, "deferred": 0, "ordered": 0}
        except Exception as e2:
            print(f"Error in get_candidate_counts: {e2}")
            return {"open": 0, "selected": 0, "deferred": 0, "ordered": 0}

"""
デモデータリポジトリ

デモデータの投入・リセット・件数取得を集約。
"""

import random
from datetime import datetime, timedelta

import bcrypt

from repositories.base import get_db_connection
from utils.date_utils import JST, get_jst_now_str

__all__ = [
    'insert_demo_data',
    'reset_demo_data',
    'get_demo_data_counts',
]


def insert_demo_data() -> dict:
    """デモ用のサンプルデータを一括投入（UPSERT方式）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            counts = {
                "departments": 0, "users": 0, "vendors": 0,
                "categories": 0, "items": 0, "inventory": 0,
                "history": 0, "approvals": 0
            }

            # 1. 部署（5件）
            print("📂 部署を投入中...")
            departments = ["総務部", "営業部", "開発部", "経理部", "人事部"]
            try:
                for dept_name in departments:
                    cursor.execute(
                        "INSERT OR IGNORE INTO departments (name, is_active) VALUES (?, 1)",
                        (dept_name,)
                    )
                    if cursor.rowcount > 0:
                        counts["departments"] += 1
                        print(f"  ✓ {dept_name} を追加")
            except Exception as e:
                print(f"❌ 部署投入エラー: {e}")
                raise

            cursor.execute(
                "SELECT id, name FROM departments WHERE name IN (?, ?, ?, ?, ?)",
                tuple(departments)
            )
            dept_map = {row["name"]: row["id"] for row in cursor.fetchall()}

            cursor.execute("SELECT id, name FROM departments")
            dept_id_to_name = {row["id"]: row["name"] for row in cursor.fetchall()}

            # 2. ユーザー（7名）
            print("👥 ユーザーを投入中...")
            users_data = [
                ("admin", "admin123", "管理者", "総務部", "ADMIN"),
                ("tanaka", "pass123", "田中太郎", "営業部", "USER"),
                ("suzuki", "pass123", "鈴木花子", "開発部", "USER"),
                ("yamada", "pass123", "山田次郎", "経理部", "USER"),
                ("sato", "pass123", "佐藤美咲", "人事部", "USER"),
                ("guest1", "guest123", "ゲスト1", "総務部", "GUEST"),
                ("guest2", "guest123", "ゲスト2", "営業部", "GUEST"),
            ]

            try:
                for username, password, display_name, dept_name, role in users_data:
                    dept_id = dept_map.get(dept_name, 1)
                    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
                    existing = cursor.fetchone()
                    if not existing:
                        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                        cursor.execute("""
                            INSERT INTO users 
                            (username, password_hash, display_name, department, department_id, user_role, is_active)
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                        """, (username, hashed_pw, display_name, dept_name, dept_id, role))
                        counts["users"] += 1
                        print(f"  ✓ {username} ({display_name} / {dept_name}) を追加")
                    else:
                        print(f"  - {username} は既存のためスキップ")
            except Exception as e:
                print(f"❌ ユーザー投入エラー: {e}")
                raise

            # 3. 業者（5社）
            print("🏢 業者を投入中...")
            vendors_data = [
                ("V001", "株式会社文具センター", "東京都千代田区1-2-3", "03-1234-5678", "info@bungu.co.jp"),
                ("V002", "電子部品商事", "神奈川県横浜市2-3-4", "045-2345-6789", "sales@denshi.co.jp"),
                ("V003", "オフィス家具プロ", "大阪府大阪市3-4-5", "06-3456-7890", "order@kagu.co.jp"),
                ("V004", "山田工業用品", "愛知県名古屋市4-5-6", "052-4567-8901", "contact@yamada-ind.co.jp"),
                ("V005", "佐藤商店", "福岡県福岡市5-6-7", "092-5678-9012", "info@sato-shop.co.jp"),
            ]

            try:
                for code, name, addr, phone, email in vendors_data:
                    cursor.execute(
                        "INSERT OR IGNORE INTO vendors (vendor_code, vendor_name, address, phone, email, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                        (code, name, addr, phone, email)
                    )
                    if cursor.rowcount > 0:
                        counts["vendors"] += 1
                        print(f"  ✓ {code} ({name}) を追加")
            except Exception as e:
                print(f"❌ 業者投入エラー: {e}")
                raise

            cursor.execute("SELECT id, vendor_code FROM vendors")
            vendor_map = {row["vendor_code"]: row["id"] for row in cursor.fetchall()}

            # 4. カテゴリ（6種類）
            print("🏷️ カテゴリを投入中...")
            categories = ["文房具", "電子機器", "家具", "消耗品", "工具", "薬品"]
            try:
                for cat_name in categories:
                    cursor.execute(
                        "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                        (cat_name,)
                    )
                    if cursor.rowcount > 0:
                        counts["categories"] += 1
                        print(f"  ✓ {cat_name} を追加")
            except Exception as e:
                print(f"❌ カテゴリ投入エラー: {e}")
                raise

            cursor.execute("SELECT id, name FROM categories")
            cat_map = {row["name"]: row["id"] for row in cursor.fetchall()}

            # 5. 物品（24件）
            print("📦 物品を投入中...")
            today = datetime.now(JST)

            items_data = [
                ("P001", "ボールペン（黒）", "文房具", "株式会社文具センター", 50, None, "全社"),
                ("P002", "A4コピー用紙", "文房具", "株式会社文具センター", 100, None, "全社"),
                ("P003", "クリアファイル", "文房具", "株式会社文具センター", 30, None, "全社"),
                ("P004", "付箋セット", "文房具", "株式会社文具センター", 20, None, "全社"),
                ("E001", "USBメモリ 32GB", "電子機器", "電子部品商事", 10, None, "営業部,開発部"),
                ("E002", "HDMIケーブル 2m", "電子機器", "電子部品商事", None, None, "全社"),
                ("E003", "マウス（無線）", "電子機器", "電子部品商事", 15, None, "全社"),
                ("E004", "キーボード", "電子機器", "電子部品商事", None, None, "開発部"),
                ("F001", "オフィスチェア", "家具", "オフィス家具プロ", None, None, "総務部"),
                ("F002", "デスク", "家具", "オフィス家具プロ", None, None, "総務部"),
                ("F003", "書棚", "家具", "オフィス家具プロ", None, None, "総務部"),
                ("F004", "ホワイトボード", "家具", "オフィス家具プロ", None, None, "全社"),
                ("C001", "トイレットペーパー", "消耗品", "佐藤商店", 200, None, "全社"),
                ("C002", "ティッシュペーパー", "消耗品", "佐藤商店", 150, None, "全社"),
                ("C003", "ゴミ袋（大）", "消耗品", "佐藤商店", 100, None, "全社"),
                ("C004", "洗剤", "消耗品", "佐藤商店", 50, None, "全社"),
                ("T001", "ドライバーセット", "工具", "山田工業用品", 5, None, "開発部"),
                ("T002", "六角レンチセット", "工具", "山田工業用品", 5, None, "開発部"),
                ("T003", "メジャー 5m", "工具", "山田工業用品", 10, None, "営業部"),
                ("T004", "カッターナイフ", "工具", "山田工業用品", 20, None, "全社"),
                ("M001", "造影剤 イオメロン300", "薬品", "株式会社文具センター", 10,
                 (today - timedelta(days=5)).strftime("%Y-%m-%d"), "人事部"),
                ("M002", "消毒用エタノール 500ml", "薬品", "株式会社文具センター", 20,
                 (today + timedelta(days=7)).strftime("%Y-%m-%d"), "人事部"),
                ("M003", "滅菌ガーゼ 5x5cm", "薬品", "株式会社文具センター", 30,
                 (today + timedelta(days=15)).strftime("%Y-%m-%d"), "人事部"),
                ("M004", "注射器 5ml（使い捨て）", "薬品", "株式会社文具センター", 50,
                 (today + timedelta(days=25)).strftime("%Y-%m-%d"), "人事部"),
            ]

            try:
                for code, name, category, vendor_name, reorder_pt, expiry, dept_tags in items_data:
                    cursor.execute("SELECT id FROM items WHERE item_code = ?", (code,))
                    if cursor.fetchone():
                        print(f"  - {code} は既存のためスキップ")
                        continue
                    cursor.execute("""
                        INSERT INTO items 
                        (item_code, item_name, category, vendor_name, reorder_point, expiry_date, department_tags, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (code, name, category, vendor_name, reorder_pt, expiry, dept_tags))
                    counts["items"] += 1
                    print(f"  ✓ {code} ({name}) - 部署タグ: {dept_tags} を追加")
            except Exception as e:
                print(f"❌ 物品投入エラー: {e}")
                raise

            cursor.execute("SELECT id, item_code FROM items")
            item_map = {row["item_code"]: row["id"] for row in cursor.fetchall()}

            # 6. 在庫
            print("📊 在庫を投入中...")
            try:
                low_stock_codes = ["P001", "P003", "E001", "C001", "T001", "M001"]
                for item_code, item_id in item_map.items():
                    cursor.execute("SELECT id FROM inventory WHERE item_id = ?", (item_id,))
                    if cursor.fetchone():
                        continue
                    cursor.execute("SELECT reorder_point FROM items WHERE id = ?", (item_id,))
                    result = cursor.fetchone()
                    reorder_pt = result["reorder_point"] if result and result["reorder_point"] else None

                    if item_code in low_stock_codes and reorder_pt:
                        qty = random.randint(1, max(1, reorder_pt - 5))
                    elif reorder_pt:
                        qty = random.randint(reorder_pt + 10, reorder_pt + 50)
                    else:
                        qty = random.randint(10, 50)

                    cursor.execute(
                        "INSERT INTO inventory (item_id, quantity, location) VALUES (?, ?, ?)",
                        (item_id, qty, "倉庫A")
                    )
                    counts["inventory"] += 1
            except Exception as e:
                print(f"❌ 在庫投入エラー: {e}")
                raise

            # 7. 在庫履歴
            print("📝 履歴を投入中...")
            try:
                cursor.execute("SELECT username FROM users LIMIT 1")
                demo_user = cursor.fetchone()
                demo_username = demo_user["username"] if demo_user else "admin"

                for item_code, item_id in list(item_map.items())[:10]:
                    for i in range(2):
                        change_type = "入庫" if i == 0 else "出庫"
                        qty = 10 if change_type == "入庫" else -5
                        cursor.execute("""
                            INSERT INTO inventory_history 
                            (item_id, change_type, quantity, user_name, note, created_at)
                            VALUES (?, ?, ?, ?, ?, datetime('now', '+09:00', ?))
                        """, (item_id, change_type, qty, demo_username,
                              f"デモデータ - {change_type}", f"-{i} days"))
                        counts["history"] += 1
            except Exception as e:
                print(f"❌ 履歴投入エラー: {e}")
                raise

            # 8. 承認待ち（スキップ）
            print("✋ 承認待ちをスキップ（テーブルが存在しない可能性）")

            # 9. 棚卸し対象フラグ
            print("🏷️ 棚卸し対象フラグを設定中...")
            try:
                non_target_codes = [
                    "P001", "P002", "P003", "P004",
                    "C001", "C002", "C003", "C004"
                ]
                for code in non_target_codes:
                    cursor.execute(
                        "UPDATE items SET is_inventory_target = 0 WHERE item_code = ?",
                        (code,)
                    )
                print(f"  ✓ {len(non_target_codes)}件を棚卸し非対象に設定")
            except Exception as e:
                print(f"❌ 棚卸し対象フラグ設定エラー: {e}")
                raise

            # 10. 棚卸しデモデータ
            print("📋 棚卸しデモデータを投入中...")
            counts["stocktake_sessions"] = 0
            counts["stocktake_records"] = 0
            try:
                cursor.execute(
                    "SELECT id FROM stocktake_sessions WHERE name = ?",
                    ("2026年3月定期棚卸し",)
                )
                existing_session = cursor.fetchone()

                if not existing_session:
                    now_str = get_jst_now_str()
                    cursor.execute("""
                        INSERT INTO stocktake_sessions
                        (name, start_date, end_date, status, note, created_by, created_at)
                        VALUES (?, ?, ?, 'OPEN', ?, ?, ?)
                    """, (
                        "2026年3月定期棚卸し",
                        "2026-03-01", "2026-03-15",
                        "デモ用棚卸しセッション。医薬品・電子機器・家具・工具が対象です。",
                        1, now_str,
                    ))
                    session_id = cursor.lastrowid
                    counts["stocktake_sessions"] = 1
                    print(f"  ✓ 棚卸しセッション作成 (ID={session_id})")

                    cursor.execute("""
                        INSERT OR IGNORE INTO stocktake_records
                        (session_id, item_id, system_qty, status)
                        SELECT ?, i.id, COALESCE(inv.quantity, 0), 'PENDING'
                        FROM items i
                        LEFT JOIN inventory inv ON i.id = inv.item_id
                        WHERE i.is_active = 1
                          AND COALESCE(i.is_inventory_target, 1) = 1
                    """, (session_id,))
                    record_count_val = cursor.rowcount
                    counts["stocktake_records"] = record_count_val
                    print(f"  ✓ {record_count_val}件の棚卸しレコードを生成")

                    cursor.execute("SELECT id FROM users WHERE username = 'admin' LIMIT 1")
                    admin_row = cursor.fetchone()
                    admin_id = admin_row["id"] if admin_row else 1

                    cursor.execute("SELECT id FROM users WHERE username = 'tanaka' LIMIT 1")
                    tanaka_row = cursor.fetchone()
                    tanaka_id = tanaka_row["id"] if tanaka_row else 2

                    cursor.execute("SELECT id FROM users WHERE username = 'suzuki' LIMIT 1")
                    suzuki_row = cursor.fetchone()
                    suzuki_id = suzuki_row["id"] if suzuki_row else 3

                    cursor.execute("""
                        SELECT sr.id, sr.item_id, sr.system_qty, i.item_code, i.category
                        FROM stocktake_records sr
                        JOIN items i ON sr.item_id = i.id
                        WHERE sr.session_id = ?
                        ORDER BY i.item_code
                    """, (session_id,))
                    st_records = [dict(row) for row in cursor.fetchall()]

                    for rec in st_records:
                        code = rec["item_code"]
                        sys_qty = rec["system_qty"]
                        rec_id = rec["id"]

                        if code == "M001":
                            actual = max(0, sys_qty - 2)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?, note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  "使用済み分が未記録の可能性", rec_id))

                        elif code == "M002":
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'VERIFIED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?
                                WHERE id = ?
                            """, (sys_qty, suzuki_id, now_str,
                                  admin_id, now_str, rec_id))

                        elif code == "M003":
                            actual = sys_qty + 3
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'APPROVED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?,
                                    approved_by = ?, approved_at = ?, note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  admin_id, now_str, admin_id, now_str,
                                  "納品時の数量誤り", rec_id))

                        elif code == "M004":
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?
                                WHERE id = ?
                            """, (sys_qty, suzuki_id, now_str, rec_id))

                        elif code == "E001":
                            actual = max(0, sys_qty - 1)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?, note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  "紛失の可能性あり", rec_id))

                        elif code == "E002":
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'VERIFIED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?
                                WHERE id = ?
                            """, (sys_qty, tanaka_id, now_str,
                                  admin_id, now_str, rec_id))

                        elif code == "F001":
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'APPROVED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?,
                                    approved_by = ?, approved_at = ?
                                WHERE id = ?
                            """, (sys_qty, suzuki_id, now_str,
                                  admin_id, now_str, admin_id, now_str, rec_id))

                        elif code == "F002":
                            actual = sys_qty + 1
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'VERIFIED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?, note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, suzuki_id, now_str,
                                  admin_id, now_str, "未登録のデスクが1台あり", rec_id))

                        elif code == "F003":
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?
                                WHERE id = ?
                            """, (sys_qty, suzuki_id, now_str, rec_id))

                        elif code == "F004":
                            actual = max(0, sys_qty - 1)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?, note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  "会議室Bから移動済み？要確認", rec_id))

                        elif code == "T003":
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?
                                WHERE id = ?
                            """, (sys_qty, tanaka_id, now_str, rec_id))

                        elif code == "T004":
                            actual = max(0, sys_qty - 5)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?, note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, suzuki_id, now_str,
                                  "各部署への貸出分が戻っていない", rec_id))

                    print("  ✓ 棚卸しレコードにデモステータスを設定")
                else:
                    print("  - 棚卸しセッション「2026年3月定期棚卸し」は既存のためスキップ")
            except Exception as e:
                print(f"❌ 棚卸しデモデータ投入エラー: {e}")
                raise

            conn.commit()
            print("✅ デモデータ投入完了！")
            return {
                "success": True,
                "message": "✅ デモデータを投入しました",
                "counts": counts
            }

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}", "counts": {}}


def reset_demo_data(keep_users_and_depts: bool = False) -> dict:
    """デモデータをリセット"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            counts = {
                "stocktake_records": 0, "stocktake_sessions": 0,
                "approvals": 0, "history": 0, "inventory": 0,
                "items": 0, "categories": 0, "vendors": 0,
                "users": 0, "departments": 0
            }

            try:
                cursor.execute("DELETE FROM stocktake_records")
                counts["stocktake_records"] = cursor.rowcount
                cursor.execute("DELETE FROM stocktake_sessions")
                counts["stocktake_sessions"] = cursor.rowcount
            except Exception:
                counts["stocktake_records"] = 0
                counts["stocktake_sessions"] = 0

            try:
                cursor.execute("DELETE FROM approval_queue")
                counts["approvals"] = cursor.rowcount
            except Exception:
                counts["approvals"] = 0

            cursor.execute("DELETE FROM inventory_history")
            counts["history"] = cursor.rowcount
            cursor.execute("DELETE FROM inventory")
            counts["inventory"] = cursor.rowcount
            cursor.execute("DELETE FROM items")
            counts["items"] = cursor.rowcount
            cursor.execute("DELETE FROM categories")
            counts["categories"] = cursor.rowcount
            cursor.execute("DELETE FROM vendors")
            counts["vendors"] = cursor.rowcount

            if not keep_users_and_depts:
                cursor.execute("DELETE FROM users")
                counts["users"] = cursor.rowcount
                cursor.execute("DELETE FROM departments")
                counts["departments"] = cursor.rowcount

            conn.commit()
            keep_msg = "（ユーザー・部署は保持）" if keep_users_and_depts else ""
            return {
                "success": True,
                "message": f"✅ デモデータをリセットしました{keep_msg}",
                "counts": counts
            }

    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}", "counts": {}}


def get_demo_data_counts() -> dict:
    """現在のデータ件数を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            counts = {}
            tables = [
                "departments", "users", "vendors", "categories",
                "items", "inventory", "inventory_history",
                "stocktake_sessions", "stocktake_records"
            ]
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                    result = cursor.fetchone()
                    counts[table] = result["count"] if result else 0
                except Exception:
                    counts[table] = 0
            return counts
    except Exception as e:
        print(f"❌ 件数取得エラー: {e}")
        return {}

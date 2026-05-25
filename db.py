"""
データベース接続・初期化モジュール
SQLite を使用した在庫管理システムのDB層
"""

import sqlite3
import os
import hashlib
import secrets
import bcrypt
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
from collections import Counter
from utils.date_utils import JST, get_jst_now_str  # noqa: F401 (再エクスポート用)

# =============================================================================
# パスワードハッシュ関連
# =============================================================================

def hash_password(password: str, salt: str = None) -> tuple:
    """
    パスワードをハッシュ化（SHA-256 + salt）
    Returns: (hash, salt)
    """
    if salt is None:
        salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${password_hash}", salt


def verify_password(password: str, stored_hash: str) -> bool:
    """
    パスワードを検証
    stored_hash形式: "salt$hash"
    """
    try:
        # stored_hash が bytes (bcrypt.hashpw の結果) の場合
        if isinstance(stored_hash, (bytes, bytearray)):
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)

        # stored_hash が文字列として保存されているが bcrypt 形式の場合
        # bcrypt のハッシュは "$2a$" や "$2b$" などで始まる
        if isinstance(stored_hash, str) and stored_hash.startswith("$2"):
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))

        # それ以外は既存の salt$sha256 形式を想定
        salt, hash_value = stored_hash.split("$")
        new_hash, _ = hash_password(password, salt)
        return new_hash == stored_hash
    except (ValueError, AttributeError, TypeError):
        return False


def get_db_path() -> str:
    """環境変数からDBパスを取得"""
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("DB_PATH", "inventory.db")


@contextmanager
def get_db_connection():
    """
    DBコネクションを取得するコンテキストマネージャー
    使用例:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items")
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能にする
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_tables():
    """
    テーブルを初期化（存在しない場合のみ作成）
    数千件対応のため、検索用インデックスを設定
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 物品マスターテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                item_code TEXT,
                vendor_name TEXT,
                vendor_item_code TEXT,
                category TEXT NOT NULL,
                department_tags TEXT,  -- カンマ区切りで複数部署対応
                unit_price REAL DEFAULT 0,
                is_asset INTEGER DEFAULT 0,  -- 0: 消耗品, 1: 資産（5万円以上）
                frequency_tag TEXT,  -- 使用頻度タグ（高頻度など）
                expiry_date TEXT,  -- 期限（薬品など、YYYY-MM-DD形式）
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(vendor_name, vendor_item_code)  -- 業者名+業者品番でユニーク化
            )
        """)
        
        # 在庫テーブル（各物品の現在在庫数）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 0,
                threshold INTEGER DEFAULT 10,  -- 在庫閾値（アラート用）
                location TEXT,  -- 保管場所
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                UNIQUE(item_id)
            )
        """)
        
        # 在庫履歴テーブル（入出庫記録 + 発注記録）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                change_type TEXT NOT NULL,  -- 'IN' or 'OUT' or 'DISPOSE' or 'ORDER'
                quantity INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                department TEXT,
                status TEXT DEFAULT 'CONFIRMED',  -- 'PENDING', 'CONFIRMED', 'REJECTED'
                note TEXT,
                vendor_name TEXT,  -- 発注先業者名（ORDER時）
                unit_price REAL,  -- 単価（ORDER時）
                total_price REAL,  -- 合計金額（ORDER時）
                created_by INTEGER,  -- 作成者ユーザーID（ORDER時）
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)
        
        # 既存テーブルにカラムを追加（マイグレーション）
        try:
            cursor.execute("ALTER TABLE inventory_history ADD COLUMN vendor_name TEXT")
        except:
            pass  # カラムが既に存在する場合はスキップ
        
        try:
            cursor.execute("ALTER TABLE inventory_history ADD COLUMN unit_price REAL")
        except:
            pass
        
        try:
            cursor.execute("ALTER TABLE inventory_history ADD COLUMN total_price REAL")
        except:
            pass
        
        try:
            cursor.execute("ALTER TABLE inventory_history ADD COLUMN created_by INTEGER")
        except:
            pass
        
        # 検索高速化のためのインデックス（数千件対応）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_name 
            ON items(item_name)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_code 
            ON items(item_code)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_category 
            ON items(category)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_vendor 
            ON items(vendor_name, vendor_item_code)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_item 
            ON inventory_history(item_id, created_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_status 
            ON inventory_history(status)
        """)
        
        # =================================================================
        # 部署マスターテーブル（Step1: 部署マスタ導入）
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_departments_name 
            ON departments(name)
        """)
        
        # デフォルト部署を作成（存在しない場合のみ）
        cursor.execute("SELECT COUNT(*) as count FROM departments")
        if cursor.fetchone()["count"] == 0:
            default_depts = ['総務部', '営業部', '経理部', '看護係', '薬剤部', '未設定']
            for dept in default_depts:
                cursor.execute("INSERT INTO departments (name) VALUES (?)", (dept,))
            print("✅ デフォルト部署を作成しました")
        
        # =================================================================
        # カテゴリマスターテーブル
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_categories_name 
            ON categories(name)
        """)
        
        # デフォルトカテゴリを作成（存在しない場合のみ）
        cursor.execute("SELECT COUNT(*) as count FROM categories")
        if cursor.fetchone()["count"] == 0:
            default_categories = ['事務用品', '薬品', '医療機器', '消耗品', 'その他']
            for cat in default_categories:
                cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
            print("✅ デフォルトカテゴリを作成しました")
        
        # =================================================================
        # 業者マスターテーブル（発注書自動作成を見据えた設計）
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_code TEXT UNIQUE NOT NULL,
                vendor_name TEXT UNIQUE NOT NULL,
                address TEXT,
                phone TEXT,
                email TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vendors_name 
            ON vendors(vendor_name)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vendors_code 
            ON vendors(vendor_code)
        """)
        
        # デフォルト業者を作成（存在しない場合のみ）
        cursor.execute("SELECT COUNT(*) as count FROM vendors")
        if cursor.fetchone()["count"] == 0:
            default_vendors = [
                ('V001', '○○商事', '東京都千代田区1-2-3', '03-1234-5678', 'info@example.co.jp'),
                ('V002', '△△物産', '大阪府大阪市2-3-4', '06-9876-5432', 'sales@example.com'),
                ('V003', '未登録業者', '', '', '')
            ]
            for vendor in default_vendors:
                cursor.execute("""
                    INSERT INTO vendors (vendor_code, vendor_name, address, phone, email) 
                    VALUES (?, ?, ?, ?, ?)
                """, vendor)
            print("✅ デフォルト業者を作成しました")
        
        # ユーザーマスターテーブル（SPEC.md 16.1準拠）
        # department_id を追加（外部キー）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                department TEXT,
                department_id INTEGER,
                user_role TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )
        """)
        
        # usersテーブル用インデックス
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username 
            ON users(username)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_role 
            ON users(user_role)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_department 
            ON users(department)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_department_id 
            ON users(department_id)
        """)
        
        # =================================================================
        # 申請テーブル（Step2: ゲスト申請テーブル）
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                actor_name TEXT NOT NULL,
                note TEXT,
                guest_user_id INTEGER NOT NULL,
                department_id INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                approved_by INTEGER,
                approved_at TEXT,
                reject_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (guest_user_id) REFERENCES users(id),
                FOREIGN KEY (department_id) REFERENCES departments(id),
                FOREIGN KEY (approved_by) REFERENCES users(id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_status 
            ON pending_transactions(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_department 
            ON pending_transactions(department_id)
        """)
        
        # =================================================================
        # 廃棄申請テーブル（Step3: 薬品廃棄管理）
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS disposal_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                reason TEXT NOT NULL,
                requester_id INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                approved_by INTEGER,
                approved_at TEXT,
                reject_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (requester_id) REFERENCES users(id),
                FOREIGN KEY (approved_by) REFERENCES users(id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_disposal_status 
            ON disposal_requests(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_disposal_requester 
            ON disposal_requests(requester_id)
        """)
        
        # =================================================================
        # 発注申請テーブル（USER→ADMIN承認フロー）
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                requested_qty INTEGER NOT NULL,
                priority TEXT DEFAULT 'normal',
                due_date TEXT,
                note TEXT,
                requested_by_user_id INTEGER NOT NULL,
                requested_by_department TEXT,
                status TEXT DEFAULT 'PENDING',
                admin_comment TEXT,
                approved_by INTEGER,
                approved_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
                FOREIGN KEY (approved_by) REFERENCES users(id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_requests_status 
            ON purchase_requests(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_requests_requester 
            ON purchase_requests(requested_by_user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_requests_item 
            ON purchase_requests(item_id)
        """)
        
        # デフォルト管理者ユーザーを作成（存在しない場合のみ）
        cursor.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()["count"] == 0:
            # 総務部のIDを取得
            cursor.execute("SELECT id FROM departments WHERE name = '総務部'")
            dept_row = cursor.fetchone()
            dept_id = dept_row["id"] if dept_row else 1
            
            admin_hash, _ = hash_password("admin123")
            cursor.execute("""
                INSERT INTO users (username, password_hash, display_name, department, department_id, user_role)
                VALUES ('admin', ?, '管理者', '総務部', ?, 'ADMIN')
            """, (admin_hash, dept_id))
            print("✅ デフォルト管理者ユーザーを作成しました (admin / admin123)")
            print("✅ デフォルト管理者ユーザーを作成しました (admin / admin123)")
        
        # itemsテーブルにis_activeカラムを追加（存在しない場合のみ）
        cursor.execute("PRAGMA table_info(items)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'is_active' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN is_active INTEGER DEFAULT 1")
            print("✅ itemsテーブルにis_activeカラムを追加しました")
        
        # itemsテーブルに管理部署と資産管理カラムを追加（存在しない場合のみ）
        if 'owner_department_id' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN owner_department_id INTEGER")
            print("✅ itemsテーブルにowner_department_idカラムを追加しました")
        
        if 'is_common' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN is_common INTEGER DEFAULT 0")
            print("✅ itemsテーブルにis_commonカラムを追加しました")
        
        if 'location_text' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN location_text TEXT")
            print("✅ itemsテーブルにlocation_textカラムを追加しました")
        
        if 'last_inspection_date' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN last_inspection_date TEXT")
            print("✅ itemsテーブルにlast_inspection_dateカラムを追加しました")
        
        if 'next_inspection_date' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN next_inspection_date TEXT")
            print("✅ itemsテーブルにnext_inspection_dateカラムを追加しました")
        
        # purchase_requestsテーブルに論理削除カラムを追加（存在しない場合のみ）
        cursor.execute("PRAGMA table_info(purchase_requests)")
        pr_columns = [col[1] for col in cursor.fetchall()]
        if 'deleted_at' not in pr_columns:
            cursor.execute("ALTER TABLE purchase_requests ADD COLUMN deleted_at TEXT")
            print("✅ purchase_requestsテーブルにdeleted_atカラムを追加しました")
        
        if 'deleted_by' not in pr_columns:
            cursor.execute("ALTER TABLE purchase_requests ADD COLUMN deleted_by INTEGER")
            print("✅ purchase_requestsテーブルにdeleted_byカラムを追加しました")
        
        if 'interval_months' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN interval_months INTEGER")
            print("✅ itemsテーブルにinterval_monthsカラムを追加しました")
        
        if 'reorder_point' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN reorder_point INTEGER")
            print("✅ itemsテーブルにreorder_pointカラムを追加しました")
        
        # =================================================================
        # 発注候補テーブル（選別状態を永続化）
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER UNIQUE NOT NULL,
                auto_reason TEXT DEFAULT 'reorder_point',
                selected_for_order INTEGER DEFAULT 0,
                deferred INTEGER DEFAULT 0,
                priority TEXT DEFAULT 'normal',
                recommended_qty INTEGER DEFAULT 0,
                note TEXT,
                status TEXT DEFAULT 'OPEN',
                updated_by_user_id INTEGER,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidates_status 
            ON purchase_candidates(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidates_selected 
            ON purchase_candidates(selected_for_order)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidates_item 
            ON purchase_candidates(item_id)
        """)
        
        # =================================================================
        # 棚卸しセッションテーブル
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocktake_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT,
                status TEXT DEFAULT 'OPEN',
                note TEXT,
                created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stocktake_sessions_status 
            ON stocktake_sessions(status)
        """)
        
        # =================================================================
        # 棚卸し記録テーブル
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocktake_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                system_qty INTEGER DEFAULT 0,
                actual_qty INTEGER,
                diff_qty INTEGER DEFAULT 0,
                counted_by INTEGER,
                counted_at TEXT,
                verified_by INTEGER,
                verified_at TEXT,
                approved_by INTEGER,
                approved_at TEXT,
                note TEXT,
                status TEXT DEFAULT 'PENDING',
                FOREIGN KEY (session_id) REFERENCES stocktake_sessions(id),
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (counted_by) REFERENCES users(id),
                FOREIGN KEY (verified_by) REFERENCES users(id),
                FOREIGN KEY (approved_by) REFERENCES users(id),
                UNIQUE(session_id, item_id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stocktake_records_session 
            ON stocktake_records(session_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stocktake_records_status 
            ON stocktake_records(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stocktake_records_item 
            ON stocktake_records(item_id)
        """)
        
        # =================================================================
        # 棚卸しテンプレートテーブル
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocktake_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                file_type TEXT DEFAULT 'excel',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # =================================================================
        # 棚卸しテンプレートマッピングテーブル
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocktake_template_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                excel_cell TEXT NOT NULL,
                display_label TEXT,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (template_id) REFERENCES stocktake_templates(id),
                UNIQUE(template_id, field_name)
            )
        """)
        
        # itemsテーブルに棚卸し対象フラグを追加（存在しない場合のみ）
        cursor.execute("PRAGMA table_info(items)")
        item_cols = [col[1] for col in cursor.fetchall()]
        if 'is_inventory_target' not in item_cols:
            cursor.execute("ALTER TABLE items ADD COLUMN is_inventory_target INTEGER DEFAULT 1")
            print("✅ itemsテーブルにis_inventory_targetカラムを追加しました")
        
        conn.commit()
        print("✅ テーブルとインデックスを作成しました")


def drop_all_tables():
    """全テーブルを削除（開発用）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS inventory_history")
        cursor.execute("DROP TABLE IF EXISTS inventory")
        cursor.execute("DROP TABLE IF EXISTS items")
        cursor.execute("DROP TABLE IF EXISTS users")
        conn.commit()
        print("✅ 全テーブルを削除しました")


def process_outbound(item_id: int, quantity: int, user_name: str, 
                     department: str = "", note: str = "") -> dict:
    """
    出庫処理を実行（在庫減算 + 履歴記録）
    
    Args:
        item_id: 物品ID
        quantity: 出庫数量（正の整数）
        user_name: 出庫者名
        department: 部署名
        note: 備考
    
    Returns:
        dict: 処理結果 {"success": bool, "message": str, "remaining_quantity": int}
    
    処理フロー:
        1. 現在の在庫数を確認
        2. 在庫数が足りるかチェック
        3. トランザクション開始
        4. 在庫を減算
        5. 履歴に記録
        6. コミット
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 現在の在庫を取得
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
            
            # 2. 在庫数チェック
            if current_quantity < quantity:
                return {
                    "success": False,
                    "message": f"❌ 在庫不足: 現在 {current_quantity} 個、要求 {quantity} 個",
                    "remaining_quantity": current_quantity
                }
            
            # 3-4. 在庫を減算（トランザクション内）
            new_quantity = current_quantity - quantity
            cursor.execute("""
                UPDATE inventory
                SET quantity = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))
            
            # 5. 履歴に記録
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, 
                    user_name, department, status, note, created_at
                ) VALUES (?, 'OUT', ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, quantity, user_name, department, note))
            
            # 6. コミット（contextmanagerで自動実行）
            
            # アラートチェック
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
    """
    ゲストユーザー用の仮出庫処理（在庫は変更せず、履歴のみ記録）
    管理者の承認待ち（PENDING）として記録
    
    Args:
        item_id: 物品ID
        quantity: 出庫数量（正の整数）
        user_name: 出庫者名
        department: 部署名
        note: 備考
    
    Returns:
        dict: 処理結果 {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 物品情報を取得
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
            
            # 在庫チェック（仮入力でも在庫が足りるかは確認）
            if quantity > current_quantity:
                return {
                    "success": False,
                    "message": f"❌ 在庫不足です（現在: {current_quantity}個、申請: {quantity}個）"
                }
            
            # 履歴に仮入力として記録（在庫は変更しない）
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
                # quantity がNULLの場合は0を設定
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
    """
    入庫処理を実行（在庫加算 + 履歴記録）
    
    Args:
        item_id: 物品ID
        quantity: 入庫数量（正の整数）
        user_name: 入庫者名
        department: 部署名
        note: 備考
    
    Returns:
        dict: 処理結果 {"success": bool, "message": str, "new_quantity": int}
    
    処理フロー:
        1. 現在の在庫数を確認
        2. トランザクション開始
        3. 在庫を加算
        4. 履歴に記録
        5. コミット
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 現在の在庫を取得
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
            threshold = result["threshold"] if result["threshold"] is not None else 0
            
            # 2-3. 在庫を加算（トランザクション内）
            new_quantity = current_quantity + quantity
            cursor.execute("""
                UPDATE inventory
                SET quantity = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))
            
            # 4. 履歴に記録
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, 
                    user_name, department, status, note, created_at
                ) VALUES (?, 'IN', ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, quantity, user_name, department, note))
            
            # 5. コミット（contextmanagerで自動実行）
            
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


def get_history_list(period_days: Optional[int] = None, 
                     change_type: str = "すべて",
                     search_query: str = "") -> list:
    """
    履歴一覧を取得（フィルタ対応）
    
    Args:
        period_days: 期間（日数）。Noneの場合は全期間
        change_type: 種別フィルタ（"すべて", "IN", "OUT"）
        search_query: 検索キーワード（品目名、品目コード）
    
    Returns:
        履歴データのリスト（新しい順）
    """
    print(f"[DEBUG] get_history_list called: period_days={period_days}, change_type='{change_type}', search_query='{search_query}'")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # まずinventory_historyから取得
        where_clauses = ["1=1"]
        params = []
        
        # 期間フィルタ
        if period_days is not None:
            where_clauses.append("h.created_at >= datetime('now', '+09:00', ?)")
            params.append(f'-{period_days} days')
        
        # 種別フィルタ
        if change_type and change_type != "すべて":
            where_clauses.append("h.change_type = ?")
            params.append(change_type)
        
        where_sql = " AND ".join(where_clauses)
        
        # まず履歴を取得
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
        
        # 各履歴に対して、itemsとinventoryの情報を追加
        result = []
        for row in history_rows:
            record = dict(row)
            
            # item情報を取得
            cursor.execute("""
                SELECT item_name, item_code FROM items WHERE id = ?
            """, (record['item_id'],))
            item_info = cursor.fetchone()
            
            if item_info:
                record['item_name'] = item_info['item_name']
                record['item_code'] = item_info['item_code']
                
                # キーワード検索フィルタ（item情報取得後にチェック）
                if search_query and search_query.strip():
                    search_param = search_query.strip().lower()
                    if (search_param not in (item_info['item_name'] or '').lower() and 
                        search_param not in (item_info['item_code'] or '').lower()):
                        continue
            else:
                record['item_name'] = '不明'
                record['item_code'] = '不明'
            
            # location情報を取得
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
    """
    直近の履歴を取得（取消UI表示用）
    ※取消済みの履歴は除外
    
    Args:
        change_type: 種別（"IN" or "OUT"）
        limit: 最大件数
    
    Returns:
        直近の履歴リスト（新しい順）
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 直近N件、かつ取消済みでない・UNDO自体でない履歴を取得
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
    """
    履歴が取消可能かどうかをチェック
    
    Args:
        history_id: 履歴ID
        minutes: 何分以内なら取消可能か
    
    Returns:
        (取消可能かどうか, 理由メッセージ)
    """
    # 既に取り消し済みかチェック
    if is_history_undone(history_id):
        return (False, "取消済み")
    
    # 時間チェック
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT created_at FROM inventory_history WHERE id = ?
        """, (history_id,))
        row = cursor.fetchone()
        
        if not row:
            return (False, "取引が見つかりません")
        
        # 時間経過チェック（SQLiteで計算）
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
    """
    指定の履歴が既に取り消し済みかどうかをチェック
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM inventory_history 
            WHERE note LIKE ?
        """, (f"%[UNDO of tx_id={history_id}]%",))
        result = cursor.fetchone()
        return result["cnt"] > 0


def get_history_by_id(history_id: int) -> Optional[dict]:
    """
    履歴IDから履歴レコードを取得
    """
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
    """
    取り消し処理を実行（逆取引を追加）
    
    Args:
        history_id: 取り消す履歴のID
        undo_user_name: 取り消し実行者名
    
    Returns:
        処理結果（success, message, new_quantity）
    """
    try:
        # 既に取り消し済みかチェック
        if is_history_undone(history_id):
            return {
                "success": False,
                "message": "❌ この取引は既に取り消し済みです"
            }
        
        # 元の取引を取得
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
        
        # 逆方向を決定
        if original_type == "OUT":
            reverse_type = "IN"
            quantity_delta = original_quantity
        else:
            reverse_type = "OUT"
            quantity_delta = -original_quantity
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 現在の在庫を取得
            cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
            inv = cursor.fetchone()
            
            if not inv:
                return {"success": False, "message": "❌ 在庫情報が見つかりません"}
            
            current_quantity = inv["quantity"]
            new_quantity = current_quantity + quantity_delta
            
            # 在庫がマイナスにならないかチェック
            if new_quantity < 0:
                return {
                    "success": False,
                    "message": f"❌ 取消できません（在庫不足: 現在 {current_quantity} 個）"
                }
            
            # 在庫を更新
            cursor.execute("""
                UPDATE inventory 
                SET quantity = ?, updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))
            
            # 逆取引を履歴に追加
            undo_note = f"[UNDO of tx_id={history_id}] 取消操作"
            cursor.execute("""
                INSERT INTO inventory_history 
                (item_id, change_type, quantity, user_name, department, status, note, created_at)
                VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, reverse_type, original_quantity, undo_user_name, 
                  original.get("department", ""), undo_note))
            
            # 発注品入庫の取り消しの場合、purchase_requestsのステータスをORDEREDに戻す
            if original_type == "IN" and original.get("note") and "発注品入庫（申請ID:" in original.get("note", ""):
                # 申請IDを抽出
                import re
                match = re.search(r"申請ID:\s*(\d+)", original.get("note", ""))
                if match:
                    request_id = int(match.group(1))
                    # ステータスをRECEIVED→ORDEREDに戻し、入庫情報をクリア
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
    """
    ゲストユーザー用の取消申請（在庫は変更せず、申請のみ記録）
    管理者の承認待ち（PENDING）として記録
    
    Args:
        history_id: 取り消したい履歴ID
        undo_user_name: 取消申請者名
        department: 部署名
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        # 元の履歴情報を取得
        original = get_history_by_id(history_id)
        if not original:
            return {"success": False, "message": "❌ 履歴が見つかりません"}
        
        # 時間制限チェック
        if not can_undo_history(history_id):
            return {"success": False, "message": "❌ 取消可能時間を過ぎています（10分以内）"}
        
        # 既に取消済みかチェック
        if is_history_undone(history_id):
            return {"success": False, "message": "❌ この履歴は既に取り消されています"}
        
        item_id = original["item_id"]
        original_type = original["change_type"]
        original_quantity = original["quantity"]
        item_name = original["item_name"]
        
        # 逆方向を決定
        if original_type == "OUT":
            reverse_type = "IN"
        else:
            reverse_type = "OUT"
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 取消申請を履歴に追加（在庫は変更しない）
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


# =============================================================================
# 在庫調整（ADJUST）関数
# =============================================================================

def process_adjust(item_id: int, new_quantity: int, user_name: str, 
                   department: str = "", reason: str = "") -> dict:
    """
    在庫調整を実行
    管理者専用機能：数量を任意に設定し、差分を履歴に記録
    
    Args:
        item_id: 物品ID
        new_quantity: 調整後の数量（0以上）
        user_name: 調整者名
        department: 部署名
        reason: 調整理由（必須）
        
    Returns:
        dict: {"success": bool, "message": str, "old_quantity": int, "new_quantity": int}
    """
    if not reason or reason.strip() == "":
        return {"success": False, "message": "❌ 調整理由は必須です"}
    
    if new_quantity < 0:
        return {"success": False, "message": "❌ 数量は0以上で指定してください"}
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 物品情報を取得
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
            
            # 差分を計算
            quantity_diff = new_quantity - old_quantity
            
            if quantity_diff == 0:
                return {"success": False, "message": "⚠️ 数量に変更がありません"}
            
            # 在庫を更新
            cursor.execute("""
                UPDATE inventory
                SET quantity = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))
            
            # 履歴に記録（ADJUST種別、差分量を記録）
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


# =============================================================================
# ユーザー認証・管理関数
# =============================================================================

def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    ユーザー認証
    Returns: ユーザー情報（成功時）またはNone（失敗時）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, u.password_hash, u.display_name, 
                       u.department, u.department_id, u.user_role, u.is_active,
                       d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.username = ? AND u.is_active = 1
            """, (username,))
            user = cursor.fetchone()
            
            if user and verify_password(password, user["password_hash"]):
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "display_name": user["display_name"],
                    "department": user["department_name"] or user["department"] or "未設定",
                    "department_id": user["department_id"],
                    "user_role": user["user_role"]
                }
            return None
    except Exception:
        return None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """ユーザーIDからユーザー情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, u.display_name, u.department, u.department_id, 
                       u.user_role, u.is_active, d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.id = ?
            """, (user_id,))
            user = cursor.fetchone()
            if user:
                return dict(user)
            return None
    except Exception:
        return None


def create_user(username: str, password: str, display_name: str, 
                department_id: int, user_role: str) -> dict:
    """
    新規ユーザーを作成
    user_role: 'ADMIN', 'USER', 'GUEST'
    department_id: 部署ID（departmentsテーブルへの外部キー）
    """
    if user_role not in ['ADMIN', 'USER', 'GUEST']:
        return {"success": False, "message": "❌ 無効なユーザー区分です"}
    
    try:
        password_hash, _ = hash_password(password)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 部署名を取得
            cursor.execute("SELECT name FROM departments WHERE id = ?", (department_id,))
            dept = cursor.fetchone()
            dept_name = dept["name"] if dept else "未設定"
            
            cursor.execute("""
                INSERT INTO users (username, password_hash, display_name, department, department_id, user_role)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (username, password_hash, display_name, dept_name, department_id, user_role))
            conn.commit()
            return {"success": True, "message": f"✅ ユーザー '{username}' を作成しました"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"❌ ユーザー名 '{username}' は既に使用されています"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_all_users() -> list:
    """全ユーザー一覧を取得（パスワードハッシュ除く、部署名も取得）"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, u.display_name, u.department, u.department_id,
                       u.user_role, u.is_active, u.created_at, u.updated_at,
                       d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                ORDER BY u.id ASC
            """)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def list_users(include_inactive: bool = False, search_query: str = "",
               role_filter: str = "", department_filter: str = "",
               limit: int = 50, offset: int = 0) -> list:
    """
    ユーザー一覧を取得（検索・フィルタ・ページング対応）
    
    Args:
        include_inactive: True の場合、無効化されたユーザーも含める
        search_query: 検索キーワード（username/display_name）
        role_filter: 権限フィルタ（ADMIN/USER/GUEST）
        department_filter: 部署名でフィルタ
        limit: 取得件数
        offset: 開始位置
    
    Returns:
        ユーザーリスト（dict の list）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT u.id, u.username, u.display_name, u.department, u.department_id,
                       u.user_role, u.is_active, u.created_at, u.updated_at,
                       d.name as department_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE 1=1
            """
            params = []
            
            # 有効/無効フィルタ
            if not include_inactive:
                query += " AND u.is_active = 1"
            
            # 検索条件
            if search_query:
                query += """ AND (
                    u.username LIKE ? OR
                    u.display_name LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param])
            
            # 権限フィルタ
            if role_filter and role_filter != "すべて":
                query += " AND u.user_role = ?"
                params.append(role_filter)
            
            # 部署フィルタ
            if department_filter and department_filter != "すべて":
                query += " AND d.name = ?"
                params.append(department_filter)
            
            # 並び順とページング
            query += " ORDER BY u.id ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ ユーザー一覧取得エラー: {e}")
        return []


def count_users(include_inactive: bool = False, search_query: str = "",
                role_filter: str = "", department_filter: str = "") -> int:
    """
    ユーザーの総件数を取得
    
    Args:
        include_inactive: True の場合、無効化されたユーザーも含める
        search_query: 検索キーワード
        role_filter: 権限フィルタ
        department_filter: 部署名フィルタ
    
    Returns:
        件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT COUNT(*) as count
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE 1=1
            """
            params = []
            
            if not include_inactive:
                query += " AND u.is_active = 1"
            
            if search_query:
                query += """ AND (
                    u.username LIKE ? OR
                    u.display_name LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param])
            
            if role_filter and role_filter != "すべて":
                query += " AND u.user_role = ?"
                params.append(role_filter)
            
            if department_filter and department_filter != "すべて":
                query += " AND d.name = ?"
                params.append(department_filter)
            
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ ユーザー件数取得エラー: {e}")
        return 0


def update_user_status(user_id: int, is_active: int) -> dict:
    """ユーザーの有効/無効を切り替え"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET is_active = ?, updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (is_active, user_id))
            conn.commit()
            status = "有効化" if is_active else "無効化"
            return {"success": True, "message": f"✅ ユーザーを{status}しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_user_role(user_id: int, new_role: str) -> dict:
    """ユーザーの権限を変更"""
    if new_role not in ['ADMIN', 'USER', 'GUEST']:
        return {"success": False, "message": "❌ 無効な権限です"}
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET user_role = ?, updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (new_role, user_id))
            conn.commit()
            role_labels = {'ADMIN': '管理者', 'USER': '一般ユーザー', 'GUEST': 'ゲスト'}
            return {"success": True, "message": f"✅ 権限を「{role_labels[new_role]}」に変更しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


# =============================================================================
# 部署マスター関連関数
# =============================================================================

def get_all_departments(active_only: bool = True) -> list:
    """全部署一覧を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute("SELECT id, name, is_active FROM departments WHERE is_active = 1 ORDER BY id ASC")
            else:
                cursor.execute("SELECT id, name, is_active FROM departments ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def list_departments(include_inactive: bool = False, search_query: str = "",
                     limit: int = 50, offset: int = 0) -> list:
    """
    部署一覧を取得（検索・ページング対応）
    
    Args:
        include_inactive: True の場合、無効化された部署も含める
        search_query: 検索キーワード（部署名）
        limit: 取得件数
        offset: 開始位置
    
    Returns:
        部署リスト（dict の list）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT id, name, is_active FROM departments WHERE 1=1"
            params = []
            
            # 有効/無効フィルタ
            if not include_inactive:
                query += " AND is_active = 1"
            
            # 検索条件
            if search_query:
                query += " AND name LIKE ?"
                params.append(f"%{search_query}%")
            
            # 並び順とページング
            query += " ORDER BY id ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ 部署一覧取得エラー: {e}")
        return []


def count_departments(include_inactive: bool = False, search_query: str = "") -> int:
    """
    部署の総件数を取得
    
    Args:
        include_inactive: True の場合、無効化された部署も含める
        search_query: 検索キーワード
    
    Returns:
        件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*) as count FROM departments WHERE 1=1"
            params = []
            
            if not include_inactive:
                query += " AND is_active = 1"
            
            if search_query:
                query += " AND name LIKE ?"
                params.append(f"%{search_query}%")
            
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ 部署件数取得エラー: {e}")
        return 0


def get_department_by_id(dept_id: int) -> Optional[dict]:
    """部署IDから部署情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, is_active FROM departments WHERE id = ?", (dept_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def get_department_by_name(name: str) -> Optional[dict]:
    """部署名から部署情報を取得"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, is_active FROM departments WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def create_department(name: str) -> dict:
    """新規部署を作成"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO departments (name) VALUES (?)", (name,))
            conn.commit()
            return {"success": True, "message": f"✅ 部署「{name}」を作成しました"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"❌ 部署名「{name}」は既に存在します"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def migrate_users_department_to_id():
    """
    既存ユーザーのdepartment（TEXT）をdepartment_idに移行
    一致しない場合は「未設定」に紐付け
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # department_idがNULLのユーザーを取得
            cursor.execute("SELECT id, department FROM users WHERE department_id IS NULL")
            users_to_migrate = cursor.fetchall()
            
            if not users_to_migrate:
                return {"success": True, "message": "移行対象のユーザーはありません"}
            
            # 「未設定」部署のIDを取得（なければ作成）
            cursor.execute("SELECT id FROM departments WHERE name = '未設定'")
            unset_row = cursor.fetchone()
            if not unset_row:
                cursor.execute("INSERT INTO departments (name) VALUES ('未設定')")
                unset_id = cursor.lastrowid
            else:
                unset_id = unset_row["id"]
            
            migrated_count = 0
            for user in users_to_migrate:
                user_id = user["id"]
                dept_name = user["department"]
                
                # 部署名で検索
                cursor.execute("SELECT id FROM departments WHERE name = ?", (dept_name,))
                dept_row = cursor.fetchone()
                
                if dept_row:
                    dept_id = dept_row["id"]
                else:
                    # 一致しない場合は「未設定」
                    dept_id = unset_id
                
                cursor.execute("""
                    UPDATE users SET department_id = ? WHERE id = ?
                """, (dept_id, user_id))
                migrated_count += 1
            
            conn.commit()
            return {"success": True, "message": f"✅ {migrated_count}件のユーザーを移行しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


# =============================================================================
# 申請（pending_transactions）関連関数
# =============================================================================

# 数量上限・異常値警告の設定（将来の自動発注連携用）
QUANTITY_LIMITS = {
    "outbound_max": 1000,      # 1回の出庫数量上限
    "inbound_max": 10000,      # 1回の入庫数量上限
    "warning_threshold": 100,  # 警告を出す閾値
}

def validate_quantity_for_order(change_type: str, quantity: int, item_id: int = None) -> dict:
    """
    数量の妥当性チェック（将来の自動発注連携用フック）
    
    Returns:
        dict: {
            "valid": bool,
            "warning": str or None,  # 警告メッセージ
            "error": str or None     # エラーメッセージ
        }
    """
    result = {"valid": True, "warning": None, "error": None}
    
    # 上限チェック
    if change_type == 'OUT' and quantity > QUANTITY_LIMITS["outbound_max"]:
        result["valid"] = False
        result["error"] = f"出庫数量が上限（{QUANTITY_LIMITS['outbound_max']}個）を超えています"
        return result
    
    if change_type == 'IN' and quantity > QUANTITY_LIMITS["inbound_max"]:
        result["valid"] = False
        result["error"] = f"入庫数量が上限（{QUANTITY_LIMITS['inbound_max']}個）を超えています"
        return result
    
    # 異常値警告（閾値超え）
    if quantity > QUANTITY_LIMITS["warning_threshold"]:
        result["warning"] = f"数量が{QUANTITY_LIMITS['warning_threshold']}個を超えています。入力ミスでないかご確認ください。"
    
    # TODO: 将来の自動発注連携
    # - 在庫が閾値以下になったら発注フラグを立てる
    # - 発注推奨数量を計算
    # - 外部システム連携（API呼び出し等）
    
    return result


def create_pending_transaction(change_type: str, item_id: int, quantity: int,
                                actor_name: str, note: str, guest_user_id: int,
                                department_id: int) -> dict:
    """
    ゲストユーザーの申請を作成（PENDING状態）
    在庫は更新しない、承認後に更新される
    """
    if change_type not in ['IN', 'OUT']:
        return {"success": False, "message": "❌ 無効な処理種別です"}
    
    if not actor_name or actor_name.strip() == "":
        return {"success": False, "message": "❌ 実行者名は必須です"}
    
    # 数量バリデーション（上限・異常値チェック）
    qty_validation = validate_quantity_for_order(change_type, quantity, item_id)
    if not qty_validation["valid"]:
        return {"success": False, "message": f"❌ {qty_validation['error']}"}
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 物品情報を取得
            cursor.execute("SELECT item_name FROM items WHERE id = ?", (item_id,))
            item = cursor.fetchone()
            if not item:
                return {"success": False, "message": "❌ 物品が見つかりません"}
            
            item_name = item["item_name"]
            
            # 出庫の場合は在庫チェック
            if change_type == 'OUT':
                cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
                inv = cursor.fetchone()
                current_qty = inv["quantity"] if inv else 0
                if quantity > current_qty:
                    return {"success": False, "message": f"❌ 在庫不足です（現在: {current_qty}個）"}
            
            # 申請を作成
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
    """
    申請一覧を取得
    department_id指定時はその部署のみ、Noneで全件
    """
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
    """
    申請を承認し、在庫を更新・履歴に記録
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 申請情報を取得
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
            
            # 現在の在庫を取得
            cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
            inv = cursor.fetchone()
            current_qty = inv["quantity"] if inv else 0
            
            # 在庫更新
            if change_type == "OUT":
                new_qty = current_qty - quantity
                if new_qty < 0:
                    return {"success": False, "message": f"❌ 在庫不足です（現在: {current_qty}個）"}
            else:  # IN
                new_qty = current_qty + quantity
            
            cursor.execute("""
                UPDATE inventory SET quantity = ?, updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_qty, item_id))
            
            # 部署名を取得
            cursor.execute("SELECT name FROM departments WHERE id = ?", (department_id,))
            dept = cursor.fetchone()
            dept_name = dept["name"] if dept else ""
            
            # 履歴に記録（承認者情報を含む）
            history_note = f"[承認済] {note} (実行者: {actor_name}, 承認者: {approver_name})"
            cursor.execute("""
                INSERT INTO inventory_history 
                (item_id, change_type, quantity, user_name, department, status, note, created_at)
                VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
            """, (item_id, change_type, quantity, actor_name, dept_name, history_note))
            
            # 申請を承認済みに更新
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
            
            # 申請情報を取得
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
            
            # 申請を却下に更新
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


# =============================================================================
# 部署マスタ管理（ADMIN向け）
# =============================================================================

def update_department_name(dept_id: int, new_name: str) -> dict:
    """部署名を変更"""
    if not new_name or not new_name.strip():
        return {"success": False, "message": "❌ 部署名は必須です"}
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE departments 
                SET name = ?
                WHERE id = ?
            """, (new_name.strip(), dept_id))
            conn.commit()
            return {"success": True, "message": f"✅ 部署名を「{new_name.strip()}」に変更しました"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"❌ 部署名「{new_name}」は既に存在します"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_department_status(dept_id: int, is_active: int) -> dict:
    """部署の有効/無効を切り替え"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE departments 
                SET is_active = ?
                WHERE id = ?
            """, (is_active, dept_id))
            conn.commit()
            status = "有効化" if is_active else "無効化"
            return {"success": True, "message": f"✅ 部署を{status}しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


# =============================================================================
# ユーザー詳細更新（ADMIN向け）
# =============================================================================

def update_user_full(user_id: int, display_name: str, department_id: int, 
                     user_role: str, is_active: int, new_password: str = None) -> dict:
    """
    ユーザー情報を一括更新（ADMIN専用）
    - display_name: 表示名（必須）
    - department_id: 部署ID（必須）
    - user_role: 権限（ADMIN/USER/GUEST）
    - is_active: 有効/無効
    - new_password: 新しいパスワード（任意、空の場合は変更しない）
    """
    # バリデーション
    if not display_name or not display_name.strip():
        return {"success": False, "message": "❌ 表示名は必須です"}
    
    if user_role not in ['ADMIN', 'USER', 'GUEST']:
        return {"success": False, "message": "❌ 無効な権限です"}
    
    if is_active not in [0, 1]:
        return {"success": False, "message": "❌ 有効/無効の値が不正です"}
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if new_password and new_password.strip():
                # パスワードも更新
                password_hash, _ = hash_password(new_password)
                cursor.execute("""
                    UPDATE users 
                    SET display_name = ?, department_id = ?, user_role = ?, 
                        is_active = ?, password_hash = ?, updated_at = datetime('now', '+09:00')
                    WHERE id = ?
                """, (display_name.strip(), department_id, user_role, is_active, password_hash, user_id))
            else:
                # パスワードは変更しない
                cursor.execute("""
                    UPDATE users 
                    SET display_name = ?, department_id = ?, user_role = ?, 
                        is_active = ?, updated_at = datetime('now', '+09:00')
                    WHERE id = ?
                """, (display_name.strip(), department_id, user_role, is_active, user_id))
            
            conn.commit()
            return {"success": True, "message": "✅ ユーザー情報を更新しました"}
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


# =============================================================================
# 申請取得・取り下げ関連（GUEST向け）
# =============================================================================

def get_my_pending_transactions(user_id: int = None, department_id: int = None, 
                                 change_type: str = None, user_role: str = "GUEST") -> list:
    """
    自分/自部署の申請一覧を取得
    - GUEST: guest_user_id で絞り込み（自分の申請のみ）
    - USER: department_id で絞り込み（自部署の申請）
    - ADMIN: 全件
    """
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
            
            # 権限に応じてフィルタリング
            if user_role == "GUEST" and user_id is not None:
                query += " AND pt.guest_user_id = ?"
                params.append(user_id)
            elif user_role == "USER" and department_id is not None:
                query += " AND pt.department_id = ?"
                params.append(department_id)
            # ADMIN は全件
            
            # change_typeでフィルタリング
            if change_type:
                query += " AND pt.change_type = ?"
                params.append(change_type)
            
            query += " ORDER BY pt.created_at DESC LIMIT 10"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def cancel_pending_transaction(pending_id: int, user_id: int, actor_name: str = None) -> dict:
    """
    申請を取り下げ（CANCELLED に更新）
    GUESTの場合: guest_user_id AND actor_name の両方が一致する場合のみ許可
    
    Args:
        pending_id: 申請ID
        user_id: ユーザーID（guest_user_id）
        actor_name: 申請者名（GUESTの本人確認用、必須）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 申請情報を取得（本人確認）
            cursor.execute("""
                SELECT pt.*, i.item_name
                FROM pending_transactions pt
                JOIN items i ON pt.item_id = i.id
                WHERE pt.id = ? AND pt.status = 'PENDING'
            """, (pending_id,))
            pending = cursor.fetchone()
            
            if not pending:
                return {"success": False, "message": "❌ 申請が見つかりません（既に処理済みの可能性があります）"}
            
            # 厳格な本人確認: guest_user_id AND actor_name の両方が一致する必要あり
            if pending["guest_user_id"] != user_id:
                return {"success": False, "message": "❌ この申請を取り下げる権限がありません（ユーザーID不一致）"}
            
            # actor_name の一致確認（必須）
            if actor_name is None or pending["actor_name"] != actor_name:
                return {"success": False, "message": "❌ この申請を取り下げる権限がありません（申請者名不一致）"}
            
            item_name = pending["item_name"]
            change_type = pending["change_type"]
            quantity = pending["quantity"]
            
            # 申請を取り下げ（CANCELLED）
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
    """
    履歴ページ用の申請一覧を取得（PENDING状態のもの）
    - GUEST: 自分の申請のみ
    - USER: 自部署の申請
    - ADMIN: 全件
    """
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
            # ADMIN は全件
            
            query += " ORDER BY pt.created_at DESC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


# =============================================================================
# 物品マスター管理
# =============================================================================

def list_items(include_inactive: bool = False, search_query: str = "", 
               category_filter: str = "", asset_filter: str = "すべて",
               department_tag_filter: str = "", limit: int = 50, offset: int = 0) -> list:
    """
    物品一覧を取得（検索・フィルタ・ページング対応）
    
    Args:
        include_inactive: True の場合、無効化された物品も含める
        search_query: 検索キーワード（品目名/品目コード/業者名/業者品番）
        category_filter: カテゴリでフィルタ
        asset_filter: "すべて" / "消耗品" / "資産"
        department_tag_filter: 部署タグでフィルタ
        limit: 取得件数
        offset: 開始位置
    
    Returns:
        物品リスト（dict の list）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    i.*,
                    d.name as owner_department_name,
                    CASE 
                        WHEN i.is_common = 1 THEN '全社'
                        WHEN i.department_tags IS NULL OR i.department_tags = '' THEN '未設定'
                        ELSE i.department_tags
                    END as display_department_tags
                FROM items i
                LEFT JOIN departments d ON i.owner_department_id = d.id
                WHERE 1=1
            """
            params = []
            
            # 有効/無効フィルタ
            if not include_inactive:
                query += " AND i.is_active = 1"
            
            # 検索条件
            if search_query:
                query += """ AND (
                    i.item_name LIKE ? OR
                    i.item_code LIKE ? OR
                    i.vendor_name LIKE ? OR
                    i.vendor_item_code LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            # カテゴリフィルタ
            if category_filter and category_filter != "すべて":
                query += " AND i.category = ?"
                params.append(category_filter)
            
            # 資産フィルタ
            if asset_filter == "消耗品":
                query += " AND i.is_asset = 0"
            elif asset_filter == "資産":
                query += " AND i.is_asset = 1"
            
            # 部署タグフィルタ
            if department_tag_filter and department_tag_filter != "すべて":
                if department_tag_filter == "全社":
                    query += " AND i.is_common = 1"
                elif department_tag_filter == "未設定":
                    query += " AND (i.department_tags IS NULL OR i.department_tags = '') AND i.is_common = 0"
                else:
                    query += " AND i.department_tags LIKE ?"
                    params.append(f"%{department_tag_filter}%")
            
            # ソートとページング
            query += " ORDER BY i.updated_at DESC, i.item_name LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ 物品一覧取得エラー: {e}")
        return []


def count_items(include_inactive: bool = False, search_query: str = "", 
                category_filter: str = "", asset_filter: str = "すべて",
                department_tag_filter: str = "") -> int:
    """
    物品の総件数を取得（検索・フィルタ条件に一致するもの）
    
    Args:
        include_inactive: True の場合、無効化された物品も含める
        search_query: 検索キーワード
        category_filter: カテゴリでフィルタ
        asset_filter: "すべて" / "消耗品" / "資産"
        department_tag_filter: 部署タグでフィルタ
    
    Returns:
        件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*) as count FROM items i WHERE 1=1"
            params = []
            
            # 有効/無効フィルタ
            if not include_inactive:
                query += " AND i.is_active = 1"
            
            # 検索条件
            if search_query:
                query += """ AND (
                    i.item_name LIKE ? OR
                    i.item_code LIKE ? OR
                    i.vendor_name LIKE ? OR
                    i.vendor_item_code LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            # カテゴリフィルタ
            if category_filter and category_filter != "すべて":
                query += " AND i.category = ?"
                params.append(category_filter)
            
            # 資産フィルタ
            if asset_filter == "消耗品":
                query += " AND i.is_asset = 0"
            elif asset_filter == "資産":
                query += " AND i.is_asset = 1"
            
            # 部署タグフィルタ
            if department_tag_filter and department_tag_filter != "すべて":
                if department_tag_filter == "全社":
                    query += " AND i.is_common = 1"
                elif department_tag_filter == "未設定":
                    query += " AND (i.department_tags IS NULL OR i.department_tags = '') AND i.is_common = 0"
                else:
                    query += " AND i.department_tags LIKE ?"
                    params.append(f"%{department_tag_filter}%")
            
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ 物品件数取得エラー: {e}")
        return 0


def get_item_master_by_id(item_id: int) -> dict:
    """
    物品IDで物品マスター情報を取得（在庫情報なし）
    
    Args:
        item_id: 物品ID
    
    Returns:
        物品情報（dict）、見つからない場合はNone
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"❌ 物品取得エラー: {e}")
        return None


def insert_item(item_name: str, category: str, item_code: str = None,
               vendor_name: str = None, vendor_item_code: str = None,
               department_tags: str = None, unit_price: float = 0,
               is_asset: int = 0, frequency_tag: str = None,
               expiry_date: str = None, owner_department_id: int = None,
               is_common: int = 0) -> dict:
    """
    新規物品を登録
    
    Args:
        item_name: 品目名（必須）
        category: カテゴリ（必須）
        item_code: 品目コード（任意）
        vendor_name: 業者名
        vendor_item_code: 業者品番
        department_tags: 部署タグ（カンマ区切り）
        unit_price: 単価
        is_asset: 資産フラグ（0: 消耗品, 1: 資産）
        frequency_tag: 使用頻度タグ
        expiry_date: 期限（YYYY-MM-DD形式）
        owner_department_id: 管理部署ID
        is_common: 全社共通フラグ（1: 全社共通）
    
    Returns:
        dict: {"success": bool, "message": str, "item_id": int（成功時のみ）}
    """
    try:
        # バリデーション
        if not item_name or not category:
            return {"success": False, "message": "品目名とカテゴリは必須です"}
        
        # item_codeが無い場合、vendor_name + vendor_item_codeでユニーク判定
        if not item_code:
            if not vendor_name or not vendor_item_code:
                return {"success": False, "message": "品目コードがない場合は業者名と業者品番が必須です"}
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 重複チェック（item_codeがある場合）
            if item_code:
                cursor.execute("SELECT id FROM items WHERE item_code = ?", (item_code,))
                if cursor.fetchone():
                    return {"success": False, "message": f"品目コード「{item_code}」は既に登録されています"}
            
            # 重複チェック（vendor_name + vendor_item_code）
            if vendor_name and vendor_item_code:
                cursor.execute(
                    "SELECT id FROM items WHERE vendor_name = ? AND vendor_item_code = ?",
                    (vendor_name, vendor_item_code)
                )
                if cursor.fetchone():
                    return {"success": False, "message": f"業者名「{vendor_name}」+ 業者品番「{vendor_item_code}」は既に登録されています"}
            
            # 挿入
            cursor.execute("""
                INSERT INTO items (
                    item_name, item_code, vendor_name, vendor_item_code,
                    category, department_tags, unit_price, is_asset,
                    frequency_tag, expiry_date, is_active, owner_department_id, is_common
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (item_name, item_code, vendor_name, vendor_item_code,
                  category, department_tags, unit_price, is_asset,
                  frequency_tag, expiry_date, owner_department_id, is_common))
            
            item_id = cursor.lastrowid
            conn.commit()
            
            return {"success": True, "message": f"✅ 物品「{item_name}」を登録しました", "item_id": item_id}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_item(item_id: int, item_name: str, category: str, item_code: str = None,
               vendor_name: str = None, vendor_item_code: str = None,
               department_tags: str = None, unit_price: float = 0,
               is_asset: int = 0, frequency_tag: str = None,
               expiry_date: str = None, owner_department_id: int = None,
               is_common: int = 0, is_inventory_target: int = 1) -> dict:
    """
    物品情報を更新
    
    Args:
        item_id: 物品ID
        （その他のパラメータはinsert_itemと同じ）
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        # バリデーション
        if not item_name or not category:
            return {"success": False, "message": "品目名とカテゴリは必須です"}
        
        if not item_code:
            if not vendor_name or not vendor_item_code:
                return {"success": False, "message": "品目コードがない場合は業者名と業者品番が必須です"}
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 重複チェック（item_codeがある場合、自分以外）
            if item_code:
                cursor.execute("SELECT id FROM items WHERE item_code = ? AND id != ?", (item_code, item_id))
                if cursor.fetchone():
                    return {"success": False, "message": f"品目コード「{item_code}」は既に他の物品で使用されています"}
            
            # 重複チェック（vendor者名 + vendor_item_code、自分以外）
            if vendor_name and vendor_item_code:
                cursor.execute(
                    "SELECT id FROM items WHERE vendor_name = ? AND vendor_item_code = ? AND id != ?",
                    (vendor_name, vendor_item_code, item_id)
                )
                if cursor.fetchone():
                    return {"success": False, "message": f"業者名「{vendor_name}」+ 業者品番「{vendor_item_code}」は既に他の物品で使用されています"}
            
            # 更新
            cursor.execute("""
                UPDATE items SET
                    item_name = ?, item_code = ?, vendor_name = ?, vendor_item_code = ?,
                    category = ?, department_tags = ?, unit_price = ?, is_asset = ?,
                    frequency_tag = ?, expiry_date = ?, owner_department_id = ?, is_common = ?,
                    is_inventory_target = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (item_name, item_code, vendor_name, vendor_item_code,
                  category, department_tags, unit_price, is_asset,
                  frequency_tag, expiry_date, owner_department_id, is_common,
                  is_inventory_target, item_id))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ 物品「{item_name}」を更新しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def deactivate_item(item_id: int) -> dict:
    """
    物品を無効化（論理削除）
    
    Args:
        item_id: 物品ID
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 物品が存在するか確認
            cursor.execute("SELECT item_name FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "物品が見つかりません"}
            
            item_name = row["item_name"]
            
            # 無効化
            cursor.execute("""
                UPDATE items SET
                    is_active = 0,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (item_id,))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ 物品「{item_name}」を無効化しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def activate_item(item_id: int) -> dict:
    """
    物品を有効化
    
    Args:
        item_id: 物品ID
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 物品が存在するか確認
            cursor.execute("SELECT item_name FROM items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "物品が見つかりません"}
            
            item_name = row["item_name"]
            
            # 有効化
            cursor.execute("""
                UPDATE items SET
                    is_active = 1,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (item_id,))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ 物品「{item_name}」を有効化しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


# =============================================================================
# カテゴリ管理
# =============================================================================

def list_categories(include_inactive: bool = False) -> list:
    """
    カテゴリ一覧を取得
    
    Args:
        include_inactive: True の場合、無効化されたカテゴリも含める
    
    Returns:
        カテゴリリスト（dict の list）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if include_inactive:
                query = "SELECT * FROM categories ORDER BY name"
            else:
                query = "SELECT * FROM categories WHERE is_active = 1 ORDER BY name"
            
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ カテゴリ一覧取得エラー: {e}")
        return []


def get_category_names() -> list:
    """
    有効なカテゴリ名のリストを取得（プルダウン用）
    
    Returns:
        カテゴリ名のリスト
    """
    categories = list_categories(include_inactive=False)
    return [cat['name'] for cat in categories]


def insert_category(name: str) -> dict:
    """
    新規カテゴリを登録
    
    Args:
        name: カテゴリ名
    
    Returns:
        成功/失敗メッセージを含むdict
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 重複チェック
            cursor.execute("SELECT COUNT(*) as count FROM categories WHERE name = ?", (name,))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ カテゴリ「{name}」は既に登録されています"}
            
            # 登録
            cursor.execute("""
                INSERT INTO categories (name) VALUES (?)
            """, (name,))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ カテゴリ「{name}」を登録しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


# =============================================================================
# 業者管理（発注書自動作成を見据えた設計）
# =============================================================================

def list_vendors(include_inactive: bool = False, search_query: str = "",
                 limit: int = 50, offset: int = 0) -> list:
    """
    業者一覧を取得（検索・ページング対応）
    
    Args:
        include_inactive: True の場合、無効化された業者も含める
        search_query: 検索キーワード（業者名/業者コード/電話/メール）
        limit: 取得件数
        offset: 開始位置
    
    Returns:
        業者リスト（dict の list）
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM vendors WHERE 1=1"
            params = []
            
            # 有効/無効フィルタ
            if not include_inactive:
                query += " AND is_active = 1"
            
            # 検索条件
            if search_query:
                query += """ AND (
                    vendor_name LIKE ? OR
                    vendor_code LIKE ? OR
                    phone LIKE ? OR
                    email LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            # 並び順とページング
            query += " ORDER BY id ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ 業者一覧取得エラー: {e}")
        return []


def count_vendors(include_inactive: bool = False, search_query: str = "") -> int:
    """
    業者の総件数を取得
    
    Args:
        include_inactive: True の場合、無効化された業者も含める
        search_query: 検索キーワード
    
    Returns:
        件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*) as count FROM vendors WHERE 1=1"
            params = []
            
            if not include_inactive:
                query += " AND is_active = 1"
            
            if search_query:
                query += """ AND (
                    vendor_name LIKE ? OR
                    vendor_code LIKE ? OR
                    phone LIKE ? OR
                    email LIKE ?
                )"""
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception as e:
        print(f"❌ 業者件数取得エラー: {e}")
        return 0


def get_vendor_names() -> list:
    """
    有効な業者名のリストを取得（プルダウン用）
    
    Returns:
        業者名のリスト
    """
    vendors = list_vendors(include_inactive=False)
    return [vendor['vendor_name'] for vendor in vendors]


def get_vendor_by_id(vendor_id: int) -> dict:
    """
    業者IDから業者情報を取得
    
    Args:
        vendor_id: 業者ID
    
    Returns:
        業者情報（dict）、存在しない場合はNone
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"❌ 業者取得エラー: {e}")
        return None


def get_vendor_by_name(vendor_name: str) -> dict:
    """
    業者名から業者情報を取得
    
    Args:
        vendor_name: 業者名
    
    Returns:
        業者情報（dict）、存在しない場合はNone
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE vendor_name = ?", (vendor_name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"❌ 業者取得エラー: {e}")
        return None


def insert_vendor(vendor_code: str, vendor_name: str, address: str = "", 
                 phone: str = "", email: str = "") -> dict:
    """
    新規業者を登録
    
    Args:
        vendor_code: 業者コード（必須、一意）
        vendor_name: 業者名（必須、一意）
        address: 所在地（任意）
        phone: 電話番号（任意）
        email: メールアドレス（任意）
    
    Returns:
        成功/失敗メッセージを含むdict
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 重複チェック（コード）
            cursor.execute("SELECT COUNT(*) as count FROM vendors WHERE vendor_code = ?", (vendor_code,))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者コード「{vendor_code}」は既に登録されています"}
            
            # 重複チェック（名前）
            cursor.execute("SELECT COUNT(*) as count FROM vendors WHERE vendor_name = ?", (vendor_name,))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者名「{vendor_name}」は既に登録されています"}
            
            # 登録
            cursor.execute("""
                INSERT INTO vendors (vendor_code, vendor_name, address, phone, email) 
                VALUES (?, ?, ?, ?, ?)
            """, (vendor_code, vendor_name, address or None, phone or None, email or None))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ 業者「{vendor_name}」を登録しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def update_vendor(vendor_id: int, vendor_code: str, vendor_name: str, 
                 address: str = "", phone: str = "", email: str = "") -> dict:
    """
    業者情報を更新
    
    Args:
        vendor_id: 業者ID
        vendor_code: 業者コード
        vendor_name: 業者名
        address: 所在地
        phone: 電話番号
        email: メールアドレス
    
    Returns:
        成功/失敗メッセージを含むdict
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 存在確認
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "業者が見つかりません"}
            
            # 重複チェック（コード、自分以外）
            cursor.execute("""
                SELECT COUNT(*) as count FROM vendors 
                WHERE vendor_code = ? AND id != ?
            """, (vendor_code, vendor_id))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者コード「{vendor_code}」は既に使用されています"}
            
            # 重複チェック（名前、自分以外）
            cursor.execute("""
                SELECT COUNT(*) as count FROM vendors 
                WHERE vendor_name = ? AND id != ?
            """, (vendor_name, vendor_id))
            if cursor.fetchone()["count"] > 0:
                return {"success": False, "message": f"❌ 業者名「{vendor_name}」は既に使用されています"}
            
            # 更新
            cursor.execute("""
                UPDATE vendors SET
                    vendor_code = ?,
                    vendor_name = ?,
                    address = ?,
                    phone = ?,
                    email = ?,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (vendor_code, vendor_name, address or None, phone or None, email or None, vendor_id))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ 業者「{vendor_name}」を更新しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def deactivate_vendor(vendor_id: int) -> dict:
    """
    業者を無効化（論理削除）
    
    Args:
        vendor_id: 業者ID
    
    Returns:
        成功/失敗メッセージを含むdict
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 存在確認
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "業者が見つかりません"}
            
            vendor_name = row["vendor_name"]
            
            # 無効化
            cursor.execute("""
                UPDATE vendors SET
                    is_active = 0,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (vendor_id,))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ 業者「{vendor_name}」を無効化しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def activate_vendor(vendor_id: int) -> dict:
    """
    業者を有効化
    
    Args:
        vendor_id: 業者ID
    
    Returns:
        成功/失敗メッセージを含むdict
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 存在確認
            cursor.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "業者が見つかりません"}
            
            vendor_name = row["vendor_name"]
            
            # 有効化
            cursor.execute("""
                UPDATE vendors SET
                    is_active = 1,
                    updated_at = datetime('now', '+09:00')
                WHERE id = ?
            """, (vendor_id,))
            
            conn.commit()
            
            return {"success": True, "message": f"✅ 業者「{vendor_name}」を有効化しました"}
            
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


# =============================================================================
# デモモード関連
# =============================================================================

def insert_demo_data() -> dict:
    """
    デモ用のサンプルデータを一括投入（UPSERT方式）
    
    Returns:
        dict: 投入結果と件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            counts = {
                "departments": 0,
                "users": 0,
                "vendors": 0,
                "categories": 0,
                "items": 0,
                "inventory": 0,
                "history": 0,
                "approvals": 0
            }
            
            # 1. 部署（5件）- 同名なら無視
            print("📂 部署を投入中...")
            departments = [
                "総務部", "営業部", "開発部", "経理部", "人事部"
            ]
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
            
            # 部署IDマップと名前マップを取得
            cursor.execute("SELECT id, name FROM departments WHERE name IN (?, ?, ?, ?, ?)", 
                          tuple(departments))
            dept_map = {row["name"]: row["id"] for row in cursor.fetchall()}
            dept_name_map = {row["id"]: row["name"] for row in cursor.fetchall()}
            
            # 部署IDから名前を取得し直す
            cursor.execute("SELECT id, name FROM departments")
            dept_id_to_name = {row["id"]: row["name"] for row in cursor.fetchall()}
            
            # 2. ユーザー（7名）- username重複時はスキップ
            print("👥 ユーザーを投入中...")
            users_data = [
                # username, password, display_name, department_name, role
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
                    
                    # 既存チェック
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
                print(f"   失敗したユーザー: username={username}, dept_name={dept_name}, dept_id={dept_id}")
                raise
            
            # 3. 業者（5社）- vendor_code重複時は更新
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
            
            # 業者IDを取得
            cursor.execute("SELECT id, vendor_code FROM vendors")
            vendor_map = {row["vendor_code"]: row["id"] for row in cursor.fetchall()}
            
            # 4. カテゴリ（6種類）- 同名なら無視
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
            
            # カテゴリIDを取得
            cursor.execute("SELECT id, name FROM categories")
            
            # カテゴリIDを取得
            cursor.execute("SELECT id, name FROM categories")
            cat_map = {row["name"]: row["id"] for row in cursor.fetchall()}
            
            # 5. 物品（24件）- item_code重複時は無視
            print("📦 物品を投入中...")
            # カテゴリ名から業者名へのマッピング
            category_vendor_map = {
                "文房具": "株式会社文具センター",
                "電子機器": "電子部品商事",
                "家具": "オフィス家具プロ",
                "消耗品": "佐藤商店",
                "工具": "山田工業用品",
                "薬品": "株式会社文具センター"
            }
            
            # 期限設定用の日付計算
            from datetime import datetime, timedelta
            today = datetime.now(JST)
            
            items_data = [
                # item_code, item_name, category, vendor_name, reorder_point, expiry_date, department_tags
                # 文房具（reorder_point設定、期限なし、全社共通）
                ("P001", "ボールペン（黒）", "文房具", "株式会社文具センター", 50, None, "全社"),
                ("P002", "A4コピー用紙", "文房具", "株式会社文具センター", 100, None, "全社"),
                ("P003", "クリアファイル", "文房具", "株式会社文具センター", 30, None, "全社"),
                ("P004", "付箋セット", "文房具", "株式会社文具センター", 20, None, "全社"),
                
                # 電子機器（一部reorder_point設定、営業部専用と全社共通）
                ("E001", "USBメモリ 32GB", "電子機器", "電子部品商事", 10, None, "営業部,開発部"),
                ("E002", "HDMIケーブル 2m", "電子機器", "電子部品商事", None, None, "全社"),
                ("E003", "マウス（無線）", "電子機器", "電子部品商事", 15, None, "全社"),
                ("E004", "キーボード", "電子機器", "電子部品商事", None, None, "開発部"),
                
                # 家具（reorder_pointなし、総務部管理）
                ("F001", "オフィスチェア", "家具", "オフィス家具プロ", None, None, "総務部"),
                ("F002", "デスク", "家具", "オフィス家具プロ", None, None, "総務部"),
                ("F003", "書棚", "家具", "オフィス家具プロ", None, None, "総務部"),
                ("F004", "ホワイトボード", "家具", "オフィス家具プロ", None, None, "全社"),
                
                # 消耗品（reorder_point設定、期限なし、全社共通）
                ("C001", "トイレットペーパー", "消耗品", "佐藤商店", 200, None, "全社"),
                ("C002", "ティッシュペーパー", "消耗品", "佐藤商店", 150, None, "全社"),
                ("C003", "ゴミ袋（大）", "消耗品", "佐藤商店", 100, None, "全社"),
                ("C004", "洗剤", "消耗品", "佐藤商店", 50, None, "全社"),
                
                # 工具（reorder_point設定、期限なし、開発部と営業部）
                ("T001", "ドライバーセット", "工具", "山田工業用品", 5, None, "開発部"),
                ("T002", "六角レンチセット", "工具", "山田工業用品", 5, None, "開発部"),
                ("T003", "メジャー 5m", "工具", "山田工業用品", 10, None, "営業部"),
                ("T004", "カッターナイフ", "工具", "山田工業用品", 20, None, "全社"),
                
                # 薬品（reorder_point設定、期限あり、人事部専用）
                ("M001", "造影剤 イオメロン300", "薬品", "株式会社文具センター", 10, (today - timedelta(days=5)).strftime("%Y-%m-%d"), "人事部"),  # 期限切れ
                ("M002", "消毒用エタノール 500ml", "薬品", "株式会社文具センター", 20, (today + timedelta(days=7)).strftime("%Y-%m-%d"), "人事部"),  # 7日後
                ("M003", "滅菌ガーゼ 5x5cm", "薬品", "株式会社文具センター", 30, (today + timedelta(days=15)).strftime("%Y-%m-%d"), "人事部"),  # 15日後
                ("M004", "注射器 5ml（使い捨て）", "薬品", "株式会社文具センター", 50, (today + timedelta(days=25)).strftime("%Y-%m-%d"), "人事部"),  # 25日後
            ]
            
            try:
                for code, name, category, vendor_name, reorder_pt, expiry, dept_tags in items_data:
                    # 既存チェック
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
                print(f"   失敗した物品: code={code}, name={name}, category={category}")
                raise
            
            # アイテムIDを取得
            cursor.execute("SELECT id, item_code FROM items")
            item_map = {row["item_code"]: row["id"] for row in cursor.fetchall()}
            
            # 6. 在庫（各物品に在庫を設定）
            print("📊 在庫を投入中...")
            try:
                import random
                
                # アラート用の在庫数設定
                # reorder_pointがある物品のうち一部は在庫不足にする
                low_stock_codes = ["P001", "P003", "E001", "C001", "T001", "M001"]  # 在庫不足にする物品（薬品M001を追加）
                
                for item_code, item_id in item_map.items():
                    # 既存在庫チェック
                    cursor.execute("SELECT id FROM inventory WHERE item_id = ?", (item_id,))
                    if cursor.fetchone():
                        continue  # 既にある場合はスキップ
                    
                    # reorder_pointを取得
                    cursor.execute("SELECT reorder_point FROM items WHERE id = ?", (item_id,))
                    result = cursor.fetchone()
                    reorder_pt = result["reorder_point"] if result and result["reorder_point"] else None
                    
                    # 在庫数を設定
                    if item_code in low_stock_codes and reorder_pt:
                        # 在庫不足：reorder_point以下にする
                        qty = random.randint(1, max(1, reorder_pt - 5))
                    elif reorder_pt:
                        # 正常在庫：reorder_pointより多めに設定
                        qty = random.randint(reorder_pt + 10, reorder_pt + 50)
                    else:
                        # reorder_pointなし：適当な在庫数
                        qty = random.randint(10, 50)
                    
                    cursor.execute(
                        "INSERT INTO inventory (item_id, quantity, location) VALUES (?, ?, ?)",
                        (item_id, qty, "倉庫A")
                    )
                    counts["inventory"] += 1
            except Exception as e:
                print(f"❌ 在庫投入エラー: {e}")
                raise
            
            # 7. 在庫履歴（各物品に2-3件の履歴）
            print("📝 履歴を投入中...")
            try:
                cursor.execute("SELECT username FROM users LIMIT 1")
                demo_user = cursor.fetchone()
                demo_username = demo_user["username"] if demo_user else "admin"
                
                for item_code, item_id in list(item_map.items())[:10]:  # 最初の10件のみ履歴を追加
                    for i in range(2):
                        change_type = "入庫" if i == 0 else "出庫"
                        qty = 10 if change_type == "入庫" else -5
                        cursor.execute("""
                            INSERT INTO inventory_history 
                            (item_id, change_type, quantity, user_name, note, created_at)
                            VALUES (?, ?, ?, ?, ?, datetime('now', '+09:00', ?))
                        """, (item_id, change_type, qty, demo_username, f"デモデータ - {change_type}", f"-{i} days"))
                        counts["history"] += 1
            except Exception as e:
                print(f"❌ 履歴投入エラー: {e}")
                raise
            
            # 8. 承認待ち（スキップ - approval_queueテーブルが存在しない場合）
            print("✋ 承認待ちをスキップ（テーブルが存在しない可能性）")
            
            # 9. 棚卸し対象フラグの設定
            print("🏷️ 棚卸し対象フラグを設定中...")
            try:
                # 文房具・消耗品は棚卸し非対象（安価な日用品・事務用品）
                non_target_codes = ["P001", "P002", "P003", "P004",
                                    "C001", "C002", "C003", "C004"]
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
                # 既存セッションチェック
                cursor.execute(
                    "SELECT id FROM stocktake_sessions WHERE name = ?",
                    ("2026年3月定期棚卸し",)
                )
                existing_session = cursor.fetchone()
                
                if not existing_session:
                    # セッション作成
                    now_str = get_jst_now_str()
                    cursor.execute("""
                        INSERT INTO stocktake_sessions
                        (name, start_date, end_date, status, note, created_by, created_at)
                        VALUES (?, ?, ?, 'OPEN', ?, ?, ?)
                    """, (
                        "2026年3月定期棚卸し",
                        "2026-03-01",
                        "2026-03-15",
                        "デモ用棚卸しセッション。医薬品・電子機器・家具・工具が対象です。",
                        1,  # admin user
                        now_str,
                    ))
                    session_id = cursor.lastrowid
                    counts["stocktake_sessions"] = 1
                    print(f"  ✓ 棚卸しセッション作成 (ID={session_id})")
                    
                    # 棚卸し対象物品のレコードを生成
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
                    
                    # ユーザーIDを取得
                    cursor.execute("SELECT id FROM users WHERE username = 'admin' LIMIT 1")
                    admin_row = cursor.fetchone()
                    admin_id = admin_row["id"] if admin_row else 1
                    
                    cursor.execute("SELECT id FROM users WHERE username = 'tanaka' LIMIT 1")
                    tanaka_row = cursor.fetchone()
                    tanaka_id = tanaka_row["id"] if tanaka_row else 2
                    
                    cursor.execute("SELECT id FROM users WHERE username = 'suzuki' LIMIT 1")
                    suzuki_row = cursor.fetchone()
                    suzuki_id = suzuki_row["id"] if suzuki_row else 3
                    
                    # 棚卸しレコードに多様なステータスを設定
                    # レコードを取得
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
                        
                        # 医薬品: 差異ありCOUNTED（不足・過剰混在）
                        if code == "M001":
                            # 造影剤: 不足2個 → COUNTED
                            actual = max(0, sys_qty - 2)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?, note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  "使用済み分が未記録の可能性", rec_id))
                        
                        elif code == "M002":
                            # 消毒用エタノール: 一致 → VERIFIED
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'VERIFIED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?
                                WHERE id = ?
                            """, (sys_qty, suzuki_id, now_str,
                                  admin_id, now_str, rec_id))
                        
                        elif code == "M003":
                            # 滅菌ガーゼ: 過剰3個 → APPROVED
                            actual = sys_qty + 3
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'APPROVED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?,
                                    approved_by = ?, approved_at = ?,
                                    note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  admin_id, now_str, admin_id, now_str,
                                  "納品時の数量誤り", rec_id))
                        
                        elif code == "M004":
                            # 注射器: 一致 → COUNTED
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?
                                WHERE id = ?
                            """, (sys_qty, suzuki_id, now_str, rec_id))
                        
                        # 電子機器: 一部入力済み
                        elif code == "E001":
                            # USBメモリ: 不足1個 → COUNTED
                            actual = max(0, sys_qty - 1)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?,
                                    note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  "紛失の可能性あり", rec_id))
                        
                        elif code == "E002":
                            # HDMIケーブル: 一致 → VERIFIED
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'VERIFIED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?
                                WHERE id = ?
                            """, (sys_qty, tanaka_id, now_str,
                                  admin_id, now_str, rec_id))
                        
                        # E003, E004 は PENDING のまま（未入力）
                        
                        # 家具: 全て入力済み
                        elif code == "F001":
                            # オフィスチェア: 一致 → APPROVED
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
                            # デスク: 過剰1台 → VERIFIED
                            actual = sys_qty + 1
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'VERIFIED',
                                    counted_by = ?, counted_at = ?,
                                    verified_by = ?, verified_at = ?,
                                    note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, suzuki_id, now_str,
                                  admin_id, now_str, "未登録のデスクが1台あり", rec_id))
                        
                        elif code == "F003":
                            # 書棚: 一致 → COUNTED
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?
                                WHERE id = ?
                            """, (sys_qty, suzuki_id, now_str, rec_id))
                        
                        elif code == "F004":
                            # ホワイトボード: 不足1台 → COUNTED
                            actual = max(0, sys_qty - 1)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?,
                                    note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, tanaka_id, now_str,
                                  "会議室Bから移動済み？要確認", rec_id))
                        
                        # 工具: T001, T002 は PENDING（未入力）
                        elif code == "T003":
                            # メジャー: 一致 → COUNTED
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = 0, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?
                                WHERE id = ?
                            """, (sys_qty, tanaka_id, now_str, rec_id))
                        
                        elif code == "T004":
                            # カッターナイフ: 不足5個 → COUNTED
                            actual = max(0, sys_qty - 5)
                            cursor.execute("""
                                UPDATE stocktake_records SET
                                    actual_qty = ?, diff_qty = ?, status = 'COUNTED',
                                    counted_by = ?, counted_at = ?,
                                    note = ?
                                WHERE id = ?
                            """, (actual, actual - sys_qty, suzuki_id, now_str,
                                  "各部署への貸出分が戻っていない", rec_id))
                        
                        # T001, T002, E003, E004 は PENDING のまま
                    
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
    """
    デモデータをリセット
    
    Args:
        keep_users_and_depts: Trueの場合、users/departmentsは残す
    
    Returns:
        dict: 削除結果と件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            counts = {
                "stocktake_records": 0,
                "stocktake_sessions": 0,
                "approvals": 0,
                "history": 0,
                "inventory": 0,
                "items": 0,
                "categories": 0,
                "vendors": 0,
                "users": 0,
                "departments": 0
            }
            
            # 棚卸し関連削除
            try:
                cursor.execute("DELETE FROM stocktake_records")
                counts["stocktake_records"] = cursor.rowcount
                cursor.execute("DELETE FROM stocktake_sessions")
                counts["stocktake_sessions"] = cursor.rowcount
            except Exception:
                counts["stocktake_records"] = 0
                counts["stocktake_sessions"] = 0
            
            # 承認待ち削除（テーブルが存在する場合のみ）
            try:
                cursor.execute("DELETE FROM approval_queue")
                counts["approvals"] = cursor.rowcount
            except Exception:
                counts["approvals"] = 0
            
            # 在庫履歴削除
            cursor.execute("DELETE FROM inventory_history")
            counts["history"] = cursor.rowcount
            
            # 在庫削除
            cursor.execute("DELETE FROM inventory")
            counts["inventory"] = cursor.rowcount
            
            # 物品削除
            cursor.execute("DELETE FROM items")
            counts["items"] = cursor.rowcount
            
            # カテゴリ削除
            cursor.execute("DELETE FROM categories")
            counts["categories"] = cursor.rowcount
            
            # 業者削除
            cursor.execute("DELETE FROM vendors")
            counts["vendors"] = cursor.rowcount
            
            # users/departmentsも削除する場合
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


def get_stock_alerts(department_name: str = None) -> list:
    """
    在庫アラートを取得
    inventory.quantity <= items.reorder_point の物品を返す
    
    Args:
        department_name: 部署名でフィルタリング（Noneの場合は全部署）
    
    Returns:
        list: アラート物品のリスト
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 部署フィルタリングを追加
            if department_name:
                cursor.execute("""
                    SELECT 
                        i.id,
                        i.item_name,
                        i.item_code,
                        i.category,
                        i.vendor_name,
                        i.reorder_point,
                        inv.quantity,
                        inv.location
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
                    SELECT 
                        i.id,
                        i.item_name,
                        i.item_code,
                        i.category,
                        i.vendor_name,
                        i.reorder_point,
                        inv.quantity,
                        inv.location
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
    
    Args:
        department_name: 部署名でフィルタリング（Noneの場合は全部署）
    
    Returns:
        dict: {
            "expired": [...],  # 期限切れ
            "expiring_soon": [...]  # 期限間近（30日以内）
        }
    """
    try:
        from datetime import datetime, timedelta
        
        today = datetime.now(JST).date()
        threshold_date = today + timedelta(days=30)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 部署フィルタリングを追加（全社共通は除外）
            if department_name:
                cursor.execute("""
                    SELECT 
                        i.id,
                        i.item_name,
                        i.item_code,
                        i.category,
                        i.vendor_name,
                        i.expiry_date,
                        inv.quantity,
                        inv.location
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.expiry_date IS NOT NULL
                      AND i.expiry_date != ''
                      AND i.is_active = 1
                      AND i.department_tags LIKE ?
                    ORDER BY i.expiry_date ASC, i.item_name
                """, (f'%{department_name}%',))
            else:
                cursor.execute("""
                    SELECT 
                        i.id,
                        i.item_name,
                        i.item_code,
                        i.category,
                        i.vendor_name,
                        i.expiry_date,
                        inv.quantity,
                        inv.location
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.expiry_date IS NOT NULL
                      AND i.expiry_date != ''
                      AND i.is_active = 1
                    ORDER BY i.expiry_date ASC, i.item_name
                """)
            
            results = cursor.fetchall()
            
            expired = []
            expiring_soon = []
            
            for row in results:
                row_dict = dict(row)
                try:
                    # YYYY-MM-DD または YYYY-MM 形式をパース
                    expiry_str = row_dict['expiry_date']
                    if len(expiry_str) == 7:  # YYYY-MM
                        expiry_date = datetime.strptime(expiry_str + "-01", "%Y-%m-%d").date()
                    else:  # YYYY-MM-DD
                        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                    
                    row_dict['expiry_date_parsed'] = expiry_date
                    
                    if expiry_date < today:
                        expired.append(row_dict)
                    elif expiry_date <= threshold_date:
                        expiring_soon.append(row_dict)
                except Exception:
                    # 日付のパースに失敗した場合はスキップ
                    continue
            
            return {
                "expired": expired,
                "expiring_soon": expiring_soon
            }
    except Exception as e:
        print(f"❌ 期限アラート取得エラー: {e}")
        return {"expired": [], "expiring_soon": []}


# =============================================================================
# 廃棄管理機能
# =============================================================================

def create_disposal_request(item_id: int, quantity: int, reason: str, requester_id: int) -> dict:
    """
    廃棄申請を作成
    
    Args:
        item_id: 物品ID
        quantity: 廃棄数量
        reason: 廃棄理由
        requester_id: 申請者ID
    
    Returns:
        dict: 処理結果
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 物品情報を取得
            cursor.execute("""
                SELECT i.item_name, inv.quantity
                FROM items i
                JOIN inventory inv ON i.id = inv.item_id
                WHERE i.id = ?
            """, (item_id,))
            
            result = cursor.fetchone()
            if not result:
                return {"success": False, "message": "❌ 物品が見つかりません"}
            
            item_name = result["item_name"]
            current_quantity = result["quantity"]
            
            # 在庫数チェック
            if quantity > current_quantity:
                return {
                    "success": False,
                    "message": f"❌ 在庫数（{current_quantity}）を超えて廃棄することはできません"
                }
            
            # 廃棄申請を登録
            cursor.execute("""
                INSERT INTO disposal_requests 
                (item_id, quantity, reason, requester_id, status, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', datetime('now', '+09:00'))
            """, (item_id, quantity, reason, requester_id))
            
            conn.commit()
            
            return {
                "success": True,
                "message": f"✅ {item_name} の廃棄申請を登録しました（{quantity}個）"
            }
    
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_disposal_requests(status: str = None, requester_id: int = None) -> list:
    """
    廃棄申請一覧を取得
    
    Args:
        status: ステータスフィルタ（'PENDING', 'APPROVED', 'REJECTED'）
        requester_id: 申請者IDフィルタ
    
    Returns:
        list: 廃棄申請リスト
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    dr.id,
                    dr.item_id,
                    i.item_name,
                    i.item_code,
                    i.category,
                    i.unit_price,
                    dr.quantity,
                    dr.reason,
                    dr.status,
                    u.display_name as requester_name,
                    dr.created_at,
                    dr.approved_at,
                    approver.display_name as approver_name,
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
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
    
    except Exception as e:
        print(f"❌ 廃棄申請取得エラー: {e}")
        return []


def approve_disposal_request(request_id: int, approver_id: int) -> dict:
    """
    廃棄申請を承認して在庫を減算
    
    Args:
        request_id: 廃棄申請ID
        approver_id: 承認者ID
    
    Returns:
        dict: 処理結果
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 申請情報を取得
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
            
            item_id = request["item_id"]
            quantity = request["quantity"]
            item_name = request["item_name"]
            requester_name = request["requester_name"]
            
            # 在庫を取得
            cursor.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
            inv_result = cursor.fetchone()
            
            if not inv_result:
                return {"success": False, "message": "❌ 在庫情報が見つかりません"}
            
            current_qty = inv_result["quantity"]
            
            if quantity > current_qty:
                return {
                    "success": False,
                    "message": f"❌ 在庫数（{current_qty}）が不足しています"
                }
            
            # 申請を承認済みに更新（冪等性確保：PENDING時のみ更新）
            cursor.execute("""
                UPDATE disposal_requests
                SET status = 'APPROVED',
                    approved_by = ?,
                    approved_at = datetime('now', '+09:00')
                WHERE id = ? AND status = 'PENDING'
            """, (approver_id, request_id))
            
            # 更新行数を確認（0なら既に処理済み）
            if cursor.rowcount == 0:
                return {
                    "success": False,
                    "message": "⚠️ この申請は既に処理済みです"
                }
            
            # 在庫を減算（承認成功時のみ）
            new_quantity = current_qty - quantity
            cursor.execute("""
                UPDATE inventory 
                SET quantity = ?, updated_at = datetime('now', '+09:00')
                WHERE item_id = ?
            """, (new_quantity, item_id))
            
            # 履歴を記録（承認成功時のみ）
            cursor.execute("""
                INSERT INTO inventory_history 
                (item_id, change_type, quantity, user_name, note, created_at)
                VALUES (?, 'DISPOSE', ?, ?, ?, datetime('now', '+09:00'))
            """, (item_id, -quantity, requester_name, f"廃棄承認（理由: {request['reason']}）"))
            
            conn.commit()
            
            return {
                "success": True,
                "message": f"✅ {item_name} の廃棄を承認しました（{quantity}個廃棄、残: {new_quantity}）"
            }
    
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def reject_disposal_request(request_id: int, approver_id: int, reject_reason: str) -> dict:
    """
    廃棄申請を却下
    
    Args:
        request_id: 廃棄申請ID
        approver_id: 承認者ID
        reject_reason: 却下理由
    
    Returns:
        dict: 処理結果
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 申請情報を取得
            cursor.execute("""
                SELECT dr.*, i.item_name
                FROM disposal_requests dr
                JOIN items i ON dr.item_id = i.id
                WHERE dr.id = ?
            """, (request_id,))
            
            request = cursor.fetchone()
            if not request:
                return {"success": False, "message": "❌ 申請が見つかりません"}
            
            if request["status"] != "PENDING":
                return {"success": False, "message": "❌ この申請は既に処理済みです"}
            
            # 申請を却下に更新（冪等性確保：PENDING時のみ更新）
            cursor.execute("""
                UPDATE disposal_requests
                SET status = 'REJECTED',
                    approved_by = ?,
                    approved_at = datetime('now', '+09:00'),
                    reject_reason = ?
                WHERE id = ? AND status = 'PENDING'
            """, (approver_id, reject_reason, request_id))
            
            # 更新行数を確認（0なら既に処理済み）
            if cursor.rowcount == 0:
                return {
                    "success": False,
                    "message": "⚠️ この申請は既に処理済みです"
                }
            
            conn.commit()
            
            return {
                "success": True,
                "message": f"✅ {request['item_name']} の廃棄申請を却下しました"
            }
    
    except Exception as e:
        return {"success": False, "message": f"❌ エラー: {str(e)}"}


def get_disposal_count(status: str = "PENDING") -> int:
    """
    廃棄申請の件数を取得
    
    Args:
        status: ステータス（デフォルト: PENDING）
    
    Returns:
        int: 件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM disposal_requests 
                WHERE status = ?
            """, (status,))
            result = cursor.fetchone()
            return result["count"] if result else 0
    except Exception:
        return 0


# =============================================================================
# ダッシュボード KPI 集計関連
# =============================================================================

def get_monthly_outbound_total(department_name: str = None) -> int:
    """
    今月の出庫数量合計を取得
    
    Args:
        department_name: 部署名（GUESTの場合のみ指定。NoneならADMIN/USER扱い）
    
    Returns:
        int: 今月の出庫数量合計
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if department_name:
                # GUEST: 自部署タグ + 全社共通のみ
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
                # ADMIN/USER: 全体
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
    """
    在庫不足件数を取得（在庫 <= 発注点）
    
    Args:
        department_name: 部署名（USER/GUESTの場合のみ指定、自部署のみカウント）
    
    Returns:
        int: 在庫不足件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if department_name:
                # USER/GUEST: 自部署のみ
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM inventory inv
                    JOIN items i ON inv.item_id = i.id
                    WHERE inv.quantity <= i.reorder_point
                      AND i.reorder_point IS NOT NULL
                      AND i.department_tags LIKE ?
                """, (f'%{department_name}%',))
            else:
                # ADMIN: 全体
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
    """
    期限切れ件数を取得
    
    Args:
        department_name: 部署名（GUESTの場合のみ指定）
    
    Returns:
        int: 期限切れ件数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if department_name:
                # GUEST: 自部署 + 全社共通
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
                # ADMIN/USER: 全体
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
    """
    出庫量の月別推移データを取得（折れ線グラフ用）
    
    Args:
        item_ids: 物品IDのリスト（最大5件推奨）
        months: 過去何ヶ月分を取得するか（デフォルト6）
        department_name: 部署名（GUESTの場合のみ指定）
    
    Returns:
        list: [{"ym": "YYYY-MM", "item_id": 1, "item_name": "...", "qty": 10}, ...]
    """
    try:
        if not item_ids:
            return []
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            placeholders = ','.join('?' * len(item_ids))
            
            if department_name:
                # GUEST: 自部署 + 全社共通のみ
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
                # ADMIN/USER: 全体
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
    """
    選択した物品のKPIを取得
    
    Args:
        item_ids: 物品IDのリスト
        department_name: 部署名（GUESTの場合のみ指定）
    
    Returns:
        dict: {
            "monthly_out": 今月の出庫数量合計,
            "weekly_out": 直近7日の出庫数量合計,
            "items": [{"item_id": 1, "item_name": "...", "quantity": 100, "threshold": 10}, ...]
        }
    """
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
    """
    今月の出庫量が多い物品TOP Nを取得
    
    Args:
        category: カテゴリフィルタ（Noneまたは「すべて」なら全体）
        keyword: キーワード検索（物品名、品目コード）
        department_name: 部署名（GUESTの場合のみ指定）
        limit: 取得件数（デフォルト10）
    
    Returns:
        list: [{"item_id", "item_name", "item_code", "category", "monthly_out", "quantity", "threshold"}, ...]
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # WHERE条件を構築
            where_clauses = ["ih.change_type = '出庫'"]
            where_clauses.append("strftime('%Y-%m', ih.created_at) = strftime('%Y-%m', 'now')")
            params = []
            
            # カテゴリフィルタ
            if category and category != "すべて":
                where_clauses.append("i.category = ?")
                params.append(category)
            
            # キーワード検索
            if keyword and keyword.strip():
                where_clauses.append("(i.item_name LIKE ? OR i.item_code LIKE ?)")
                keyword_param = f"%{keyword.strip()}%"
                params.extend([keyword_param, keyword_param])
            
            # 部署フィルタ（GUEST）
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


def get_reorder_candidates(department_name: str = None) -> list:
    """
    発注候補を取得（消耗品、在庫<=発注点、直近30日内に出庫あり、推奨発注量>0）

    Args:
        department_name: 部署名（GUESTの場合のみ指定）

    Returns:
        list of dict: {
            item_id, item_name, current_stock, threshold, recent_30_out,
            recommended_qty, unit_price, vendor_name
        }
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 直近30日の出庫合計サブクエリをJOIN
            # 絞り込み: is_asset=0（消耗品）, 在庫 <= 発注点, 直近30日で出庫あり
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

            params = params  # keep order
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_reorder_candidates: {e}")
        return []


def get_reorder_candidates_count(department_name: str = None) -> int:
    """
    発注候補の件数を取得（消耗品、在庫<=発注点、直近30日内に出庫あり）
    
    Args:
        department_name: 部署名（GUESTの場合のみ指定）
    
    Returns:
        int: 発注候補の件数
    """
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


# =============================================================================
# 発注候補管理（purchase_candidates テーブル操作）
# =============================================================================

def sync_purchase_candidates(user_id: int = None) -> dict:
    """
    自動候補を purchase_candidates テーブルに同期（upsert）
    - 発注点割れ + 直近30日OUT > 0 の消耗品を自動抽出
    - 既存の selected/deferred 状態は保持
    - status='OPEN' のみ対象（ORDERED/CLOSED は対象外）
    
    Args:
        user_id: 更新者のユーザーID（任意）
    
    Returns:
        dict: {"success": bool, "added": int, "updated": int, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 現在の自動候補を取得（発注点割れ + 30日OUT > 0）
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
                
                # 在庫ゼロなら priority = urgent
                priority = "urgent" if current_stock == 0 else "normal"
                
                # 既存レコードを確認
                cursor.execute("""
                    SELECT id, status, selected_for_order, deferred 
                    FROM purchase_candidates 
                    WHERE item_id = ?
                """, (item_id,))
                existing = cursor.fetchone()
                
                if existing:
                    # 既存: statusがOPENの場合のみ更新（推奨数量とpriority）
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
                    # 新規追加
                    # 在庫ゼロなら自動で selected_for_order = 1
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
    """
    発注申請（PENDING/APPROVED）を発注候補テーブルに同期
    全部署からのAPPROVED/PENDINGの申請を発注候補に追加
    
    Args:
        user_id: 更新者のユーザーID（任意）
    
    Returns:
        dict: {"success": bool, "added": int, "updated": int, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # APPROVED/PENDINGの申請を取得（最新の申請からnoteも取得）
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
            
            # デバッグ: 取得した申請をログ出力
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
                
                # 申請情報を含むnoteを作成
                combined_note = f"【申請者】{requester_name}（{department}）\n【申請理由】{request_note}" if request_note else f"【申請者】{requester_name}（{department}）"
                
                # 既存候補を確認
                cursor.execute("""
                    SELECT id, status, recommended_qty
                    FROM purchase_candidates
                    WHERE item_id = ?
                """, (item_id,))
                existing = cursor.fetchone()
                
                if existing:
                    # 既存: statusがOPENなら推奨数量とnoteを更新（大きい方を採用）
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
                    # 新規追加（申請からの候補は自動選択）
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
    """
    発注候補一覧を取得
    
    Args:
        status: ステータスフィルタ（OPEN/ORDERED/CLOSED、Noneで全件）
        department_name: 部署フィルタ（GUESTの場合のみ）
    
    Returns:
        list: 候補リスト（物品情報含む）
    """
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
    """
    候補の選択状態を更新
    
    Args:
        candidate_id: 候補ID
        selected: 選択状態（True/False）
        user_id: 更新者のユーザーID
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 選択時は deferred を解除
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
    """
    候補の保留状態を更新
    
    Args:
        candidate_id: 候補ID
        deferred: 保留状態（True/False）
        user_id: 更新者のユーザーID
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 保留時は selected を解除
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
    """
    候補の発注数量を更新（ADMIN専用）
    
    Args:
        candidate_id: 候補ID
        qty: 発注数量
        user_id: 更新者のユーザーID
    
    Returns:
        dict: {"success": bool, "message": str}
    """
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
    """
    候補のメモを更新
    
    Args:
        candidate_id: 候補ID
        note: メモ
        user_id: 更新者のユーザーID
    
    Returns:
        dict: {"success": bool, "message": str}
    """
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
    """
    選択された候補を発注済み(ORDERED)に更新
    候補がfrom_requestの場合、対応する申請もORDEREDに更新
    
    Args:
        candidate_ids: 候補IDリスト
        user_id: 更新者のユーザーID
    
    Returns:
        dict: {"success": bool, "count": int, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if not candidate_ids:
                return {"success": False, "count": 0, "message": "対象がありません"}
            
            # 候補を取得（item_idとauto_reasonが必要）
            placeholders = ",".join(["?" for _ in candidate_ids])
            cursor.execute(f"""
                SELECT id, item_id, auto_reason
                FROM purchase_candidates
                WHERE id IN ({placeholders}) AND status = 'OPEN' AND selected_for_order = 1
            """, candidate_ids)
            candidates = cursor.fetchall()
            
            if not candidates:
                return {"success": False, "count": 0, "message": "対象がありません"}
            
            # 候補をORDEREDに更新
            cursor.execute(f"""
                UPDATE purchase_candidates 
                SET status = 'ORDERED',
                    updated_by_user_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders}) AND status = 'OPEN' AND selected_for_order = 1
            """, [user_id] + candidate_ids)
            
            count = cursor.rowcount
            
            # from_requestの候補については、対応する申請もORDEREDに更新
            request_updated = 0
            for candidate in candidates:
                if candidate['auto_reason'] == 'from_request':
                    item_id = candidate['item_id']
                    # 該当item_idのPENDING/APPROVEDの申請をORDEREDに更新
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
    """
    発注対象（selected_for_order=1, status=OPEN）の候補を取得
    業者別にグループ化された形で返す
    
    Returns:
        list: 選択済み候補リスト
    """
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
    """
    候補のステータス別件数を取得
    
    Returns:
        dict: {"open": int, "selected": int, "deferred": int, "ordered": int}
    """
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
    except Exception as e:
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


# =============================================================================
# 発注申請管理（purchase_requests テーブル操作）
# =============================================================================

def create_purchase_request(
    item_id: int,
    requested_qty: int,
    user_id: int,
    department: str,
    priority: str = "normal",
    due_date: str = None,
    note: str = None
) -> dict:
    """
    発注申請を作成（USER/ADMIN用）
    
    Args:
        item_id: 物品ID
        requested_qty: 希望数量
        user_id: 申請者ユーザーID
        department: 申請者部署
        priority: 優先度（normal/urgent）
        due_date: 希望納期（任意）
        note: 備考（任意）
    
    Returns:
        dict: {"success": bool, "message": str, "id": int}
    """
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
    """
    発注申請一覧を取得
    
    Args:
        status: ステータスフィルタ（PENDING/APPROVED/ON_HOLD/REJECTED/ORDERED）
        requester_id: 申請者IDフィルタ
        department: 部署フィルタ
    
    Returns:
        list: 申請リスト
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            where_clauses = []
            params = []
            
            # 削除済みを除外
            where_clauses.append("pr.deleted_at IS NULL")
            
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
                    pr.id,
                    pr.item_id,
                    i.item_name,
                    i.item_code,
                    i.vendor_name,
                    i.unit_price,
                    IFNULL(inv.quantity, 0) as current_stock,
                    IFNULL(inv.threshold, 0) as threshold,
                    pr.requested_qty,
                    pr.priority,
                    pr.due_date,
                    pr.note,
                    pr.requested_by_user_id,
                    pr.requested_by_department,
                    u.display_name as requester_name,
                    pr.status,
                    pr.admin_comment,
                    pr.approved_by,
                    pr.approved_at,
                    pr.created_at,
                    pr.updated_at
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
    """
    複数のitem_idについて申請中（PENDING/APPROVED/ON_HOLD）かチェック
    
    Args:
        item_ids: チェックするitem_idのリスト
    
    Returns:
        dict: {item_id: True/False}（申請中ならTrue）
    """
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
            
            # 申請中のitem_idをセットに変換
            pending_items = {row['item_id'] for row in rows}
            
            # 全item_idについて結果を返す
            return {item_id: (item_id in pending_items) for item_id in item_ids}
    except Exception as e:
        print(f"Error in check_items_pending_requests: {e}")
        return {item_id: False for item_id in item_ids}


def check_items_ordered_status(item_ids: list) -> dict:
    """
    複数のitem_idについて発注済み（ORDERED/RECEIVED）かチェック
    
    Args:
        item_ids: チェックするitem_idのリスト
    
    Returns:
        dict: {item_id: {'status': 'pending'/'ordered'/'received'/None, 'qty': int}}
    """
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
            
            # item_id毎に最優先のstatusを記録
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
            
            # 全item_idについて結果を返す
            return {item_id: status_map.get(item_id) for item_id in item_ids}
    except Exception as e:
        print(f"Error in check_items_ordered_status: {e}")
        return {item_id: None for item_id in item_ids}


def get_purchase_request_counts() -> dict:
    """
    発注申請のステータス別件数を取得
    
    Returns:
        dict: {"pending": int, "approved": int, "on_hold": int, "rejected": int, "ordered": int}
    """
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
    """
    発注申請を承認
    
    Args:
        request_id: 申請ID
        admin_user_id: 承認者ID
        comment: コメント（任意）
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # まず現在のステータスを確認
            cursor.execute("""
                SELECT status FROM purchase_requests WHERE id = ?
            """, (request_id,))
            result = cursor.fetchone()
            
            if not result:
                return {"success": False, "message": "申請が見つかりません", "error_code": "NOT_FOUND"}
            
            current_status = result[0]
            
            # ORDERED または APPROVED の場合は処理できない
            if current_status == 'ORDERED':
                return {"success": False, "message": "この申請は既に発注済みです", "error_code": "ALREADY_ORDERED", "current_status": current_status}
            elif current_status == 'APPROVED':
                return {"success": False, "message": "この申請は既に承認済みです", "error_code": "ALREADY_APPROVED", "current_status": current_status}
            
            # PENDING, ON_HOLD, REJECTED から承認可能
            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'APPROVED',
                    approved_by = ?,
                    approved_at = ?,
                    admin_comment = ?,
                    updated_at = ?
                WHERE id = ? AND status IN ('PENDING', 'ON_HOLD', 'REJECTED') AND deleted_at IS NULL
            """, (admin_user_id, now_jst, comment, now_jst, request_id))
            
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました", "error_code": "UPDATE_FAILED", "current_status": current_status}
            
            conn.commit()
            return {"success": True, "message": "申請を承認しました"}
    except Exception as e:
        print(f"Error in approve_purchase_request: {e}")
        return {"success": False, "message": str(e), "error_code": "EXCEPTION"}


def hold_purchase_request(request_id: int, admin_user_id: int, comment: str) -> dict:
    """
    発注申請を保留
    
    Args:
        request_id: 申請ID
        admin_user_id: 承認者ID
        comment: 保留理由（必須）
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # まず現在のステータスを確認
            cursor.execute("""
                SELECT status FROM purchase_requests WHERE id = ?
            """, (request_id,))
            result = cursor.fetchone()
            
            if not result:
                return {"success": False, "message": "申請が見つかりません", "error_code": "NOT_FOUND"}
            
            current_status = result[0]
            
            # ORDERED の場合は処理できない
            if current_status == 'ORDERED':
                return {"success": False, "message": "この申請は既に発注済みです", "error_code": "ALREADY_ORDERED", "current_status": current_status}
            
            # PENDING, ON_HOLD, APPROVED, REJECTED から保留可能
            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'ON_HOLD',
                    approved_by = ?,
                    approved_at = ?,
                    admin_comment = ?,
                    updated_at = ?
                WHERE id = ? AND status IN ('PENDING', 'ON_HOLD', 'APPROVED', 'REJECTED') AND deleted_at IS NULL
            """, (admin_user_id, now_jst, comment, now_jst, request_id))
            
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました", "error_code": "UPDATE_FAILED", "current_status": current_status}
            
            conn.commit()
            return {"success": True, "message": "申請を保留にしました"}
    except Exception as e:
        print(f"Error in hold_purchase_request: {e}")
        return {"success": False, "message": str(e), "error_code": "EXCEPTION"}


def reject_purchase_request(request_id: int, admin_user_id: int, comment: str) -> dict:
    """
    発注申請を却下
    
    Args:
        request_id: 申請ID
        admin_user_id: 承認者ID
        comment: 却下理由（必須）
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # まず現在のステータスを確認
            cursor.execute("""
                SELECT status FROM purchase_requests WHERE id = ?
            """, (request_id,))
            result = cursor.fetchone()
            
            if not result:
                return {"success": False, "message": "申請が見つかりません", "error_code": "NOT_FOUND"}
            
            current_status = result[0]
            
            # ORDERED の場合は処理できない
            if current_status == 'ORDERED':
                return {"success": False, "message": "この申請は既に発注済みです", "error_code": "ALREADY_ORDERED", "current_status": current_status}
            
            # PENDING, ON_HOLD, APPROVED, REJECTED から却下可能
            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'REJECTED',
                    approved_by = ?,
                    approved_at = ?,
                    admin_comment = ?,
                    updated_at = ?
                WHERE id = ? AND status IN ('PENDING', 'ON_HOLD', 'APPROVED', 'REJECTED') AND deleted_at IS NULL
            """, (admin_user_id, now_jst, comment, now_jst, request_id))
            
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました", "error_code": "UPDATE_FAILED", "current_status": current_status}
            
            conn.commit()
            return {"success": True, "message": "申請を却下しました"}
    except Exception as e:
        print(f"Error in reject_purchase_request: {e}")
        return {"success": False, "message": str(e), "error_code": "EXCEPTION"}


def reset_purchase_request_to_pending(request_id: int, admin_user_id: int, comment: str = None) -> dict:
    """
    発注申請を承認待ち（PENDING）に戻す
    
    Args:
        request_id: 申請ID
        admin_user_id: 管理者ID
        comment: コメント（任意）
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 現在のステータスを確認
            cursor.execute("""
                SELECT status FROM purchase_requests WHERE id = ?
            """, (request_id,))
            result = cursor.fetchone()
            
            if not result:
                return {"success": False, "message": "申請が見つかりません"}
            
            current_status = result[0]
            
            # ORDEREDの場合は戻せない
            if current_status == 'ORDERED':
                return {"success": False, "message": "発注済みの申請は承認待ちに戻せません", "error_code": "ALREADY_ORDERED"}
            
            # PENDINGに戻す（REJECTED, ON_HOLD, APPROVEDから可能）
            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'PENDING',
                    admin_comment = ?,
                    updated_at = ?
                WHERE id = ? AND status IN ('REJECTED', 'ON_HOLD', 'APPROVED') AND deleted_at IS NULL
            """, (comment, now_jst, request_id))
            
            if cursor.rowcount == 0:
                return {"success": False, "message": "申請の更新に失敗しました（既にPENDINGまたは削除済み）", "error_code": "UPDATE_FAILED"}
            
            conn.commit()
            return {"success": True, "message": "申請を承認待ちに戻しました"}
    except Exception as e:
        print(f"Error in reset_purchase_request_to_pending: {e}")
        return {"success": False, "message": str(e)}


def delete_purchase_request(request_id: int, deleted_by_user_id: int = None) -> dict:
    """
    発注申請を削除（論理削除）
    
    Args:
        request_id: 申請ID
        deleted_by_user_id: 削除者ID
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 現在のステータスを確認
            cursor.execute("""
                SELECT status, deleted_at FROM purchase_requests WHERE id = ?
            """, (request_id,))
            result = cursor.fetchone()
            
            if not result:
                return {"success": False, "message": "申請が見つかりません"}
            
            current_status = result[0]
            deleted_at = result[1]
            
            # 既に削除済みの場合
            if deleted_at:
                return {"success": False, "message": "この申請は既に削除済みです"}
            
            # ORDEREDの場合は削除できない
            if current_status == 'ORDERED':
                return {"success": False, "message": "発注済みの申請は削除できません"}
            
            # 論理削除実行
            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE purchase_requests 
                SET deleted_at = ?,
                    deleted_by = ?,
                    updated_at = ?
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
    """
    発注書作成対象（APPROVED）の申請を取得
    業者別にグループ化された形で返す
    
    Returns:
        list: 承認済み申請リスト
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    pr.id,
                    pr.item_id,
                    i.item_name,
                    i.item_code,
                    i.vendor_name,
                    i.unit_price,
                    pr.requested_qty,
                    pr.priority,
                    pr.due_date,
                    pr.note,
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


def mark_requests_ordered(request_ids: list, admin_user_id: int, order_channel: str = None, document_name: str = None) -> dict:
    """
    承認済み申請を発注済み(ORDERED)に更新し、同時にinventory_historyに発注記録を追加
    
    Args:
        request_ids: 申請IDリスト
        admin_user_id: 更新者ID
        order_channel: 発注方法（email/pdf/excel）
        document_name: 生成されたドキュメント名
    
    Returns:
        dict: {"success": bool, "count": int, "message": str}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if not request_ids:
                return {"success": False, "count": 0, "message": "対象がありません"}
            
            placeholders = ",".join(["?" for _ in request_ids])
            
            now_jst = get_jst_now_str()
            # 1. purchase_requestsを更新
            cursor.execute(f"""
                UPDATE purchase_requests 
                SET status = 'ORDERED',
                    ordered_at = ?,
                    order_channel = ?,
                    generated_document_name = ?,
                    updated_at = ?
                WHERE id IN ({placeholders}) AND status = 'APPROVED' AND deleted_at IS NULL
            """, [now_jst, order_channel, document_name, now_jst] + request_ids)
            
            count = cursor.rowcount
            
            # 2. inventory_historyに発注記録を追加
            # 発注申請の詳細情報を取得
            cursor.execute(f"""
                SELECT 
                    pr.id,
                    pr.item_id,
                    pr.requested_qty,
                    pr.requested_by_department,
                    pr.requested_by_user_id,
                    i.item_name,
                    i.vendor_name,
                    i.unit_price,
                    u.display_name as requester_name
                FROM purchase_requests pr
                LEFT JOIN items i ON pr.item_id = i.id
                LEFT JOIN users u ON pr.requested_by_user_id = u.id
                WHERE pr.id IN ({placeholders})
            """, request_ids)
            
            requests = cursor.fetchall()
            
            # 各申請ごとにinventory_historyに記録
            for req in requests:
                item_id = req['item_id']
                quantity = req['requested_qty']
                unit_price = req['unit_price'] or 0
                total_price = quantity * unit_price
                vendor_name = req['vendor_name']
                department = req['requested_by_department']
                # requester_nameがNoneの場合は'Unknown'を使用
                user_name = req['requester_name'] if req['requester_name'] else 'Unknown'
                
                cursor.execute("""
                    INSERT INTO inventory_history (
                        item_id,
                        change_type,
                        quantity,
                        user_name,
                        department,
                        status,
                        vendor_name,
                        unit_price,
                        total_price,
                        created_by,
                        note,
                        created_at
                    ) VALUES (?, 'ORDER', ?, ?, ?, 'CONFIRMED', ?, ?, ?, ?, ?, ?)
                """, (
                    item_id,
                    quantity,
                    user_name,
                    department,
                    vendor_name,
                    unit_price,
                    total_price,
                    admin_user_id,
                    f"発注確定（{order_channel or '不明'}）",
                    now_jst
                ))
            
            conn.commit()
            return {"success": True, "count": count, "message": f"{count}件を発注済みにし、履歴に記録しました"}
    except Exception as e:
        print(f"Error in mark_requests_ordered: {e}")
        return {"success": False, "count": 0, "message": str(e)}


def get_ordered_purchase_requests(department_name=None) -> list:
    """
    発注済み（ORDERED）で入庫待ちの申請を取得
    
    Args:
        department_name: 部署名（指定時は該当部署のみ）
    
    Returns:
        list: 発注済み申請リスト
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    pr.id,
                    pr.item_id,
                    i.item_name,
                    i.item_code,
                    i.vendor_name,
                    i.unit_price,
                    pr.requested_qty,
                    pr.priority,
                    pr.due_date,
                    pr.note,
                    pr.requested_by_department,
                    pr.ordered_at,
                    pr.order_channel,
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


def receive_purchase_order(request_id: int, received_qty: int, received_note: str, user_id: int) -> dict:
    """
    発注品の入庫処理を実行
    
    Args:
        request_id: 発注申請ID
        received_qty: 入庫数量
        received_note: 入庫メモ
        user_id: 入庫担当者ID
    
    Returns:
        dict: {"success": bool, "message": str, "item_name": str, "new_quantity": int}
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 発注申請の情報取得
            cursor.execute("""
                SELECT 
                    pr.item_id,
                    pr.requested_qty,
                    pr.requested_by_department,
                    i.item_name,
                    i.item_code,
                    inv.quantity as current_stock,
                    i.unit_price,
                    i.vendor_name,
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
            
            # 2. 在庫数を更新
            new_quantity = current_stock + received_qty
            now_jst = get_jst_now_str()
            cursor.execute("""
                UPDATE inventory 
                SET quantity = ?,
                    updated_at = ?
                WHERE item_id = ?
            """, (new_quantity, now_jst, item_id))
            
            # 3. purchase_requestsを更新（RECEIVED状態へ）
            cursor.execute("""
                UPDATE purchase_requests 
                SET status = 'RECEIVED',
                    received_at = ?,
                    received_by = ?,
                    received_qty = ?,
                    received_note = ?,
                    updated_at = ?
                WHERE id = ?
            """, (now_jst, user_id, received_qty, received_note, now_jst, request_id))
            
            # 4. inventory_historyに入庫記録を追加
            total_price = received_qty * unit_price
            note_text = f"発注品入庫（申請ID: {request_id}）"
            if received_note:
                note_text += f" - {received_note}"
            
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id,
                    change_type,
                    quantity,
                    user_name,
                    department,
                    status,
                    vendor_name,
                    unit_price,
                    total_price,
                    created_by,
                    note,
                    created_at
                    ) VALUES (?, 'IN', ?, ?, ?, 'CONFIRMED', ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                received_qty,
                receiver_name or 'Unknown',
                department,
                vendor_name,
                unit_price,
                total_price,
                user_id,
                note_text,
                now_jst
            ))
            
            # 履歴IDを取得
            history_id = cursor.lastrowid
            
            print(f"[DEBUG] receive_purchase_order: history_id={history_id}, new_quantity={new_quantity}")
            
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


# =============================================================================
# データメンテナンス関数
# =============================================================================

def check_history_change_types() -> dict:
    """
    inventory_historyのchange_type分布を確認
    
    Returns:
        dict: {change_type: count}
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT change_type, COUNT(*) as count 
            FROM inventory_history 
            GROUP BY change_type 
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        return {row['change_type']: row['count'] for row in rows}


def backup_inventory_history_to_csv(filepath: str = None) -> str:
    """
    inventory_historyをCSVにバックアップ
    
    Args:
        filepath: バックアップファイルパス（Noneの場合はタイムスタンプ付きファイル名を自動生成）
    
    Returns:
        str: 保存したファイルパス
    """
    import csv
    from datetime import datetime
    
    if filepath is None:
        timestamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
        filepath = f"inventory_history_backup_{timestamp}.csv"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory_history ORDER BY created_at DESC")
        rows = cursor.fetchall()
        
        if not rows:
            raise ValueError("バックアップするデータがありません")
        
        # CSVに書き込み
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        
        print(f"Backup saved to {filepath} ({len(rows)} records)")
        return filepath


def cleanup_history_change_types(dry_run: bool = True) -> dict:
    """
    inventory_historyのchange_typeを整理
    - ORDER: 削除（在庫を動かさない発注記録は不要）
    - INBOUND: INに変換（納品入庫は通常の入庫）
    
    Args:
        dry_run: Trueなら実際の変更は行わず、変更内容のみ返す
    
    Returns:
        dict: {
            'converted': INBOUND→IN変換件数,
            'deleted': ORDER削除件数,
            'total_affected': 合計変更件数
        }
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # ORDERの件数確認
        cursor.execute("SELECT COUNT(*) as count FROM inventory_history WHERE change_type = 'ORDER'")
        order_count = cursor.fetchone()['count']
        
        # INBOUNDの件数確認
        cursor.execute("SELECT COUNT(*) as count FROM inventory_history WHERE change_type = 'INBOUND'")
        inbound_count = cursor.fetchone()['count']
        
        if not dry_run:
            # 実際に変更を実行
            if order_count > 0:
                cursor.execute("DELETE FROM inventory_history WHERE change_type = 'ORDER'")
            
            if inbound_count > 0:
                cursor.execute("UPDATE inventory_history SET change_type = 'IN' WHERE change_type = 'INBOUND'")
            
            conn.commit()
        
        return {
            'converted': inbound_count,
            'deleted': order_count,
            'total_affected': inbound_count + order_count
        }


# =============================================================================
# 棚卸し関数
# =============================================================================

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
            # is_inventory_target=1 かつ is_active=1 の物品を対象
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
            return {"success": True, "message": "✅ 実数を記録しました",
                    "diff_qty": diff_qty}
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
            # 承認済み＆差異ありの記録を取得
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
                # 在庫を更新
                cursor.execute("""
                    UPDATE inventory
                    SET quantity = ?,
                        updated_at = datetime('now', '+09:00')
                    WHERE item_id = ?
                """, (rec["actual_qty"], rec["item_id"]))
                
                # 履歴に記録
                adjust_note = f"[棚卸し調整] セッションID:{session_id} ({rec['system_qty']} → {rec['actual_qty']})"
                cursor.execute("""
                    INSERT INTO inventory_history (
                        item_id, change_type, quantity, 
                        user_name, department, status, note, created_at
                    ) VALUES (?, 'ADJUST', ?, ?, ?, 'CONFIRMED', ?, datetime('now', '+09:00'))
                """, (rec["item_id"], abs(rec["diff_qty"]), user_name, department, adjust_note))
                
                # 記録ステータスを更新
                cursor.execute("""
                    UPDATE stocktake_records SET status = 'APPLIED' WHERE id = ?
                """, (rec["id"],))
                
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
            
            cursor.execute(f"""
                UPDATE stocktake_templates SET {', '.join(updates)} WHERE id = ?
            """, params)
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


if __name__ == "__main__":
    # 直接実行時はテーブル初期化
    print("データベース初期化を開始...")
    init_tables()
    print("完了！")


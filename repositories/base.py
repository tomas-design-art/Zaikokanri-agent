"""
データベース基盤モジュール

接続管理、スキーマ初期化、パスワードハッシュなど
基盤的なDB操作を提供する。

全ドメインリポジトリはここから get_db_connection をインポートする。
"""

import sqlite3
import os
import hashlib
import secrets
import bcrypt
from contextlib import contextmanager
from utils.date_utils import JST, get_jst_now_str  # noqa: F401

__all__ = [
    'get_db_path',
    'get_db_connection',
    'init_tables',
    'drop_all_tables',
    'hash_password',
    'verify_password',
    'get_jst_now_str',
    'JST',
]


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
    stored_hash形式: "salt$hash" or bcrypt hash
    """
    try:
        if isinstance(stored_hash, (bytes, bytearray)):
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        if isinstance(stored_hash, str) and stored_hash.startswith("$2"):
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
        salt, hash_value = stored_hash.split("$")
        new_hash, _ = hash_password(password, salt)
        return new_hash == stored_hash
    except (ValueError, AttributeError, TypeError):
        return False


# =============================================================================
# DB接続管理
# =============================================================================

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
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# =============================================================================
# スキーマ初期化
# =============================================================================

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
                department_tags TEXT,
                unit_price REAL DEFAULT 0,
                is_asset INTEGER DEFAULT 0,
                frequency_tag TEXT,
                expiry_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(vendor_name, vendor_item_code)
            )
        """)

        # 在庫テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 0,
                threshold INTEGER DEFAULT 10,
                location TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                UNIQUE(item_id)
            )
        """)

        # 在庫履歴テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                change_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                department TEXT,
                status TEXT DEFAULT 'CONFIRMED',
                note TEXT,
                vendor_name TEXT,
                unit_price REAL,
                total_price REAL,
                created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)

        # 既存テーブルにカラムを追加（マイグレーション）
        for col in ['vendor_name TEXT', 'unit_price REAL', 'total_price REAL', 'created_by INTEGER']:
            try:
                cursor.execute(f"ALTER TABLE inventory_history ADD COLUMN {col}")
            except Exception:
                pass

        # 検索高速化のためのインデックス
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_name ON items(item_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_code ON items(item_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_vendor ON items(vendor_name, vendor_item_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_item ON inventory_history(item_id, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON inventory_history(status)")

        # 部署マスターテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_departments_name ON departments(name)")

        cursor.execute("SELECT COUNT(*) as count FROM departments")
        if cursor.fetchone()["count"] == 0:
            for dept in ['総務部', '営業部', '経理部', '看護係', '薬剤部', '未設定']:
                cursor.execute("INSERT INTO departments (name) VALUES (?)", (dept,))
            print("✅ デフォルト部署を作成しました")

        # カテゴリマスターテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name)")

        cursor.execute("SELECT COUNT(*) as count FROM categories")
        if cursor.fetchone()["count"] == 0:
            for cat in ['事務用品', '薬品', '医療機器', '消耗品', 'その他']:
                cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
            print("✅ デフォルトカテゴリを作成しました")

        # 業者マスターテーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendors_name ON vendors(vendor_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendors_code ON vendors(vendor_code)")

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

        # ユーザーマスターテーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(user_role)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_department ON users(department)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_department_id ON users(department_id)")

        # 申請テーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_transactions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_department ON pending_transactions(department_id)")

        # 廃棄申請テーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_disposal_status ON disposal_requests(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_disposal_requester ON disposal_requests(requester_id)")

        # 発注申請テーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchase_requests_status ON purchase_requests(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchase_requests_requester ON purchase_requests(requested_by_user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchase_requests_item ON purchase_requests(item_id)")

        # デフォルト管理者ユーザー
        cursor.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()["count"] == 0:
            cursor.execute("SELECT id FROM departments WHERE name = '総務部'")
            dept_row = cursor.fetchone()
            dept_id = dept_row["id"] if dept_row else 1
            admin_hash, _ = hash_password("admin123")
            cursor.execute("""
                INSERT INTO users (username, password_hash, display_name, department, department_id, user_role)
                VALUES ('admin', ?, '管理者', '総務部', ?, 'ADMIN')
            """, (admin_hash, dept_id))
            print("✅ デフォルト管理者ユーザーを作成しました (admin / admin123)")

        # items テーブル マイグレーション
        cursor.execute("PRAGMA table_info(items)")
        columns = [col[1] for col in cursor.fetchall()]
        _add_column_if_missing = lambda col_def: (
            cursor.execute(f"ALTER TABLE items ADD COLUMN {col_def}")
            if col_def.split()[0] not in columns else None
        )
        for col_def in [
            'is_active INTEGER DEFAULT 1',
            'owner_department_id INTEGER',
            'is_common INTEGER DEFAULT 0',
            'location_text TEXT',
            'last_inspection_date TEXT',
            'next_inspection_date TEXT',
            'interval_months INTEGER',
            'reorder_point INTEGER',
            'is_inventory_target INTEGER DEFAULT 1',
        ]:
            try:
                col_name = col_def.split()[0]
                if col_name not in columns:
                    cursor.execute(f"ALTER TABLE items ADD COLUMN {col_def}")
            except Exception:
                pass

        # purchase_requests テーブル マイグレーション
        cursor.execute("PRAGMA table_info(purchase_requests)")
        pr_columns = [col[1] for col in cursor.fetchall()]
        for col_def in ['deleted_at TEXT', 'deleted_by INTEGER']:
            try:
                col_name = col_def.split()[0]
                if col_name not in pr_columns:
                    cursor.execute(f"ALTER TABLE purchase_requests ADD COLUMN {col_def}")
            except Exception:
                pass

        # 発注候補テーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON purchase_candidates(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_selected ON purchase_candidates(selected_for_order)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_item ON purchase_candidates(item_id)")

        # 棚卸しセッションテーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stocktake_sessions_status ON stocktake_sessions(status)")

        # 棚卸し記録テーブル
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stocktake_records_session ON stocktake_records(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stocktake_records_status ON stocktake_records(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stocktake_records_item ON stocktake_records(item_id)")

        # 棚卸しテンプレートテーブル
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

        # 棚卸しテンプレートマッピングテーブル
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

"""発注申請テーブルに入庫関連カラムを追加するマイグレーション"""
import sys
sys.path.append('.')
from db import get_db_connection

def migrate():
    """purchase_requestsテーブルに入庫関連カラムを追加"""
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 既存カラムを確認
        cursor.execute("PRAGMA table_info(purchase_requests)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        print("=" * 80)
        print("【発注申請テーブルのマイグレーション】")
        print("=" * 80)
        print(f"\n現在のカラム: {', '.join(columns)}")
        
        # 入庫済み日時カラムを追加
        if 'received_at' not in columns:
            cursor.execute("""
                ALTER TABLE purchase_requests 
                ADD COLUMN received_at TEXT
            """)
            print("\n✅ received_at カラムを追加しました")
        else:
            print("\n⏭️  received_at カラムは既に存在します")
        
        # 入庫担当者カラムを追加
        if 'received_by' not in columns:
            cursor.execute("""
                ALTER TABLE purchase_requests 
                ADD COLUMN received_by INTEGER
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_purchase_requests_received_by 
                ON purchase_requests(received_by)
            """)
            print("✅ received_by カラムを追加しました")
        else:
            print("⏭️  received_by カラムは既に存在します")
        
        # 入庫数量カラムを追加
        if 'received_qty' not in columns:
            cursor.execute("""
                ALTER TABLE purchase_requests 
                ADD COLUMN received_qty INTEGER
            """)
            print("✅ received_qty カラムを追加しました")
        else:
            print("⏭️  received_qty カラムは既に存在します")
        
        # 入庫メモカラムを追加
        if 'received_note' not in columns:
            cursor.execute("""
                ALTER TABLE purchase_requests 
                ADD COLUMN received_note TEXT
            """)
            print("✅ received_note カラムを追加しました")
        else:
            print("⏭️  received_note カラムは既に存在します")
        
        conn.commit()
        
        print("\n" + "=" * 80)
        print("✅ マイグレーション完了")
        print("=" * 80)
        
        # 更新後のカラムを確認
        cursor.execute("PRAGMA table_info(purchase_requests)")
        new_columns = [row['name'] for row in cursor.fetchall()]
        print(f"\n更新後のカラム: {', '.join(new_columns)}")

if __name__ == "__main__":
    migrate()

"""
purchase_requestsテーブルにdeleted_atとdeleted_byカラムを追加するマイグレーション
"""
import sqlite3

def migrate():
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    
    # 既存カラムを確認
    cursor.execute("PRAGMA table_info(purchase_requests)")
    columns = [row[1] for row in cursor.fetchall()]
    
    print("現在のカラム:", columns)
    
    # deleted_atカラムを追加
    if 'deleted_at' not in columns:
        print("\n✅ deleted_at カラムを追加中...")
        cursor.execute("""
            ALTER TABLE purchase_requests 
            ADD COLUMN deleted_at TEXT DEFAULT NULL
        """)
        print("   deleted_at カラムを追加しました")
    else:
        print("\n⚠️ deleted_at カラムは既に存在します")
    
    # deleted_byカラムを追加
    if 'deleted_by' not in columns:
        print("✅ deleted_by カラムを追加中...")
        cursor.execute("""
            ALTER TABLE purchase_requests 
            ADD COLUMN deleted_by INTEGER DEFAULT NULL
        """)
        print("   deleted_by カラムを追加しました")
    else:
        print("⚠️ deleted_by カラムは既に存在します")
    
    conn.commit()
    
    # 確認
    cursor.execute("PRAGMA table_info(purchase_requests)")
    new_columns = [row[1] for row in cursor.fetchall()]
    
    print("\n更新後のカラム:", new_columns)
    print("\n✅ マイグレーション完了")
    
    conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("purchase_requests テーブル マイグレーション")
    print("=" * 60)
    migrate()

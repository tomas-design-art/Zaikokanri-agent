"""
purchase_requestsテーブルに発注履歴カラムを追加
"""
import sqlite3

def migrate():
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    
    # 既存カラムを確認
    cursor.execute("PRAGMA table_info(purchase_requests)")
    columns = [row[1] for row in cursor.fetchall()]
    
    print("現在のカラム:", columns)
    print()
    
    # ordered_atカラムを追加
    if 'ordered_at' not in columns:
        print("✅ ordered_at カラムを追加中...")
        cursor.execute("""
            ALTER TABLE purchase_requests 
            ADD COLUMN ordered_at TEXT DEFAULT NULL
        """)
        print("   ordered_at カラムを追加しました")
    else:
        print("⚠️ ordered_at カラムは既に存在します")
    
    # order_channelカラムを追加
    if 'order_channel' not in columns:
        print("✅ order_channel カラムを追加中...")
        cursor.execute("""
            ALTER TABLE purchase_requests 
            ADD COLUMN order_channel TEXT DEFAULT NULL
        """)
        print("   order_channel カラムを追加しました")
    else:
        print("⚠️ order_channel カラムは既に存在します")
    
    # generated_document_nameカラムを追加
    if 'generated_document_name' not in columns:
        print("✅ generated_document_name カラムを追加中...")
        cursor.execute("""
            ALTER TABLE purchase_requests 
            ADD COLUMN generated_document_name TEXT DEFAULT NULL
        """)
        print("   generated_document_name カラムを追加しました")
    else:
        print("⚠️ generated_document_name カラムは既に存在します")
    
    conn.commit()
    
    # 確認
    cursor.execute("PRAGMA table_info(purchase_requests)")
    new_columns = [row[1] for row in cursor.fetchall()]
    
    print("\n更新後のカラム:", new_columns)
    print("\n✅ マイグレーション完了")
    
    conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("purchase_requests 発注履歴カラム追加マイグレーション")
    print("=" * 60)
    migrate()

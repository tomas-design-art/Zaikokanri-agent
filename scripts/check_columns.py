import sqlite3

conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

# purchase_requestsテーブルの構造を確認
cursor.execute("PRAGMA table_info(purchase_requests)")
columns_info = cursor.fetchall()

print("=" * 60)
print("purchase_requests テーブルのカラム構造:")
print("=" * 60)
for col in columns_info:
    print(f"{col[1]:20s} {col[2]:15s} NOT NULL={col[3]} DEFAULT={col[4]}")

print("\n" + "=" * 60)
column_names = [row[1] for row in columns_info]
print(f"deleted_at カラム存在: {'deleted_at' in column_names}")
print(f"deleted_by カラム存在: {'deleted_by' in column_names}")
print("=" * 60)

# データ件数確認
cursor.execute("SELECT COUNT(*) FROM purchase_requests")
total_count = cursor.fetchone()[0]
print(f"\n総レコード数: {total_count}")

# deleted_atカラムが存在する場合のみ
if 'deleted_at' in column_names:
    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE deleted_at IS NULL")
    active_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE deleted_at IS NOT NULL")
    deleted_count = cursor.fetchone()[0]
    print(f"有効レコード: {active_count}")
    print(f"削除済み: {deleted_count}")
else:
    print("⚠️ deleted_atカラムが存在しません → マイグレーション未実行")

# ステータス別件数
cursor.execute("SELECT status, COUNT(*) FROM purchase_requests GROUP BY status")
status_counts = cursor.fetchall()
print("\nステータス別件数:")
for status, count in status_counts:
    print(f"  {status}: {count}件")

conn.close()

import sqlite3

conn = sqlite3.connect('purchase_management.db')
cursor = conn.cursor()

# テーブル一覧
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("=== テーブル一覧 ===")
for table in tables:
    print(f"- {table[0]}")

print("\n=== itemsテーブル ===")
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='items'")
result = cursor.fetchone()
if result:
    print(result[0])

print("\n=== purchase_requestsテーブル ===")
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='purchase_requests'")
result = cursor.fetchone()
if result:
    print(result[0])

print("\n=== vendorsテーブル ===")
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='vendors'")
result = cursor.fetchone()
if result:
    print(result[0])

# purchase_requestsの列を確認
print("\n=== purchase_requestsの列 ===")
cursor.execute("PRAGMA table_info(purchase_requests)")
for col in cursor.fetchall():
    print(f"{col[1]} ({col[2]})")

# itemsの列を確認
print("\n=== itemsの列 ===")
cursor.execute("PRAGMA table_info(items)")
for col in cursor.fetchall():
    print(f"{col[1]} ({col[2]})")

conn.close()

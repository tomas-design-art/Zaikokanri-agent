import sqlite3

conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

cursor.execute('SELECT * FROM departments')
print('=== 部署一覧 ===')
for row in cursor.fetchall():
    print(row)

cursor.execute('SELECT * FROM users')
print('\n=== ユーザー一覧 ===')
for row in cursor.fetchall():
    print(row)

cursor.execute('SELECT * FROM vendors')
print('\n=== 業者一覧 ===')
for row in cursor.fetchall():
    print(row)

cursor.execute('SELECT * FROM items')
print('\n=== 物品一覧 ===')
for row in cursor.fetchall():
    print(row[:5])

conn.close()

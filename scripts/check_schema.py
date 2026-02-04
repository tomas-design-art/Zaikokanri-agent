import sqlite3

conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

cursor.execute('PRAGMA table_info(items)')
print('=== items テーブル構造 ===')
for row in cursor.fetchall():
    print(f'{row[0]:2d}. {row[1]:30s} {row[2]:10s} NOT NULL={row[3]==1}')

conn.close()

import sqlite3

conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

# change_type分布を確認
cursor.execute('''
    SELECT change_type, COUNT(*) as count 
    FROM inventory_history 
    GROUP BY change_type 
    ORDER BY count DESC
''')

rows = cursor.fetchall()

print('=' * 50)
print('現在のchange_type分布:')
print('=' * 50)
for row in rows:
    print(f'  {row[0]}: {row[1]}件')

print('=' * 50)
print(f'合計: {sum(r[1] for r in rows)}件')
print('=' * 50)

# ORDER と INBOUND の詳細
cursor.execute("SELECT * FROM inventory_history WHERE change_type IN ('ORDER', 'INBOUND') LIMIT 5")
problematic = cursor.fetchall()
if problematic:
    print('\n⚠️ 問題のあるレコード（最初の5件）:')
    for row in problematic:
        print(f'  ID={row[0]}, change_type={row[1]}, created_at={row[10]}')
else:
    print('\n✅ ORDER / INBOUND のレコードはありません')

conn.close()

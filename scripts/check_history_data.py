"""inventory_historyテーブルのデータ状況を調査"""
from db import get_db_connection

print("=" * 60)
print("inventory_history データ調査")
print("=" * 60)

with get_db_connection() as conn:
    cursor = conn.cursor()
    
    # 1. change_type の値一覧
    print("\n1. change_type の値一覧:")
    cursor.execute("SELECT DISTINCT change_type FROM inventory_history ORDER BY change_type")
    types = cursor.fetchall()
    for row in types:
        print(f"  - {row['change_type']}")
    
    # 2. created_at の範囲
    print("\n2. created_at の範囲:")
    cursor.execute("SELECT MIN(created_at) as min_date, MAX(created_at) as max_date FROM inventory_history")
    dates = cursor.fetchone()
    print(f"  最小: {dates['min_date']}")
    print(f"  最大: {dates['max_date']}")
    
    # 3. 今月のデータ件数（OUT）
    print("\n3. 今月のOUTデータ件数:")
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM inventory_history
        WHERE change_type = 'OUT'
          AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
    """)
    count = cursor.fetchone()
    print(f"  今月のOUT件数: {count['count']}")
    
    # 4. 全OUTデータ件数
    print("\n4. 全OUTデータ件数:")
    cursor.execute("SELECT COUNT(*) as count FROM inventory_history WHERE change_type = 'OUT'")
    total = cursor.fetchone()
    print(f"  全期間のOUT件数: {total['count']}")
    
    # 5. OUT数量の合計（今月）
    print("\n5. 今月のOUT数量合計:")
    cursor.execute("""
        SELECT SUM(ABS(quantity)) as total
        FROM inventory_history
        WHERE change_type = 'OUT'
          AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
    """)
    qty = cursor.fetchone()
    print(f"  今月のOUT数量合計: {qty['total']}")
    
    # 6. 月別OUT集計（直近6ヶ月）
    print("\n6. 月別OUT集計（直近6ヶ月）:")
    cursor.execute("""
        SELECT 
            strftime('%Y-%m', created_at) as ym,
            COUNT(*) as count,
            SUM(ABS(quantity)) as total_qty
        FROM inventory_history
        WHERE change_type = 'OUT'
          AND created_at >= date('now', '-6 months')
        GROUP BY ym
        ORDER BY ym DESC
    """)
    monthly = cursor.fetchall()
    for row in monthly:
        print(f"  {row['ym']}: {row['count']}件, 数量{row['total_qty']}")
    
    # 7. 物品別OUT集計（今月TOP5）
    print("\n7. 今月の物品別OUT集計 TOP5:")
    cursor.execute("""
        SELECT 
            i.item_name,
            i.item_code,
            SUM(ABS(ih.quantity)) as total_qty,
            COUNT(*) as count
        FROM inventory_history ih
        JOIN items i ON ih.item_id = i.id
        WHERE ih.change_type = 'OUT'
          AND strftime('%Y-%m', ih.created_at) = strftime('%Y-%m', 'now')
        GROUP BY ih.item_id, i.item_name, i.item_code
        ORDER BY total_qty DESC
        LIMIT 5
    """)
    top_items = cursor.fetchall()
    if top_items:
        for row in top_items:
            print(f"  {row['item_name']} ({row['item_code']}): 数量{row['total_qty']} ({row['count']}件)")
    else:
        print("  （今月のOUTデータなし）")

print("\n" + "=" * 60)
print("調査完了")
print("=" * 60)

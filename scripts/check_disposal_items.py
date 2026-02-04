"""廃棄申請可能な物品を確認するスクリプト"""
import sys
sys.path.append('.')
from db import get_db_connection

def check_disposal_items():
    """廃棄申請可能な薬品をチェック"""
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        print("=" * 80)
        print("【薬品カテゴリの物品チェック】")
        print("=" * 80)
        
        # 1. 薬品カテゴリの全物品（在庫あり・なし問わず）
        cursor.execute("""
            SELECT i.id, i.item_name, i.item_code, i.category, i.department_tags, 
                   i.is_active, i.is_asset, inv.quantity
            FROM items i
            LEFT JOIN inventory inv ON i.id = inv.item_id
            WHERE i.category = '薬品'
            ORDER BY i.item_name
        """)
        
        all_medicines = cursor.fetchall()
        
        print(f"\n✅ 薬品カテゴリの物品総数: {len(all_medicines)}件")
        
        if not all_medicines:
            print("\n⚠️ 薬品カテゴリの物品が1件も登録されていません！")
            print("\n💡 対処法:")
            print("   1. 物品マスター管理で新規物品を登録")
            print("   2. カテゴリを「薬品」に設定")
            print("   3. 部署タグを設定")
            print("   4. 在庫数を1以上に設定")
            return
        
        print("\n【全薬品リスト】")
        for item in all_medicines:
            item_dict = dict(item)
            print(f"\nID: {item_dict['id']}")
            print(f"  物品名: {item_dict['item_name']}")
            print(f"  品目コード: {item_dict.get('item_code', 'なし')}")
            print(f"  部署タグ: {item_dict.get('department_tags', 'なし')}")
            print(f"  在庫数: {item_dict.get('quantity', 0)}")
            print(f"  有効: {item_dict['is_active']}")
            print(f"  資産: {item_dict['is_asset']}")
        
        # 2. 廃棄申請可能な物品（全条件満たす）
        cursor.execute("""
            SELECT i.id, i.item_name, i.item_code, i.department_tags, inv.quantity
            FROM items i
            JOIN inventory inv ON i.id = inv.item_id
            WHERE i.category = '薬品'
              AND i.is_active = 1
              AND i.is_asset = 0
              AND inv.quantity > 0
            ORDER BY i.item_name
        """)
        
        eligible_items = cursor.fetchall()
        
        print("\n" + "=" * 80)
        print(f"【廃棄申請可能な薬品】: {len(eligible_items)}件")
        print("=" * 80)
        
        if not eligible_items:
            print("\n⚠️ 廃棄申請可能な薬品がありません")
            print("\n💡 確認ポイント:")
            print("   - is_active = 1 （有効化されているか）")
            print("   - is_asset = 0 （資産ではないか）")
            print("   - quantity > 0 （在庫があるか）")
        else:
            for item in eligible_items:
                item_dict = dict(item)
                print(f"\n✅ {item_dict['item_name']}")
                print(f"   ID: {item_dict['id']}")
                print(f"   品目コード: {item_dict.get('item_code', 'なし')}")
                print(f"   部署タグ: {item_dict.get('department_tags', 'なし')}")
                print(f"   在庫数: {item_dict['quantity']}")
        
        # 3. 部署別フィルタリングのテスト
        print("\n" + "=" * 80)
        print("【部署別フィルタリングテスト】")
        print("=" * 80)
        
        # 登録されている部署を取得
        cursor.execute("SELECT name FROM departments WHERE is_active = 1")
        departments = [dict(row)['name'] for row in cursor.fetchall()]
        
        for dept in departments:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM items i
                JOIN inventory inv ON i.id = inv.item_id
                WHERE i.category = '薬品'
                  AND i.is_active = 1
                  AND i.is_asset = 0
                  AND inv.quantity > 0
                  AND i.department_tags LIKE ?
            """, (f'%{dept}%',))
            
            count = cursor.fetchone()['count']
            print(f"\n{dept}: {count}件")
            
            if count > 0:
                cursor.execute("""
                    SELECT i.item_name, i.department_tags
                    FROM items i
                    JOIN inventory inv ON i.id = inv.item_id
                    WHERE i.category = '薬品'
                      AND i.is_active = 1
                      AND i.is_asset = 0
                      AND inv.quantity > 0
                      AND i.department_tags LIKE ?
                    LIMIT 3
                """, (f'%{dept}%',))
                
                items = cursor.fetchall()
                for item in items:
                    item_dict = dict(item)
                    print(f"  - {item_dict['item_name']} (タグ: {item_dict['department_tags']})")

if __name__ == "__main__":
    check_disposal_items()

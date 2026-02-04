"""
部署タグフィルタリング機能のテストスクリプト
"""

import sys
sys.path.insert(0, '.')

from db import get_db_connection, reset_demo_data, insert_demo_data

def test_department_filtering():
    """部署タグフィルタリングのテスト"""
    print("=" * 60)
    print("🔍 部署タグフィルタリング機能テスト")
    print("=" * 60)
    
    # デモデータをリセット＆再投入
    print("\n【準備】デモデータのリセット＆再投入...")
    reset_result = reset_demo_data(keep_users_and_depts=False)
    if not reset_result["success"]:
        print(f"❌ リセット失敗: {reset_result['message']}")
        return False
    print(f"✅ リセット完了")
    
    insert_result = insert_demo_data()
    if not insert_result["success"]:
        print(f"❌ データ投入失敗: {insert_result['message']}")
        return False
    print(f"✅ デモデータ投入完了")
    print(f"   物品: {insert_result['counts']['items']}件")
    
    # テスト1: 全物品の部署タグを確認
    print("\n" + "=" * 60)
    print("【テスト1】全物品の部署タグを確認")
    print("=" * 60)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT item_code, item_name, category, department_tags
            FROM items
            ORDER BY item_code
        """)
        
        all_items = cursor.fetchall()
        print(f"\n全物品数: {len(all_items)}件\n")
        
        for item in all_items:
            tags = item['department_tags'] or "タグなし"
            print(f"  {item['item_code']:6} | {item['item_name']:30} | タグ: {tags}")
    
    # テスト2: 全社共通物品をカウント
    print("\n" + "=" * 60)
    print("【テスト2】全社共通物品をカウント")
    print("=" * 60)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM items
            WHERE (',' || department_tags || ',') LIKE '%,全社,%'
               OR department_tags IS NULL
               OR department_tags = ''
        """)
        
        result = cursor.fetchone()
        print(f"  全社共通物品: {result['count']}件")
    
    # テスト3: 各部署専用物品をカウント
    print("\n" + "=" * 60)
    print("【テスト3】各部署専用物品をカウント")
    print("=" * 60)
    
    departments = ["総務部", "営業部", "開発部", "経理部", "人事部"]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        for dept in departments:
            # 自部署タグ + 全社共通
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM items
                WHERE (',' || department_tags || ',') LIKE ?
                   OR (',' || department_tags || ',') LIKE '%,全社,%'
                   OR department_tags IS NULL
                   OR department_tags = ''
            """, (f'%,{dept},%',))
            
            dept_count = cursor.fetchone()['count']
            
            # 自部署専用（全社共通を除く）
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM items
                WHERE (',' || department_tags || ',') LIKE ?
                  AND (',' || department_tags || ',') NOT LIKE '%,全社,%'
            """, (f'%,{dept},%',))
            
            dept_only = cursor.fetchone()['count']
            
            print(f"  {dept:10} | 見える物品: {dept_count}件 (専用: {dept_only}件)")
    
    # テスト4: 営業部でフィルタリング（実際のSQL）
    print("\n" + "=" * 60)
    print("【テスト4】営業部でフィルタリング（実際のSQL）")
    print("=" * 60)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        dept_name = "営業部"
        
        cursor.execute("""
            SELECT item_code, item_name, department_tags
            FROM items
            WHERE (',' || department_tags || ',') LIKE ?
               OR (',' || department_tags || ',') LIKE '%,全社,%'
               OR department_tags IS NULL
               OR department_tags = ''
            ORDER BY item_code
        """, (f'%,{dept_name},%',))
        
        filtered_items = cursor.fetchall()
        print(f"\n営業部が見える物品: {len(filtered_items)}件\n")
        
        for item in filtered_items:
            tags = item['department_tags'] or "タグなし"
            print(f"  {item['item_code']:6} | {item['item_name']:30} | タグ: {tags}")
    
    # テスト5: 部分一致誤爆のチェック（重要）
    print("\n" + "=" * 60)
    print("【テスト5】部分一致誤爆のチェック")
    print("=" * 60)
    
    print("  仮に「営業」という部署がある場合...")
    print("  「営業部」タグの物品が「営業」で誤爆しないかをチェック")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 誤ったクエリ（単純LIKE）
        cursor.execute("""
            SELECT item_code, item_name, department_tags
            FROM items
            WHERE department_tags LIKE '%営業%'
        """)
        wrong_results = cursor.fetchall()
        
        # 正しいクエリ（区切り込み）
        cursor.execute("""
            SELECT item_code, item_name, department_tags
            FROM items
            WHERE (',' || department_tags || ',') LIKE '%,営業,%'
        """)
        correct_results = cursor.fetchall()
        
        print(f"\n  単純LIKE '%営業%': {len(wrong_results)}件")
        print(f"  区切り込み LIKE '%,営業,%': {len(correct_results)}件")
        
        if len(wrong_results) > len(correct_results):
            print(f"  ✅ 区切り込みにより誤爆を {len(wrong_results) - len(correct_results)}件防止")
        else:
            print(f"  - 誤爆なし")
    
    # テスト6: 出庫可能物品取得（GUESTユーザー想定）
    print("\n" + "=" * 60)
    print("【テスト6】出庫可能物品取得（GUESTユーザー想定）")
    print("=" * 60)
    
    from app import get_all_items_for_outbound
    
    print("\n  営業部GUESTが見える出庫可能物品:")
    items_eigyo = get_all_items_for_outbound(department_name="営業部")
    print(f"    {len(items_eigyo)}件")
    
    print("\n  開発部GUESTが見える出庫可能物品:")
    items_kaihatsu = get_all_items_for_outbound(department_name="開発部")
    print(f"    {len(items_kaihatsu)}件")
    
    print("\n  総務部GUESTが見える出庫可能物品:")
    items_soumu = get_all_items_for_outbound(department_name="総務部")
    print(f"    {len(items_soumu)}件")
    
    print("\n  人事部GUESTが見える出庫可能物品:")
    items_jinji = get_all_items_for_outbound(department_name="人事部")
    print(f"    {len(items_jinji)}件")
    
    # 各部署専用物品の例を表示
    print("\n  【営業部専用物品の例】")
    for item in items_eigyo[:5]:
        if item.get('item_name') and '営業' in str(get_item_tags(item['id'])):
            print(f"    - {item['item_name']}")
    
    print("\n  【開発部専用物品の例】")
    for item in items_kaihatsu[:5]:
        tags = get_item_tags(item['id'])
        if tags and '開発部' in tags and '全社' not in tags:
            print(f"    - {item['item_name']} (タグ: {tags})")
    
    print("\n" + "=" * 60)
    print("✅ 全てのテスト完了")
    print("=" * 60)
    
    return True


def get_item_tags(item_id):
    """物品IDから部署タグを取得"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT department_tags FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        return result['department_tags'] if result else None


if __name__ == "__main__":
    test_department_filtering()

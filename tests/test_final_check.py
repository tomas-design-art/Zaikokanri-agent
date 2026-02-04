"""
最終チェック：GUEST以外（USER/ADMIN）の見え方確認
"""

import sys
sys.path.insert(0, '.')

from app import get_inventory_list, get_total_count, get_all_items_for_outbound
from db import get_db_connection

def test_final_checks():
    """最終チェック実行"""
    print("=" * 70)
    print("🔍 最終チェック：GUEST以外の動作確認")
    print("=" * 70)
    
    # チェック①：NULL/空の扱い
    print("\n" + "=" * 70)
    print("【チェック①】department_tags が NULL/空の扱い")
    print("=" * 70)
    
    # テスト用にNULL/空の物品を一時追加
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 既存のNULL/空タグ物品をカウント
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM items
            WHERE department_tags IS NULL OR department_tags = ''
        """)
        null_count = cursor.fetchone()['count']
        print(f"\n  既存のNULL/空タグ物品: {null_count}件")
        
        # テスト物品を追加（タグなし）
        test_items = [
            ("TEST001", "テスト物品（タグなし）", None),
            ("TEST002", "テスト物品（空文字）", ""),
            ("TEST003", "テスト物品（スペースのみ）", "   "),
        ]
        
        for code, name, tags in test_items:
            cursor.execute("DELETE FROM items WHERE item_code = ?", (code,))
            cursor.execute("""
                INSERT INTO items (item_code, item_name, category, department_tags, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (code, name, "テスト", tags))
            
            item_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO inventory (item_id, quantity, location)
                VALUES (?, 50, '倉庫A')
            """, (item_id,))
        
        conn.commit()
        print(f"  テスト物品を3件追加しました")
    
    # GUESTユーザー（営業部）でフィルタリング
    print("\n  【営業部GUESTでの表示確認】")
    items_guest = get_all_items_for_outbound(department_name="営業部")
    
    # テスト物品が含まれているか確認
    test_codes = ["TEST001", "TEST002", "TEST003"]
    found_in_guest = []
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for code in test_codes:
            cursor.execute("SELECT id FROM items WHERE item_code = ?", (code,))
            result = cursor.fetchone()
            if result:
                item_id = result['id']
                if any(item['id'] == item_id for item in items_guest):
                    found_in_guest.append(code)
    
    print(f"    営業部GUESTが見える全物品: {len(items_guest)}件")
    print(f"    うちテスト物品（NULL/空タグ）: {len(found_in_guest)}件")
    
    if len(found_in_guest) == 3:
        print(f"    ✅ NULL/空タグの物品も全社共通として表示されている")
        for code in found_in_guest:
            print(f"       - {code}")
    else:
        print(f"    ❌ 一部のテスト物品が表示されていない")
        print(f"       表示: {found_in_guest}")
    
    # クリーンアップ
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for code in test_codes:
            cursor.execute("DELETE FROM inventory WHERE item_id IN (SELECT id FROM items WHERE item_code = ?)", (code,))
            cursor.execute("DELETE FROM items WHERE item_code = ?", (code,))
        conn.commit()
    
    print(f"\n  テスト物品をクリーンアップしました")
    
    # チェック②：USER/ADMINの見え方
    print("\n" + "=" * 70)
    print("【チェック②】USER/ADMIN（department_name=None）の動作確認")
    print("=" * 70)
    
    # 全件数を取得（フィルタなし）
    print("\n  【フィルタなし（USER/ADMIN想定）】")
    total_all = get_total_count(department_name=None)
    items_all = get_inventory_list(limit=1000, offset=0, department_name=None)
    
    print(f"    総件数（get_total_count）: {total_all}件")
    print(f"    取得件数（get_inventory_list）: {len(items_all)}件")
    
    if total_all == len(items_all):
        print(f"    ✅ 件数が一致（正常）")
    else:
        print(f"    ⚠️ 件数が不一致")
    
    # GUESTの件数と比較
    print("\n  【営業部GUESTとの比較】")
    total_guest = get_total_count(department_name="営業部")
    items_guest_inv = get_inventory_list(limit=1000, offset=0, department_name="営業部")
    
    print(f"    営業部GUEST総件数: {total_guest}件")
    print(f"    営業部GUEST取得件数: {len(items_guest_inv)}件")
    
    if total_guest == len(items_guest_inv):
        print(f"    ✅ GUEST側も件数一致（正常）")
    else:
        print(f"    ⚠️ GUEST側で件数不一致")
    
    # 差分確認
    diff = total_all - total_guest
    print(f"\n    USER/ADMINとGUESTの差分: {diff}件")
    
    if diff > 0:
        print(f"    ✅ GUESTは制限されている（正常）")
        
        # 制限されている物品を確認
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT item_code, item_name, department_tags
                FROM items
                WHERE NOT (
                    (',' || department_tags || ',') LIKE '%,営業部,%'
                    OR (',' || department_tags || ',') LIKE '%,全社,%'
                    OR department_tags IS NULL
                    OR department_tags = ''
                )
                ORDER BY item_code
                LIMIT 10
            """)
            
            restricted = cursor.fetchall()
            print(f"\n    【営業部GUESTが見えない物品の例】（最大10件）")
            for item in restricted:
                tags = item['department_tags'] or "タグなし"
                print(f"      - {item['item_code']:6} | {item['item_name']:30} | タグ: {tags}")
    else:
        print(f"    ⚠️ GUESTとの差分がない（フィルタが効いていない可能性）")
    
    # チェック③：ページング整合性
    print("\n" + "=" * 70)
    print("【チェック③】ページング整合性確認")
    print("=" * 70)
    
    # 全件を10件ずつページング
    print("\n  【全件を10件ずつページング（USER/ADMIN）】")
    page_size = 10
    page_count = (total_all + page_size - 1) // page_size
    
    all_items_paged = []
    for page in range(page_count):
        offset = page * page_size
        items_page = get_inventory_list(limit=page_size, offset=offset, department_name=None)
        all_items_paged.extend([dict(row) for row in items_page.to_dict('records')])
    
    print(f"    総件数: {total_all}件")
    print(f"    ページ数: {page_count}ページ")
    print(f"    ページングで取得した件数: {len(all_items_paged)}件")
    
    if total_all == len(all_items_paged):
        print(f"    ✅ ページング整合性OK")
    else:
        print(f"    ⚠️ ページングに問題あり（{total_all} != {len(all_items_paged)}）")
    
    # GUESTでも同様にチェック
    print("\n  【営業部GUESTのページング】")
    page_count_guest = (total_guest + page_size - 1) // page_size
    
    all_items_guest_paged = []
    for page in range(page_count_guest):
        offset = page * page_size
        items_page = get_inventory_list(limit=page_size, offset=offset, department_name="営業部")
        all_items_guest_paged.extend([dict(row) for row in items_page.to_dict('records')])
    
    print(f"    総件数: {total_guest}件")
    print(f"    ページ数: {page_count_guest}ページ")
    print(f"    ページングで取得した件数: {len(all_items_guest_paged)}件")
    
    if total_guest == len(all_items_guest_paged):
        print(f"    ✅ GUESTのページング整合性OK")
    else:
        print(f"    ⚠️ GUESTのページングに問題あり（{total_guest} != {len(all_items_guest_paged)}）")
    
    # 最終サマリー
    print("\n" + "=" * 70)
    print("📊 最終チェック結果サマリー")
    print("=" * 70)
    
    results = []
    
    # チェック①
    if len(found_in_guest) == 3:
        results.append(("✅", "NULL/空タグは全社共通として扱われる"))
    else:
        results.append(("❌", "NULL/空タグの扱いに問題あり"))
    
    # チェック②
    if total_all == len(items_all) and diff > 0:
        results.append(("✅", "USER/ADMINは全件表示、GUESTは制限される"))
    else:
        results.append(("❌", "フィルタリングに問題あり"))
    
    # チェック③
    if total_all == len(all_items_paged) and total_guest == len(all_items_guest_paged):
        results.append(("✅", "ページング整合性OK"))
    else:
        results.append(("❌", "ページングに問題あり"))
    
    for status, message in results:
        print(f"  {status} {message}")
    
    print("\n" + "=" * 70)
    
    all_passed = all(status == "✅" for status, _ in results)
    if all_passed:
        print("🎉 全ての最終チェックに合格しました！")
    else:
        print("⚠️ 一部のチェックに問題があります")
    print("=" * 70)


if __name__ == "__main__":
    test_final_checks()

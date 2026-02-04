# -*- coding: utf-8 -*-
"""申請済み表示機能のテスト"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    init_tables,
    get_reorder_candidates,
    check_items_pending_requests,
    create_purchase_request,
    get_all_users
)

def main():
    print("=" * 60)
    print("申請済み表示機能テスト")
    print("=" * 60)
    
    init_tables()
    
    # 発注候補を取得
    candidates = get_reorder_candidates()
    print(f"\n発注候補件数: {len(candidates)}件")
    
    if not candidates:
        print("発注候補がありません")
        return
    
    # 申請状況をチェック
    item_ids = [item['item_id'] for item in candidates[:5]]
    print(f"\nチェック対象item_ids: {item_ids}")
    
    pending_status = check_items_pending_requests(item_ids)
    print(f"申請状況: {pending_status}")
    
    # 表示例
    print("\n発注候補物品（申請済み表示付き）:")
    for idx, item in enumerate(candidates[:5], 1):
        item_id = item['item_id']
        status_text = " 申請済" if pending_status.get(item_id, False) else ""
        print(f"{idx}. {item['item_name']} (在庫: {item['current_stock']}, 発注点: {item['threshold']}){status_text}")
    
    # テスト：新規申請を作成して再チェック
    if candidates:
        test_item = candidates[0]
        users = get_all_users()
        user = next((u for u in users if u['user_role'] == 'USER'), None)
        
        if user:
            print(f"\n[テスト] {test_item['item_name']}の申請を作成...")
            result = create_purchase_request(
                item_id=test_item['item_id'],
                requested_qty=10,
                user_id=user['id'],
                department=user.get('department', '未設定'),
                priority='normal',
                note='テスト申請'
            )
            print(f"結果: {result}")
            
            # 再チェック
            pending_status2 = check_items_pending_requests([test_item['item_id']])
            print(f"再チェック: {pending_status2}")
            
            if pending_status2.get(test_item['item_id']):
                print("✅ 申請済み表示が正しく動作しています")
            else:
                print("❌ 申請済み表示が動作していません")
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)

if __name__ == "__main__":
    main()

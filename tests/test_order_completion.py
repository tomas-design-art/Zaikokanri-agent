# -*- coding: utf-8 -*-
"""発注完了フローのテスト"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    init_tables,
    create_purchase_request,
    sync_requests_to_candidates,
    get_purchase_candidates,
    mark_candidates_ordered,
    get_purchase_requests,
    check_items_ordered_status,
    get_all_users
)

def main():
    print("=" * 60)
    print("発注完了フローテスト")
    print("=" * 60)
    
    init_tables()
    
    # テスト用ユーザー取得
    users = get_all_users()
    admin = next((u for u in users if u['user_role'] == 'ADMIN'), None)
    user = next((u for u in users if u['user_role'] == 'USER'), None)
    
    if not admin or not user:
        print("❌ テスト用ユーザーが見つかりません")
        return
    
    print(f"\nADMIN: {admin['username']} (id={admin['id']})")
    print(f"USER: {user['username']} (id={user['id']})")
    
    # テスト1: USER申請を作成
    print("\n[1] USERで発注申請を作成（item_id=41）...")
    result = create_purchase_request(
        item_id=41,
        requested_qty=15,
        user_id=user['id'],
        department=user.get('department', '未設定'),
        priority='normal',
        note='テスト申請: 在庫切れそう'
    )
    print(f"結果: {result}")
    request_id = result['id']
    
    # テスト2: 申請を発注候補に同期
    print("\n[2] 申請を発注候補に同期（ADMIN実行）...")
    sync_result = sync_requests_to_candidates(admin['id'])
    print(f"結果: {sync_result}")
    
    # テスト3: 候補を取得
    print("\n[3] 発注候補を取得...")
    candidates = get_purchase_candidates(status="OPEN")
    item_41_candidates = [c for c in candidates if c['item_id'] == 41]
    if item_41_candidates:
        candidate = item_41_candidates[0]
        candidate_id = candidate['id']
        print(f"候補ID: {candidate_id}")
        print(f"  - 物品名: {candidate['item_name']}")
        print(f"  - 選択済み: {candidate['selected_for_order']}")
        print(f"  - 理由: {candidate['auto_reason']}")
    
    # テスト4: 申請のステータス確認（発注前）
    print("\n[4] 申請のステータス確認（発注前）...")
    requests = get_purchase_requests()
    item_41_request = [r for r in requests if r['id'] == request_id]
    if item_41_request:
        print(f"申請ステータス: {item_41_request[0]['status']}")
    
    # テスト5: 候補を発注済みに更新
    print("\n[5] 候補を発注済みに更新（ADMIN実行）...")
    if item_41_candidates:
        order_result = mark_candidates_ordered([candidate_id], admin['id'])
        print(f"結果: {order_result}")
    
    # テスト6: 申請のステータス確認（発注後）
    print("\n[6] 申請のステータス確認（発注後）...")
    requests_after = get_purchase_requests()
    item_41_request_after = [r for r in requests_after if r['id'] == request_id]
    if item_41_request_after:
        status = item_41_request_after[0]['status']
        print(f"申請ステータス: {status}")
        if status == 'ORDERED':
            print("✅ 申請が正しくORDEREDに更新されました")
        else:
            print("❌ 申請がORDEREDに更新されていません")
    
    # テスト7: check_items_ordered_status関数のテスト
    print("\n[7] check_items_ordered_status関数のテスト...")
    order_status = check_items_ordered_status([41])
    print(f"item_id=41のステータス: {order_status.get(41)}")
    if order_status.get(41) == 'ordered':
        print("✅ ステータスチェック関数も正常動作")
    
    print("\n" + "=" * 60)
    print("✅ 全テスト完了")
    print("=" * 60)

if __name__ == "__main__":
    main()

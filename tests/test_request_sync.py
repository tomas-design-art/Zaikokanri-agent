# -*- coding: utf-8 -*-
"""発注申請→発注候補 同期テスト"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    init_tables,
    create_purchase_request,
    sync_requests_to_candidates,
    get_purchase_candidates,
    get_all_users
)

def main():
    print("=" * 60)
    print("発注申請→発注候補 同期テスト")
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
    print("\n[1] USERで発注申請を作成（item_id=40）...")
    result = create_purchase_request(
        item_id=40,
        requested_qty=20,
        user_id=user['id'],
        department=user.get('department', '未設定'),
        priority='urgent',
        note='緊急申請テスト'
    )
    print(f"結果: {result}")
    
    # テスト2: 同期前の発注候補を確認
    print("\n[2] 同期前の発注候補を確認...")
    candidates_before = get_purchase_candidates(status="OPEN")
    item_40_before = [c for c in candidates_before if c['item_id'] == 40]
    print(f"item_id=40の候補: {len(item_40_before)}件")
    
    # テスト3: 申請を発注候補に同期
    print("\n[3] 申請を発注候補に同期（ADMIN実行）...")
    sync_result = sync_requests_to_candidates(admin['id'])
    print(f"結果: {sync_result}")
    
    # テスト4: 同期後の発注候補を確認
    print("\n[4] 同期後の発注候補を確認...")
    candidates_after = get_purchase_candidates(status="OPEN")
    item_40_after = [c for c in candidates_after if c['item_id'] == 40]
    print(f"item_id=40の候補: {len(item_40_after)}件")
    
    if item_40_after:
        candidate = item_40_after[0]
        print(f"  - 物品名: {candidate['item_name']}")
        print(f"  - 推奨数量: {candidate['recommended_qty']}")
        print(f"  - 優先度: {candidate['priority']}")
        print(f"  - 選択済み: {candidate['selected_for_order']}")
        print(f"  - 理由: {candidate['auto_reason']}")
    
    # テスト5: 全候補を表示
    print(f"\n[5] 全発注候補（{len(candidates_after)}件）:")
    for idx, c in enumerate(candidates_after, 1):
        selected = "✓" if c['selected_for_order'] else " "
        urgent = "🔴" if c['priority'] == 'urgent' else ""
        print(f"  {idx}. [{selected}] {c['item_name']} (推奨: {c['recommended_qty']}) {urgent}")
    
    print("\n" + "=" * 60)
    if item_40_after and item_40_after[0]['auto_reason'] == 'from_request':
        print("✅ 申請が発注候補に正常に同期されました")
    else:
        print("❌ 同期が失敗しました")
    print("=" * 60)

if __name__ == "__main__":
    main()

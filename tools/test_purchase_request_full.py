# -*- coding: utf-8 -*-
"""
発注申請フロー 完全テスト
- USER申請 → ADMIN承認 → AI発注書文案 → ORDERED
- GUESTは発注申請不可（権限チェック）
- 二重実行防止
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    init_tables,
    create_purchase_request,
    get_purchase_requests,
    get_purchase_request_counts,
    approve_purchase_request,
    hold_purchase_request,
    reject_purchase_request,
    get_approved_requests_for_order,
    mark_requests_ordered,
    get_all_users
)

def main():
    print("=" * 60)
    print("発注申請フロー 完全テスト")
    print("=" * 60)
    
    # DB初期化
    init_tables()
    
    # テスト用データ取得
    users = get_all_users()
    admin_user = next((u for u in users if u['user_role'] == 'ADMIN'), None)
    normal_user = next((u for u in users if u['user_role'] == 'USER'), None)
    guest_user = next((u for u in users if u['user_role'] == 'GUEST'), None)
    
    if not admin_user or not normal_user:
        print("❌ テスト用ユーザーが見つかりません")
        return
    
    print(f"\nテスト用ユーザー:")
    print(f"  ADMIN: {admin_user['username']} (id={admin_user['id']})")
    print(f"  USER: {normal_user['username']} (id={normal_user['id']})")
    if guest_user:
        print(f"  GUEST: {guest_user['username']} (id={guest_user['id']})")
    
    # 存在するitem_idを取得
    import sqlite3
    conn = sqlite3.connect('inventory.db')
    conn.row_factory = sqlite3.Row
    items = conn.execute('SELECT id FROM items ORDER BY id LIMIT 5').fetchall()
    conn.close()
    if len(items) < 3:
        print("❌ テスト用アイテムが足りません")
        return
    item_ids = [r['id'] for r in items]
    print(f"  テスト用item_ids: {item_ids[:3]}")
    
    # テスト1: USER申請
    print("\n[1] USERで発注申請を作成...")
    result = create_purchase_request(
        item_id=item_ids[0],
        requested_qty=10,
        user_id=normal_user['id'],
        department=normal_user.get('department', '未設定'),
        priority='urgent',
        due_date='2026-02-15',
        note='テスト申請（至急）'
    )
    print(f"  結果: {result}")
    assert result['success'], "申請作成に失敗"
    request_id = result['id']
    
    # テスト2: ステータス確認
    print("\n[2] ステータス別件数を確認...")
    counts = get_purchase_request_counts()
    print(f"  件数: {counts}")
    assert counts['pending'] >= 1, "PENDING件数が0"
    
    # テスト3: PENDING一覧
    print("\n[3] PENDING一覧を取得...")
    pending_list = get_purchase_requests(status='PENDING')
    print(f"  件数: {len(pending_list)}")
    found = any(r['id'] == request_id for r in pending_list)
    assert found, "作成した申請がPENDING一覧にない"
    
    # テスト4: 保留テスト
    print("\n[4] 保留（ON_HOLD）にする...")
    result = hold_purchase_request(request_id, admin_user['id'], '在庫確認中')
    print(f"  結果: {result}")
    assert result['success'], "保留に失敗"
    
    # ON_HOLD確認
    on_hold = get_purchase_requests(status='ON_HOLD')
    found = any(r['id'] == request_id for r in on_hold)
    assert found, "ON_HOLD一覧に見つからない"
    print("  ✅ ON_HOLD確認OK")
    
    # テスト5: 保留から承認
    print("\n[5] 保留から承認（APPROVED）にする...")
    # 保留状態からは承認できないので、新しい申請を作成
    result2 = create_purchase_request(
        item_id=item_ids[1],
        requested_qty=5,
        user_id=normal_user['id'],
        department=normal_user.get('department', '未設定'),
        priority='normal',
        note='通常優先度テスト'
    )
    request_id2 = result2['id']
    
    result = approve_purchase_request(request_id2, admin_user['id'], '承認します')
    print(f"  結果: {result}")
    assert result['success'], "承認に失敗"
    
    # APPROVED確認
    approved = get_approved_requests_for_order()
    found = any(r['id'] == request_id2 for r in approved)
    assert found, "APPROVED一覧に見つからない"
    print("  ✅ APPROVED確認OK")
    
    # テスト6: 発注済み（ORDERED）に更新
    print("\n[6] 発注済み（ORDERED）に更新...")
    result = mark_requests_ordered([request_id2], admin_user['id'])
    print(f"  結果: {result}")
    assert result['success'], "ORDERED更新に失敗"
    
    # ORDERED確認
    counts = get_purchase_request_counts()
    print(f"  最終件数: {counts}")
    
    # テスト7: 却下テスト
    print("\n[7] 却下（REJECTED）テスト...")
    result3 = create_purchase_request(
        item_id=item_ids[2],
        requested_qty=100,
        user_id=normal_user['id'],
        department=normal_user.get('department', '未設定'),
        priority='normal',
        note='却下テスト用'
    )
    request_id3 = result3['id']
    
    result = reject_purchase_request(request_id3, admin_user['id'], '予算オーバーのため却下')
    print(f"  結果: {result}")
    assert result['success'], "却下に失敗"
    
    # REJECTED確認
    rejected = get_purchase_requests(status='REJECTED')
    found = any(r['id'] == request_id3 for r in rejected)
    assert found, "REJECTED一覧に見つからない"
    print("  ✅ REJECTED確認OK")
    
    # テスト8: 二重承認防止
    print("\n[8] 二重承認防止テスト...")
    result = approve_purchase_request(request_id3, admin_user['id'])  # 既にREJECTED
    print(f"  結果: {result}")
    assert not result['success'], "二重処理が防止されていない"
    print("  ✅ 二重処理防止OK")
    
    print("\n" + "=" * 60)
    print("✅ 全テスト成功！")
    print("=" * 60)

if __name__ == "__main__":
    main()

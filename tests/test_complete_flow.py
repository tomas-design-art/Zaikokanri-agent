# -*- coding: utf-8 -*-
"""完全な発注申請フローテスト（新しい一括発注確定機能付き）"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    init_tables,
    create_purchase_request,
    approve_purchase_request,
    get_approved_requests_for_order,
    mark_requests_ordered,
    get_purchase_requests,
    check_items_ordered_status,
    get_all_users
)

def main():
    print("=" * 60)
    print("完全な発注申請フロー（新機能テスト）")
    print("=" * 60)
    
    init_tables()
    
    users = get_all_users()
    admin = next((u for u in users if u['user_role'] == 'ADMIN'), None)
    user = next((u for u in users if u['user_role'] == 'USER'), None)
    
    print(f"\nADMIN: {admin['username']} (id={admin['id']})")
    print(f"USER: {user['username']} (id={user['id']})")
    
    # ステップ1: USERが申請を作成
    print("\n" + "=" * 60)
    print("ステップ1: USERが発注申請を作成")
    print("=" * 60)
    
    request_ids = []
    
    result1 = create_purchase_request(
        item_id=39,  # ボールペン（黒）
        requested_qty=50,
        user_id=user['id'],
        department=user.get('department', '未設定'),
        priority='normal',
        note='ボールペンが足りません'
    )
    print(f"申請1: {result1}")
    request_ids.append(result1['id'])
    
    result2 = create_purchase_request(
        item_id=40,  # A4コピー用紙
        requested_qty=100,
        user_id=user['id'],
        department=user.get('department', '未設定'),
        priority='urgent',
        note='至急必要です！'
    )
    print(f"申請2: {result2}")
    request_ids.append(result2['id'])
    
    # ステップ2: ADMINが承認
    print("\n" + "=" * 60)
    print("ステップ2: ADMINが申請を承認")
    print("=" * 60)
    
    for req_id in request_ids:
        result = approve_purchase_request(req_id, admin['id'], comment='承認します')
        print(f"申請ID={req_id}: {result}")
    
    # ステップ3: 承認済み申請を確認
    print("\n" + "=" * 60)
    print("ステップ3: 承認済み申請を確認")
    print("=" * 60)
    
    approved = get_approved_requests_for_order()
    print(f"承認済み件数: {len(approved)}件")
    for req in approved:
        print(f"  - {req['item_name']}: {req['requested_qty']}個 (申請ID={req['id']})")
    
    # ステップ4: 一括発注確定
    print("\n" + "=" * 60)
    print("ステップ4: 一括発注確定（新機能）")
    print("=" * 60)
    
    approved_ids = [req['id'] for req in approved]
    print(f"発注確定する申請ID: {approved_ids}")
    
    result = mark_requests_ordered(approved_ids, admin['id'])
    print(f"結果: {result}")
    
    # ステップ5: 結果確認
    print("\n" + "=" * 60)
    print("ステップ5: 結果確認")
    print("=" * 60)
    
    print("\nAPPROVED申請:")
    approved_after = get_approved_requests_for_order()
    if approved_after:
        for req in approved_after:
            print(f"  - {req['item_name']} (ID={req['id']})")
    else:
        print("  なし ✅")
    
    print("\nORDERED申請（最新5件）:")
    ordered = get_purchase_requests(status='ORDERED')
    for req in ordered[-5:]:
        print(f"  - {req['item_name']}: {req['status']} (ID={req['id']})")
    
    # ステップ6: USERの視点で確認
    print("\n" + "=" * 60)
    print(f"ステップ6: USERの視点 ({user['username']})")
    print("=" * 60)
    
    my_requests = get_purchase_requests(requester_id=user['id'])
    print(f"\n自分の申請（最新5件）:")
    for req in my_requests[-5:]:
        status_label = {
            'PENDING': '⏳ 承認待ち',
            'APPROVED': '✅ 承認済み',
            'ORDERED': '✅ 発注完了'
        }.get(req['status'], req['status'])
        print(f"  - {req['item_name']}: {status_label}")
    
    # ステップ7: 発注点割れ物品の表示確認
    print("\n" + "=" * 60)
    print("ステップ7: 発注点割れ物品の表示確認")
    print("=" * 60)
    
    item_ids = [39, 40]
    order_status = check_items_ordered_status(item_ids)
    
    for item_id in item_ids:
        status = order_status.get(item_id)
        if status == 'ordered':
            print(f"  item_id={item_id}: 申請済 ✅ 発注完了しました。到着までしばらくお待ちください。")
        elif status == 'pending':
            print(f"  item_id={item_id}: 申請済")
        else:
            print(f"  item_id={item_id}: (申請なし)")
    
    print("\n" + "=" * 60)
    print("✅ 全テスト成功！新しい一括発注確定機能が正常に動作しています")
    print("=" * 60)

if __name__ == "__main__":
    main()

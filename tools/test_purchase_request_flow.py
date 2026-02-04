"""
発注申請フロー自動テスト
- 申請作成 → 承認 → 発注書作成対象取得 → 発注済み化
"""
import sys
import pathlib

# プロジェクトルートをパスに追加
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))

from db import (
    init_tables, get_db_connection,
    create_purchase_request, get_purchase_requests, get_purchase_request_counts,
    approve_purchase_request, hold_purchase_request, reject_purchase_request,
    get_approved_requests_for_order, mark_requests_ordered
)


def get_or_create_user():
    """テスト用ユーザーIDを取得"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE user_role = 'ADMIN' LIMIT 1")
        row = cur.fetchone()
        if row:
            return row['id']
        # なければ作成
        cur.execute("""
            INSERT INTO users (username, password_hash, display_name, department, user_role)
            VALUES ('test_admin', 'hash', 'テスト管理者', '未設定', 'ADMIN')
        """)
        return cur.lastrowid


def get_or_create_item():
    """テスト用物品IDを取得"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM items LIMIT 1")
        row = cur.fetchone()
        if row:
            return row['id']
        cur.execute("INSERT INTO items (item_name, category, vendor_name) VALUES (?, ?, ?)",
                    ("テスト物品", "消耗品", "テスト業者"))
        item_id = cur.lastrowid
        cur.execute("INSERT INTO inventory (item_id, quantity, threshold) VALUES (?, ?, ?)",
                    (item_id, 5, 10))
        return item_id


def test_full_flow():
    """フルフローテスト"""
    print("=" * 50)
    print("発注申請フロー 自動テスト")
    print("=" * 50)
    
    # 初期化
    init_tables()
    user_id = get_or_create_user()
    item_id = get_or_create_item()
    
    print(f"\nテスト用 user_id={user_id}, item_id={item_id}")
    
    # 1. 申請作成
    print("\n[1] 発注申請を作成...")
    res = create_purchase_request(
        item_id=item_id,
        requested_qty=10,
        user_id=user_id,
        department="未設定",
        priority="urgent",
        due_date="2026-02-15",
        note="テスト申請"
    )
    print(f"  結果: {res}")
    assert res.get('success'), "申請作成に失敗"
    
    # 2. 件数確認
    print("\n[2] ステータス別件数を確認...")
    counts = get_purchase_request_counts()
    print(f"  件数: {counts}")
    assert counts.get('pending', 0) >= 1, "PENDING件数が0"
    
    # 3. PENDING一覧取得
    print("\n[3] PENDING一覧を取得...")
    pendings = get_purchase_requests(status='PENDING')
    print(f"  件数: {len(pendings)}")
    assert len(pendings) >= 1, "PENDING一覧が空"
    
    req_id = pendings[0]['id']
    print(f"  対象申請ID: {req_id}")
    
    # 4. 承認
    print("\n[4] 申請を承認...")
    approve_res = approve_purchase_request(req_id, admin_user_id=user_id, comment="テスト承認OK")
    print(f"  結果: {approve_res}")
    assert approve_res.get('success'), "承認に失敗"
    
    # 5. 承認済み取得
    print("\n[5] 発注書作成対象（APPROVED）を取得...")
    approved = get_approved_requests_for_order()
    print(f"  件数: {len(approved)}")
    assert len(approved) >= 1, "承認済みが空"
    
    # 6. 発注済みにする
    print("\n[6] 発注済み（ORDERED）に更新...")
    ids = [a['id'] for a in approved]
    order_res = mark_requests_ordered(ids, admin_user_id=user_id)
    print(f"  結果: {order_res}")
    assert order_res.get('success'), "発注済み更新に失敗"
    
    # 7. 最終確認
    print("\n[7] 最終件数を確認...")
    final_counts = get_purchase_request_counts()
    print(f"  件数: {final_counts}")
    
    print("\n" + "=" * 50)
    print("✅ 全テスト成功！")
    print("=" * 50)


if __name__ == '__main__':
    test_full_flow()

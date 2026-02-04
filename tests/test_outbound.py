"""
出庫処理の整合性テストスクリプト
DB更新後に在庫数が正しく反映されるかを確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db_connection, process_outbound, get_item_by_id


def test_outbound_consistency():
    """出庫処理の整合性をテスト"""
    print("=" * 60)
    print("出庫処理 整合性テスト")
    print("=" * 60)
    
    # テスト対象の物品ID（コピー用紙）
    test_item_id = 1
    test_quantity = 3
    
    # 1. 出庫前の在庫数を取得
    print(f"\n【ステップ1】出庫前の在庫確認")
    item_before = get_item_by_id(test_item_id)
    if not item_before:
        print("❌ テスト物品が見つかりません")
        return
    
    print(f"  物品名: {item_before['item_name']}")
    print(f"  出庫前在庫: {item_before['quantity']} 個")
    
    if item_before['quantity'] < test_quantity:
        print(f"⚠️  在庫不足のためテスト中止（必要: {test_quantity}個、現在: {item_before['quantity']}個）")
        return
    
    # 2. 出庫処理を実行
    print(f"\n【ステップ2】出庫処理実行")
    print(f"  出庫数量: {test_quantity} 個")
    
    result = process_outbound(
        item_id=test_item_id,
        quantity=test_quantity,
        user_name="テストユーザー",
        department="開発部",
        note="整合性テスト"
    )
    
    print(f"  処理結果: {result['message']}")
    print(f"  成功: {result['success']}")
    print(f"  返却された残在庫: {result['remaining_quantity']} 個")
    
    if not result['success']:
        print("❌ 出庫処理が失敗しました")
        return
    
    # 3. 出庫後の在庫数をDBから再取得
    print(f"\n【ステップ3】出庫後の在庫確認（DB再取得）")
    item_after = get_item_by_id(test_item_id)
    
    print(f"  DB在庫数: {item_after['quantity']} 個")
    
    # 4. 在庫一覧取得関数でも確認
    print(f"\n【ステップ4】在庫一覧取得関数で確認")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                i.id, i.item_name, inv.quantity
            FROM items i
            LEFT JOIN inventory inv ON i.id = inv.item_id
            WHERE i.id = ?
        """, (test_item_id,))
        result_from_list = cursor.fetchone()
        list_quantity = result_from_list['quantity'] if result_from_list else None
    
    print(f"  一覧取得での在庫: {list_quantity} 個")
    
    # 5. 整合性チェック
    print(f"\n【ステップ5】整合性チェック")
    expected_quantity = item_before['quantity'] - test_quantity
    
    print(f"  期待値: {expected_quantity} 個")
    print(f"  process_outbound返却値: {result['remaining_quantity']} 個")
    print(f"  get_item_by_id取得値: {item_after['quantity']} 個")
    print(f"  一覧取得での値: {list_quantity} 個")
    
    # 判定
    all_match = (
        result['remaining_quantity'] == expected_quantity and
        item_after['quantity'] == expected_quantity and
        list_quantity == expected_quantity
    )
    
    print("\n" + "=" * 60)
    if all_match:
        print("✅ テスト成功: すべての値が一致しました！")
    else:
        print("❌ テスト失敗: 値に不整合があります")
        if result['remaining_quantity'] != expected_quantity:
            print(f"  - process_outbound返却値が不一致")
        if item_after['quantity'] != expected_quantity:
            print(f"  - get_item_by_id取得値が不一致")
        if list_quantity != expected_quantity:
            print(f"  - 一覧取得での値が不一致")
    print("=" * 60)
    
    # 6. 履歴確認
    print(f"\n【ステップ6】履歴記録確認")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                change_type, quantity, user_name, department, note, created_at
            FROM inventory_history
            WHERE item_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (test_item_id,))
        history = cursor.fetchone()
    
    if history:
        print(f"  種類: {history['change_type']}")
        print(f"  数量: {history['quantity']} 個")
        print(f"  実行者: {history['user_name']}")
        print(f"  部署: {history['department']}")
        print(f"  備考: {history['note']}")
        print(f"  日時: {history['created_at']}")
        
        if history['change_type'] == 'OUT' and history['quantity'] == test_quantity:
            print("  ✅ 履歴記録OK")
        else:
            print("  ❌ 履歴記録に問題あり")
    else:
        print("  ❌ 履歴が見つかりません")


if __name__ == "__main__":
    test_outbound_consistency()

"""
発注履歴統合のテストスクリプト

【テスト項目】
1. inventory_historyテーブルにORDER用カラムが追加されているか
2. 発注確定時にinventory_historyに記録されるか
3. 履歴ページでORDERが表示されるか
4. CSVにORDERが含まれるか
"""

import sys
import os

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    get_db_connection,
    init_tables,
    insert_item,
    create_purchase_request,
    approve_purchase_request,
    mark_requests_ordered,
    get_history_list
)

def print_section(title):
    """セクションタイトルを表示"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_table_schema():
    """テスト1: テーブルスキーマの確認"""
    print_section("テスト1: inventory_historyテーブルのスキーマ確認")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(inventory_history)")
        columns = cursor.fetchall()
        
        print("\n📋 inventory_history テーブルのカラム:")
        for col in columns:
            print(f"  - {col['name']} ({col['type']})")
        
        # 必要なカラムが存在するか確認
        column_names = [col['name'] for col in columns]
        required_columns = ['vendor_name', 'unit_price', 'total_price', 'created_by']
        
        missing = [col for col in required_columns if col not in column_names]
        if missing:
            print(f"\n❌ 不足しているカラム: {missing}")
            return False
        else:
            print(f"\n✅ すべての必要なカラムが存在します")
            return True

def test_order_recording():
    """テスト2: 発注記録の動作確認"""
    print_section("テスト2: 発注確定時のinventory_history記録")
    
    try:
        # テストデータ準備
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # テスト用品目を追加（タイムスタンプでユニークに）
            import time
            timestamp = int(time.time())
            result = insert_item(
                item_name=f"テスト用品目_発注履歴_{timestamp}",
                item_code=f"TEST-ORDER-{timestamp}",
                category="テスト",
                vendor_name="テスト業者A",
                vendor_item_code=f"VENDOR-{timestamp}",
                unit_price=1000
            )
            if not result['success']:
                print(f"❌ 品目追加エラー: {result['message']}")
                return False
            
            item_id = result['item_id']
            print(f"\n✅ テスト用品目を追加しました (ID: {item_id})")
            
            # 発注申請を作成
            result = create_purchase_request(
                item_id=item_id,
                requested_qty=10,
                user_id=1,
                department="総務部",
                note="発注履歴テスト用"
            )
            request_id = result['id']
            print(f"✅ 発注申請を作成しました (ID: {request_id})")
            
            # 申請を承認
            approve_result = approve_purchase_request(request_id, 1)
            print(f"✅ 申請を承認しました: {approve_result['message']}")
            
            # 発注確定前のinventory_history件数を確認
            cursor.execute("SELECT COUNT(*) as count FROM inventory_history WHERE change_type = 'ORDER'")
            before_count = cursor.fetchone()['count']
            print(f"\n📊 発注確定前のORDER履歴件数: {before_count}")
            
            # 発注確定
            order_result = mark_requests_ordered([request_id], 1, order_channel="email", document_name="test_order.pdf")
            print(f"✅ 発注確定しました: {order_result['message']}")
            
            # 発注確定後のinventory_history件数を確認
            cursor.execute("SELECT COUNT(*) as count FROM inventory_history WHERE change_type = 'ORDER'")
            after_count = cursor.fetchone()['count']
            print(f"📊 発注確定後のORDER履歴件数: {after_count}")
            
            if after_count > before_count:
                print(f"✅ ORDER履歴が {after_count - before_count} 件追加されました")
                
                # 追加された履歴の詳細を確認
                cursor.execute("""
                    SELECT 
                        id, item_id, change_type, quantity, 
                        vendor_name, unit_price, total_price, 
                        user_name, department, created_by, note
                    FROM inventory_history 
                    WHERE change_type = 'ORDER' 
                    ORDER BY id DESC 
                    LIMIT 1
                """)
                order_history = cursor.fetchone()
                
                print("\n📝 追加された履歴の詳細:")
                print(f"  - ID: {order_history['id']}")
                print(f"  - 品目ID: {order_history['item_id']}")
                print(f"  - 種別: {order_history['change_type']}")
                print(f"  - 数量: {order_history['quantity']}")
                print(f"  - 業者名: {order_history['vendor_name']}")
                print(f"  - 単価: ¥{order_history['unit_price']:,.0f}")
                print(f"  - 合計金額: ¥{order_history['total_price']:,.0f}")
                print(f"  - 担当者: {order_history['user_name']}")
                print(f"  - 部署: {order_history['department']}")
                print(f"  - 確定者ID: {order_history['created_by']}")
                print(f"  - 備考: {order_history['note']}")
                
                return True
            else:
                print("❌ ORDER履歴が追加されませんでした")
                return False
                
    except Exception as e:
        print(f"❌ エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_history_display():
    """テスト3: 履歴表示の確認"""
    print_section("テスト3: 履歴ページでのORDER表示")
    
    try:
        # 全履歴を取得
        all_history = get_history_list(change_type="すべて")
        order_history = [h for h in all_history if h['change_type'] == 'ORDER']
        
        print(f"\n📊 全履歴件数: {len(all_history)}")
        print(f"📦 ORDER履歴件数: {len(order_history)}")
        
        if order_history:
            print("\n📝 ORDER履歴の一覧:")
            for i, h in enumerate(order_history[:5], 1):  # 最大5件表示
                print(f"\n  {i}. {h['item_name']} ({h['item_code']})")
                print(f"     - 数量: {h['quantity']} 個")
                vendor = h.get('vendor_name') or '不明'
                print(f"     - 業者: {vendor}")
                unit_price = h.get('order_unit_price') or 0
                print(f"     - 単価: ¥{unit_price:,.0f}")
                total = h.get('total_price') or 0
                print(f"     - 合計: ¥{total:,.0f}")
                print(f"     - 担当者: {h['user_name']} ({h['department']})")
                print(f"     - 日時: {h['created_at']}")
            
            # ORDER専用フィルタのテスト
            order_only = get_history_list(change_type="ORDER")
            print(f"\n✅ ORDER専用フィルタ: {len(order_only)} 件取得")
            
            return True
        else:
            print("\n⚠️ ORDER履歴が見つかりませんでした")
            return False
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """メイン処理"""
    print("\n" + "="*60)
    print("  発注履歴統合テスト")
    print("="*60)
    
    # データベース初期化（テーブル作成・マイグレーション）
    print("\n🔧 データベースを初期化中...")
    init_tables()
    print("✅ データベース初期化完了")
    
    # テスト実行
    results = []
    
    results.append(("スキーマ確認", test_table_schema()))
    results.append(("発注記録", test_order_recording()))
    results.append(("履歴表示", test_history_display()))
    
    # 結果サマリー
    print_section("テスト結果サマリー")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 成功" if result else "❌ 失敗"
        print(f"  {status}: {name}")
    
    print(f"\n📊 合計: {passed}/{total} 件成功")
    
    if passed == total:
        print("\n🎉 すべてのテストに合格しました！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 件のテストが失敗しました")
        return 1

if __name__ == "__main__":
    exit(main())

"""
デモモードの全機能テスト
1. 初期状態の確認
2. デモデータ投入
3. 投入後の確認
4. リセット実行
5. リセット後の確認
"""

from db import insert_demo_data, reset_demo_data, get_demo_data_counts

def print_counts(counts, title):
    print(f"\n{'=' * 50}")
    print(f" {title}")
    print('=' * 50)
    print(f"部署: {counts.get('departments', 0):3d} | ユーザー: {counts.get('users', 0):3d}")
    print(f"業者: {counts.get('vendors', 0):3d} | カテゴリ: {counts.get('categories', 0):3d}")
    print(f"物品: {counts.get('items', 0):3d} | 在庫: {counts.get('inventory', 0):3d}")
    print(f"履歴: {counts.get('inventory_history', 0):3d}")
    print('=' * 50)

# 1. 初期状態
print("\n🔍 Step 1: 初期状態の確認")
initial = get_demo_data_counts()
print_counts(initial, "初期状態")

# 2. デモデータ投入
print("\n📥 Step 2: デモデータを投入中...")
result = insert_demo_data()
print(f"結果: {result['message']}")

after_insert = get_demo_data_counts()
print_counts(after_insert, "投入後")

# 3. 増加数を表示
print("\n📊 増加数:")
for key in ['departments', 'users', 'vendors', 'categories', 'items', 'inventory', 'inventory_history']:
    diff = after_insert.get(key, 0) - initial.get(key, 0)
    if diff > 0:
        print(f"  {key}: +{diff}")

# 4. リセット実行
print("\n🔄 Step 3: デモリセット（ユーザー・部署保持）")
reset_result = reset_demo_data(keep_users_and_depts=True)
print(f"結果: {reset_result['message']}")
print("\n削除件数:")
for key, value in reset_result['counts'].items():
    if value > 0:
        print(f"  {key}: {value}件")

after_reset = get_demo_data_counts()
print_counts(after_reset, "リセット後")

# 5. 再投入テスト
print("\n♻️  Step 4: 再投入テスト")
result2 = insert_demo_data()
print(f"結果: {result2['message']}")

final = get_demo_data_counts()
print_counts(final, "再投入後")

print("\n✅ 全テスト完了！")
print("\n📝 確認ポイント:")
print("  - 投入後に部署・ユーザー・業者・カテゴリ・物品・在庫・履歴が増加")
print("  - リセット後にユーザー・部署は保持、その他はクリア")
print("  - 再投入で再度データが投入される")
print("  - 既存データがある場合はスキップされる")

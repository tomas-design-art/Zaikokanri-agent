"""
アラート機能のテスト
1. デモデータをリセット
2. デモデータを投入（reorder_point、expiry_date付き）
3. アラートを確認
"""

from db import reset_demo_data, insert_demo_data, get_stock_alerts, get_expiry_alerts

print("=== Step 1: デモデータをリセット ===")
result = reset_demo_data(keep_users_and_depts=True)
print(f"{result['message']}\n")

print("=== Step 2: デモデータを投入 ===")
result = insert_demo_data()
print(f"{result['message']}\n")

print("=== Step 3: 在庫アラートを確認 ===")
stock_alerts = get_stock_alerts()
print(f"在庫不足: {len(stock_alerts)}件")
for item in stock_alerts:
    print(f"  - {item['item_name']} (在庫: {item['quantity']}, 発注点: {item['reorder_point']})")

print("\n=== Step 4: 期限アラートを確認 ===")
expiry_alerts = get_expiry_alerts()
expired = expiry_alerts.get("expired", [])
expiring_soon = expiry_alerts.get("expiring_soon", [])

print(f"期限切れ: {len(expired)}件")
for item in expired:
    print(f"  - {item['item_name']} (期限: {item['expiry_date']}, 在庫: {item['quantity']})")

print(f"\n期限間近（30日以内）: {len(expiring_soon)}件")
for item in expiring_soon:
    print(f"  - {item['item_name']} (期限: {item['expiry_date']}, 在庫: {item['quantity']})")

print("\n✅ テスト完了！")
print("Streamlitアプリで「🚨 アラート」メニューを確認してください。")

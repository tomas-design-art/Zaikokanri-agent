"""
デモリセット機能をテスト
"""

from db import reset_demo_data, get_demo_data_counts

print("=== リセット前の件数 ===")
counts_before = get_demo_data_counts()
for key, value in counts_before.items():
    print(f"{key}: {value}")

print("\n=== デモリセット実行（ユーザー・部署を保持） ===")
result = reset_demo_data(keep_users_and_depts=True)
print(f"結果: {result['message']}")
print("\n削除件数:")
for key, value in result['counts'].items():
    print(f"  {key}: {value}件")

print("\n=== リセット後の件数 ===")
counts_after = get_demo_data_counts()
for key, value in counts_after.items():
    print(f"{key}: {value}")

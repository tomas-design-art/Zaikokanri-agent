"""
デモデータ投入をテスト
"""

from db import insert_demo_data, get_demo_data_counts

print("=== デモデータ投入前の件数 ===")
counts_before = get_demo_data_counts()
for key, value in counts_before.items():
    print(f"{key}: {value}")

print("\n=== デモデータを投入中 ===")
result = insert_demo_data()
print(f"結果: {result['message']}")

print("\n=== デモデータ投入後の件数 ===")
counts_after = get_demo_data_counts()
for key, value in counts_after.items():
    print(f"{key}: {value}")

print("\n=== 増加数 ===")
for key in counts_after:
    diff = counts_after[key] - counts_before.get(key, 0)
    print(f"{key}: +{diff}")

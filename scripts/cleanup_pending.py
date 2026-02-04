# -*- coding: utf-8 -*-
"""PENDING申請をクリーンアップ"""

import sqlite3

conn = sqlite3.connect('inventory.db')
cursor = conn.cursor()

# 全てのPENDING申請をORDEREDに更新
cursor.execute("UPDATE purchase_requests SET status='ORDERED' WHERE status='PENDING'")
count = cursor.rowcount
conn.commit()

print(f"✅ {count}件のPENDING申請をORDEREDに更新しました")

# 確認
requests = cursor.execute("SELECT status, COUNT(*) FROM purchase_requests GROUP BY status").fetchall()
print("\n申請ステータス別件数:")
for r in requests:
    print(f"  {r[0]}: {r[1]}件")

conn.close()

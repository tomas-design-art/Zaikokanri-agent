# -*- coding: utf-8 -*-
"""現在のデータベース状態を確認"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3

conn = sqlite3.connect('inventory.db')
conn.row_factory = sqlite3.Row

print("=" * 60)
print("発注申請（purchase_requests）の状態")
print("=" * 60)

requests = conn.execute("""
    SELECT pr.id, pr.item_id, i.item_name, pr.status, pr.requested_by_user_id, 
           u.display_name, pr.note, pr.created_at
    FROM purchase_requests pr
    LEFT JOIN items i ON pr.item_id = i.id
    LEFT JOIN users u ON pr.requested_by_user_id = u.id
    ORDER BY pr.id DESC
    LIMIT 10
""").fetchall()

for r in requests:
    print(f"\nID={r['id']}: {r['item_name']} ({r['status']})")
    print(f"  申請者: {r['display_name']}")
    print(f"  理由: {r['note'][:50] if r['note'] else 'なし'}")

print("\n" + "=" * 60)
print("発注候補（purchase_candidates）の状態")
print("=" * 60)

candidates = conn.execute("""
    SELECT pc.id, pc.item_id, i.item_name, pc.status, pc.auto_reason, 
           pc.selected_for_order, pc.note
    FROM purchase_candidates pc
    LEFT JOIN items i ON pc.item_id = i.id
    ORDER BY pc.id DESC
    LIMIT 10
""").fetchall()

for c in candidates:
    print(f"\nID={c['id']}: {c['item_name']} ({c['status']})")
    print(f"  理由: {c['auto_reason']}")
    print(f"  選択済み: {c['selected_for_order']}")
    print(f"  note: {c['note'][:50] if c['note'] else 'なし'}")

print("\n" + "=" * 60)
print("ステータス別件数")
print("=" * 60)

request_counts = conn.execute("""
    SELECT status, COUNT(*) as cnt
    FROM purchase_requests
    GROUP BY status
""").fetchall()

print("\n申請ステータス:")
for r in request_counts:
    print(f"  {r['status']}: {r['cnt']}件")

candidate_counts = conn.execute("""
    SELECT status, COUNT(*) as cnt
    FROM purchase_candidates
    GROUP BY status
""").fetchall()

print("\n候補ステータス:")
for c in candidate_counts:
    print(f"  {c['status']}: {c['cnt']}件")

conn.close()

# -*- coding: utf-8 -*-
"""発注候補のnote確認"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_purchase_candidates

candidates = get_purchase_candidates(status='OPEN')
print(f'候補数: {len(candidates)}')

for c in candidates:
    note = c.get('note', '')
    note_preview = note[:80] + '...' if len(note) > 80 else note
    print(f"\n物品: {c['item_name']}")
    print(f"  note: {note_preview if note else '(なし)'}")
    print(f"  auto_reason: {c.get('auto_reason', 'なし')}")

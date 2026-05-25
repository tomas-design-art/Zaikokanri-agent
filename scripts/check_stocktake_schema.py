import sqlite3
conn = sqlite3.connect('inventory.db')
c = conn.cursor()
for t in ['stocktake_sessions','stocktake_records','stocktake_templates','stocktake_template_mappings']:
    c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (t,))
    ok = c.fetchone()[0]
    print(f"{t}: {'OK' if ok else 'MISSING'}")
c.execute("PRAGMA table_info(items)")
cols = [col[1] for col in c.fetchall()]
print(f"is_inventory_target: {'OK' if 'is_inventory_target' in cols else 'MISSING'}")
conn.close()

"""
db.py 分割スクリプト

db/ パッケージディレクトリを作成する。
ファイル内容は別途 create tool で配置する。

使い方: python scripts/create_db_package.py
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PKG = os.path.join(BASE_DIR, "db")

os.makedirs(DB_PKG, exist_ok=True)
print(f"Created: {DB_PKG}")

# 空の __init__.py を作成（後で上書きされる）
init_path = os.path.join(DB_PKG, "__init__.py")
if not os.path.exists(init_path):
    with open(init_path, "w", encoding="utf-8") as f:
        f.write("# db package\n")
    print(f"Created: {init_path}")

print("Done. db/ package directory is ready.")

"""
完全なDB初期化スクリプト
departments/users/vendors/categoriesを含むすべてのテーブルを作成
"""

import sys
from db import init_tables

if __name__ == "__main__":
    print("🔧 データベースを初期化中...")
    init_tables()
    print("✅ 初期化完了！")

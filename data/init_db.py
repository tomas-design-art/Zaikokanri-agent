"""
ダミーデータ投入スクリプト（デモモード用）
実行: python data/init_db.py
"""

import sys
import os

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_tables, drop_all_tables, get_db_connection


def insert_dummy_data():
    """ダミーデータを投入"""
    
    # ダミー物品データ（事務用品・薬品など多様なカテゴリ）
    dummy_items = [
        # 事務用品
        ("コピー用紙 A4", "S-001", "オフィス商事", "CP-A4-5000", "事務用品", "全社", 2500, 0, "高頻度", None),
        ("ボールペン（黒）", "S-002", "文具堂", "BP-BK-10", "事務用品", "全社", 100, 100, "高頻度", None),  # 単価100円
        ("クリアファイル A4", "S-003", "文具堂", "CF-A4-100", "事務用品", "全社", 800, 0, "中頻度", None),
        ("付箋紙（75x75mm）", "S-004", "オフィス商事", "ST-7575-Y", "事務用品", "全社", 300, 0, "高頻度", None),
        ("ホチキス針", "S-005", "文具堂", "ST-NO10", "事務用品", "全社", 150, 0, "中頻度", None),
        
        # 薬品（期限管理あり）
        ("造影剤 イオメロン300", "M-101", "医薬品卸A", "IOM-300-50", "薬品", "放射線科", 8500, 3500, "高頻度", "2026-12-31"),  # 単価3500円（廃棄対象）
        ("造影剤 オムニパーク300", "M-102", "医薬品卸A", "OMP-300-50", "薬品", "放射線科", 9000, 4000, "高頻度", "2026-10-31"),  # 単価4000円（廃棄対象）
        ("消毒用エタノール 500ml", "M-103", "医薬品卸B", "ETH-500", "薬品", "全社", 1200, 5000, "高頻度", "2027-03-31"),  # 単価5000円
        ("滅菌ガーゼ 5x5cm", "M-104", "医薬品卸B", "GZ-55-100", "医療用品", "全社", 800, 0, "中頻度", None),
        ("注射器 5ml（使い捨て）", "M-105", "医薬品卸C", "SYR-5ML-100", "医療用品", "全社", 3500, 0, "高頻度", None),
        
        # 清掃用品
        ("トイレットペーパー", None, "清掃用品店", "TP-12R", "清掃用品", "全社", 1800, 0, "高頻度", None),
        ("ゴミ袋 45L（半透明）", None, "清掃用品店", "GB-45-50", "清掃用品", "全社", 900, 0, "高頻度", None),
        
        # 高額資産（5万円以上）
        ("デスクトップPC（管理用）", "E-001", "PCショップ", "DT-WIN-PRO", "電子機器", "総務部", 120000, 60000, "低頻度", None),  # 単価60000円
        ("レーザープリンタ複合機", "E-002", "OA機器店", "LP-MF-500", "電子機器", "総務部", 250000, 1, "中頻度", None),
    ]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        print("📦 物品マスターを投入中...")
        for item in dummy_items:
            cursor.execute("""
                INSERT OR IGNORE INTO items (
                    item_name, item_code, vendor_name, vendor_item_code,
                    category, department_tags, unit_price, is_asset,
                    frequency_tag, expiry_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, item)
        
        print(f"✅ {len(dummy_items)}件の物品を登録しました")
        
        # 在庫データを投入
        print("📊 在庫データを投入中...")
        cursor.execute("SELECT id, item_name FROM items")
        items = cursor.fetchall()
        
        dummy_inventory = [
            (1, 50, 20, "倉庫A-1"),
            (2, 120, 30, "倉庫A-2"),
            (3, 80, 20, "倉庫A-2"),
            (4, 200, 50, "倉庫A-3"),
            (5, 150, 40, "倉庫A-3"),
            (6, 15, 10, "冷蔵庫B-1"),
            (7, 8, 10, "冷蔵庫B-1"),
            (8, 25, 15, "倉庫C-1"),
            (9, 300, 50, "倉庫C-2"),
            (10, 500, 100, "倉庫C-3"),
            (11, 60, 24, "倉庫D-1"),
            (12, 40, 30, "倉庫D-1"),
            (13, 1, 1, "総務部"),
            (14, 1, 1, "総務部"),
        ]
        
        for inv in dummy_inventory:
            cursor.execute("""
                INSERT OR IGNORE INTO inventory (item_id, quantity, threshold, location)
                VALUES (?, ?, ?, ?)
            """, inv)
        
        print(f"✅ {len(dummy_inventory)}件の在庫データを登録しました")
        
        # 履歴データをいくつか投入
        print("📋 在庫履歴を投入中...")
        dummy_history = [
            (1, "IN", 100, "管理者", "総務部", "CONFIRMED", "初期在庫"),
            (2, "IN", 200, "管理者", "総務部", "CONFIRMED", "初期在庫"),
            (1, "OUT", 50, "田中太郎", "営業部", "CONFIRMED", None),
            (6, "IN", 20, "管理者", "放射線科", "CONFIRMED", "定期発注"),
            (6, "OUT", 5, "佐藤花子", "放射線科", "CONFIRMED", "検査使用"),
            (7, "IN", 10, "管理者", "放射線科", "CONFIRMED", "定期発注"),
            (2, "OUT", 80, "鈴木一郎", "総務部", "PENDING", "仮出庫（ゲスト）"),
        ]
        
        for hist in dummy_history:
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, user_name, 
                    department, status, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, hist)
        
        print(f"✅ {len(dummy_history)}件の履歴データを登録しました")
        
        conn.commit()


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description="在庫管理DB初期化ツール")
    parser.add_argument("--reset", action="store_true", help="既存テーブルを削除してから再作成")
    args = parser.parse_args()
    
    if args.reset:
        print("⚠️  既存テーブルを削除します...")
        drop_all_tables()
    
    print("🔧 テーブルを初期化します...")
    init_tables()
    
    print("\n🌱 ダミーデータを投入します...")
    insert_dummy_data()
    
    print("\n✅ すべての初期化が完了しました！")
    print(f"📁 データベースファイル: {os.getenv('DB_PATH', 'inventory.db')}")


if __name__ == "__main__":
    main()

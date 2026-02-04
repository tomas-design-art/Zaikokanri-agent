"""
本番寄せデモデータ投入スクリプト（医療現場想定）
- 部署10、ユーザー12名（ADMIN×2, USER×7, GUEST×3）
- 業者8社、カテゴリ10、物品60件以上
- 在庫・履歴・発注申請データを含む本番想定データセット
"""

import sys
import sqlite3
from datetime import datetime, timedelta
from db import get_db_connection, init_tables, hash_password

def reset_all_data():
    """全データをリセット（テーブルは残す）"""
    print("🔄 全データをリセット中...")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM inventory_history")
        cursor.execute("DELETE FROM pending_transactions")
        cursor.execute("DELETE FROM disposal_requests")
        cursor.execute("DELETE FROM purchase_requests")
        cursor.execute("DELETE FROM purchase_candidates")
        cursor.execute("DELETE FROM inventory")
        cursor.execute("DELETE FROM items")
        cursor.execute("DELETE FROM categories")
        cursor.execute("DELETE FROM vendors")
        cursor.execute("DELETE FROM users")
        cursor.execute("DELETE FROM departments")
        print("✅ リセット完了")

def insert_departments():
    """部署マスタ（医療現場想定10部署）"""
    print("\n🏢 部署マスタを投入中...")
    departments = [
        "総務部",
        "放射線科",
        "検査科",
        "看護部",
        "薬剤部",
        "専門課",
        "運動課",
        "事務",
        "医局",
        "施設管理"
    ]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for dept in departments:
            cursor.execute("INSERT INTO departments (name, is_active) VALUES (?, 1)", (dept,))
    
    print(f"✅ {len(departments)}部署を投入完了")
    return departments

def insert_users(departments):
    """ユーザーマスタ（12名：ADMIN×2, USER×7, GUEST×3）"""
    print("\n👥 ユーザーマスタを投入中...")
    
    # 部署IDマップを作成
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM departments")
        dept_map = {row["name"]: row["id"] for row in cursor.fetchall()}
    
    users = [
        # ADMIN: 2名
        ("admin", "admin123", "管理者A", "総務部", "ADMIN"),
        ("admin2", "admin123", "管理者B", "事務", "ADMIN"),
        
        # USER: 7名（各部署に配置）
        ("U001", "0000", "放射線太郎", "放射線科", "USER"),
        ("U002", "0000", "検査花子", "検査科", "USER"),
        ("U003", "0000", "看護一郎", "看護部", "USER"),
        ("U004", "0000", "薬剤次郎", "薬剤部", "USER"),
        ("U005", "0000", "専門三郎", "専門課", "USER"),
        ("U006", "0000", "運動四郎", "運動課", "USER"),
        ("U007", "0000", "事務五郎", "事務", "USER"),
        
        # GUEST: 3名（閲覧制限あり）
        ("G001", "0000", "ゲスト放射線", "放射線科", "GUEST"),
        ("G002", "0000", "ゲスト検査", "検査科", "GUEST"),
        ("G003", "0000", "ゲスト看護", "看護部", "GUEST"),
    ]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for username, password, display_name, department, role in users:
            password_hash, _ = hash_password(password)
            dept_id = dept_map.get(department)
            cursor.execute("""
                INSERT INTO users (username, password_hash, display_name, department, department_id, user_role, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (username, password_hash, display_name, department, dept_id, role))
    
    print(f"✅ {len(users)}名のユーザーを投入完了")
    print("   ADMIN: admin/admin123, admin2/admin123")
    print("   USER: U001〜U007（パスワード: 0000）")
    print("   GUEST: G001〜G003（パスワード: 0000）")

def insert_vendors():
    """業者マスタ（8社）"""
    print("\n🏢 業者マスタを投入中...")
    vendors = [
        ("V001", "医薬品卸A社", "東京都千代田区丸の内1-1-1", "03-1111-1111", "sales-a@medical.co.jp"),
        ("V002", "医薬品卸B社", "大阪府大阪市北区梅田2-2-2", "06-2222-2222", "sales-b@medical.co.jp"),
        ("V003", "医療材料C社", "愛知県名古屋市中村区名駅3-3-3", "052-3333-3333", "info@material-c.co.jp"),
        ("V004", "文具・日用品D社", "東京都港区赤坂4-4-4", "03-4444-4444", "order@bungu-d.co.jp"),
        ("V005", "産業用品・工具E社", "神奈川県横浜市西区みなとみらい5-5-5", "045-5555-5555", "sales@tool-e.co.jp"),
        ("V006", "IT機器F社", "東京都渋谷区渋谷6-6-6", "03-6666-6666", "support@it-f.co.jp"),
        ("V007", "洗剤・消毒G社", "大阪府吹田市江坂町7-7-7", "06-7777-7777", "order@clean-g.co.jp"),
        ("V008", "廃棄回収H社", "東京都江東区豊洲8-8-8", "03-8888-8888", "info@haiki-h.co.jp"),
    ]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for vendor in vendors:
            cursor.execute("""
                INSERT INTO vendors (vendor_code, vendor_name, address, phone, email, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, vendor)
    
    print(f"✅ {len(vendors)}業者を投入完了")

def insert_categories():
    """カテゴリマスタ（10カテゴリ）"""
    print("\n🏷️ カテゴリマスタを投入中...")
    categories = [
        "造影剤",
        "医薬品（内服）",
        "医薬品（外用）",
        "医療材料（消耗）",
        "滅菌/ガーゼ",
        "消毒・衛生",
        "日用品",
        "事務用品",
        "IT機器",
        "工具/施設"
    ]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for cat in categories:
            cursor.execute("INSERT INTO categories (name, is_active) VALUES (?, 1)", (cat,))
    
    print(f"✅ {len(categories)}カテゴリを投入完了")

def insert_items():
    """物品マスタ（60件以上）"""
    print("\n📦 物品マスタを投入中...")
    
    # 日付計算
    today = datetime.now()
    expired1 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    expired2 = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    near1 = (today + timedelta(days=15)).strftime("%Y-%m-%d")
    near2 = (today + timedelta(days=30)).strftime("%Y-%m-%d")
    near3 = (today + timedelta(days=45)).strftime("%Y-%m-%d")
    near4 = (today + timedelta(days=60)).strftime("%Y-%m-%d")
    near5 = (today + timedelta(days=75)).strftime("%Y-%m-%d")
    normal = (today + timedelta(days=365)).strftime("%Y-%m-%d")
    
    items = [
        # 造影剤（6件）- 高額、期限あり、放射線科
        ("M-1001", "イオパミロン300", "医薬品卸A社", "A-IOPAMIRO-300", "造影剤", "放射線科", 8500, 0, near1, 10),
        ("M-1002", "オムニパーク350", "医薬品卸A社", "A-OMNIPAQUE-350", "造影剤", "放射線科", 9200, 0, near2, 8),
        ("M-1003", "ガドビスト1.0", "医薬品卸B社", "B-GADOVIST-1.0", "造影剤", "放射線科,医局", 12000, 0, normal, 5),
        ("M-1004", "ウログラフィン76%", "医薬品卸A社", "A-UROGRAFIN-76", "造影剤", "放射線科", 3800, 0, expired1, 0),
        ("M-1005", "イオメロン300", "医薬品卸B社", "B-IOMERON-300", "造影剤", "放射線科", 8800, 0, near3, 12),
        ("M-1006", "バリトゲンHD", "医薬品卸A社", "A-BARITOGEN-HD", "造影剤", "放射線科,検査科", 1200, 0, normal, 15),
        
        # 医薬品（内服）（6件）- 期限あり
        ("M-2001", "ロキソニン錠60mg", "医薬品卸A社", "A-LOXONIN-60", "医薬品（内服）", "薬剤部", 15, 0, normal, 100),
        ("M-2002", "アムロジピン錠5mg", "医薬品卸B社", "B-AMLODIPINE-5", "医薬品（内服）", "薬剤部", 12, 0, normal, 200),
        ("M-2003", "ムコスタ錠100mg", "医薬品卸A社", "A-MUCOSTA-100", "医薬品（内服）", "薬剤部", 28, 0, near4, 50),
        ("M-2004", "セレコックス錠100mg", "医薬品卸B社", "B-CELECOXIB-100", "医薬品（内服）", "薬剤部", 65, 0, normal, 80),
        ("M-2005", "タケキャブ錠20mg", "医薬品卸A社", "A-TAKECAB-20", "医薬品（内服）", "薬剤部", 120, 0, expired2, 0),
        ("M-2006", "リリカカプセル75mg", "医薬品卸B社", "B-LYRICA-75", "医薬品（内服）", "薬剤部", 85, 0, normal, 60),
        
        # 医薬品（外用）（6件）
        ("M-3001", "ヒルドイドソフト0.3%", "医薬品卸A社", "A-HIRUDOID-SOFT", "医薬品（外用）", "薬剤部,看護部", 180, 0, normal, 30),
        ("M-3002", "アズノール軟膏0.033%", "医薬品卸B社", "B-AZNOL-OINT", "医薬品（外用）", "薬剤部", 95, 0, near5, 20),
        ("M-3003", "リンデロンVG軟膏", "医薬品卸A社", "A-RINDERON-VG", "医薬品（外用）", "薬剤部", 210, 0, normal, 25),
        ("M-3004", "ゲンタシン軟膏0.1%", "医薬品卸B社", "B-GENTACIN-OINT", "医薬品（外用）", "薬剤部,看護部", 125, 0, normal, 40),
        ("M-3005", "ロコイド軟膏0.1%", "医薬品卸A社", "A-LOCOID-OINT", "医薬品（外用）", "薬剤部", 160, 0, normal, 15),
        ("M-3006", "ヒルドイドローション0.3%", "医薬品卸B社", "B-HIRUDOID-LOTION", "医薬品（外用）", "薬剤部", 190, 0, normal, 20),
        
        # 医療材料（消耗）（8件）
        ("N-3001", "ディスポ注射器5ml", "医療材料C社", "C-SYRINGE-5ML", "医療材料（消耗）", "", 18, 0, None, 200),
        ("N-3002", "ディスポ注射器10ml", "医療材料C社", "C-SYRINGE-10ML", "医療材料（消耗）", "", 22, 0, None, 150),
        ("N-3003", "採血管（EDTA）", "医療材料C社", "C-VACUTAINER-EDTA", "医療材料（消耗）", "検査科", 35, 0, None, 300),
        ("N-3004", "採血管（凝固系）", "医療材料C社", "C-VACUTAINER-COAG", "医療材料（消耗）", "検査科", 38, 0, None, 250),
        ("N-3005", "留置針22G", "医療材料C社", "C-IV-CATHETER-22G", "医療材料（消耗）", "看護部", 85, 0, None, 100),
        ("N-3006", "留置針24G", "医療材料C社", "C-IV-CATHETER-24G", "医療材料（消耗）", "看護部", 82, 0, None, 100),
        ("N-3007", "点滴セット（成人用）", "医療材料C社", "C-DRIP-SET-ADULT", "医療材料（消耗）", "看護部", 45, 0, None, 150),
        ("N-3008", "サーフロー留置針20G", "医療材料C社", "C-SURFLO-20G", "医療材料（消耗）", "看護部", 90, 0, None, 80),
        
        # 滅菌/ガーゼ（6件）- 期限あり
        ("S-4001", "滅菌ガーゼ 7.5×7.5cm", "医療材料C社", "C-GAUZE-75X75", "滅菌/ガーゼ", "", 120, 0, normal, 100),
        ("S-4002", "滅菌ガーゼ 10×10cm", "医療材料C社", "C-GAUZE-100X100", "滅菌/ガーゼ", "", 150, 0, normal, 80),
        ("S-4003", "滅菌綿棒10本入", "医療材料C社", "C-SWAB-STERILE-10", "滅菌/ガーゼ", "看護部,検査科", 85, 0, normal, 50),
        ("S-4004", "滅菌手袋7.0", "医療材料C社", "C-GLOVE-STERILE-70", "滅菌/ガーゼ", "看護部", 180, 0, normal, 40),
        ("S-4005", "滅菌手袋7.5", "医療材料C社", "C-GLOVE-STERILE-75", "滅菌/ガーゼ", "看護部", 180, 0, normal, 40),
        ("S-4006", "滅菌ドレープ 75×90cm", "医療材料C社", "C-DRAPE-75X90", "滅菌/ガーゼ", "看護部", 350, 0, normal, 20),
        
        # 消毒・衛生（6件）
        ("H-5001", "イソジン液10% 500ml", "洗剤・消毒G社", "G-ISODINE-500", "消毒・衛生", "", 680, 0, None, 15),
        ("H-5002", "消毒用エタノール500ml", "洗剤・消毒G社", "G-ETHANOL-500", "消毒・衛生", "", 420, 0, None, 20),
        ("H-5003", "次亜塩素酸ナトリウム 1L", "洗剤・消毒G社", "G-HYPOCHLORITE-1L", "消毒・衛生", "施設管理", 580, 0, None, 10),
        ("H-5004", "手指消毒液ポンプ式500ml", "洗剤・消毒G社", "G-HANDRUB-500", "消毒・衛生", "", 850, 0, None, 30),
        ("H-5005", "クレゾール石鹸液500ml", "洗剤・消毒G社", "G-CRESOL-500", "消毒・衛生", "施設管理", 320, 0, None, 8),
        ("H-5006", "ハイター1000ml", "洗剤・消毒G社", "G-HAITER-1000", "消毒・衛生", "", 280, 0, None, 12),
        
        # 日用品（6件）
        ("D-6001", "ティッシュペーパー200組×5箱", "文具・日用品D社", "D-TISSUE-5BOX", "日用品", "", 380, 0, None, 20),
        ("D-6002", "トイレットペーパー12ロール", "文具・日用品D社", "D-TOILET-12R", "日用品", "", 580, 0, None, 30),
        ("D-6003", "ペーパータオル200枚", "文具・日用品D社", "D-PAPER-TOWEL-200", "日用品", "", 220, 0, None, 40),
        ("D-6004", "ゴミ袋45L 半透明50枚", "文具・日用品D社", "D-GARBAG-45L-50", "日用品", "", 680, 0, None, 15),
        ("D-6005", "ラップ30cm×50m", "文具・日用品D社", "D-WRAP-30X50", "日用品", "", 320, 0, None, 10),
        ("D-6006", "キッチンペーパー2ロール", "文具・日用品D社", "D-KITCHEN-2R", "日用品", "", 280, 0, None, 12),
        
        # 事務用品（6件）
        ("O-7001", "コピー用紙A4 2500枚", "文具・日用品D社", "D-COPY-A4-2500", "事務用品", "事務,総務部", 2800, 0, None, 5),
        ("O-7002", "ボールペン（黒）10本", "文具・日用品D社", "D-PEN-BLACK-10", "事務用品", "", 580, 0, None, 8),
        ("O-7003", "クリアファイル A4 10枚", "文具・日用品D社", "D-CLEARFILE-A4-10", "事務用品", "", 350, 0, None, 10),
        ("O-7004", "付箋紙75×75mm 5色", "文具・日用品D社", "D-STICKY-75X75-5C", "事務用品", "", 480, 0, None, 15),
        ("O-7005", "ホッチキス針 No.10 5箱", "文具・日用品D社", "D-STAPLE-10-5BOX", "事務用品", "", 280, 0, None, 10),
        ("O-7006", "クリップ大中小ミックス", "文具・日用品D社", "D-CLIP-MIX", "事務用品", "", 180, 0, None, 15),
        
        # IT機器（6件）- 資産扱い
        ("P-8001", "ノートPC i5/8GB/256GB", "IT機器F社", "F-LAPTOP-I5-8G", "IT機器", "事務,総務部", 98000, 1, None, 0),
        ("P-8002", "液晶モニタ 24インチ", "IT機器F社", "F-MONITOR-24", "IT機器", "事務", 28000, 0, None, 0),
        ("P-8003", "レーザープリンタA4", "IT機器F社", "F-PRINTER-A4", "IT機器", "事務,総務部", 45000, 0, None, 0),
        ("P-8004", "無線LANルーター", "IT機器F社", "F-ROUTER-WIFI", "IT機器", "総務部", 12800, 0, None, 1),
        ("P-8005", "外付けHDD 2TB", "IT機器F社", "F-HDD-2TB", "IT機器", "", 9800, 0, None, 2),
        ("P-8006", "Webカメラ Full HD", "IT機器F社", "F-WEBCAM-FHD", "IT機器", "", 8500, 0, None, 3),
        
        # 工具/施設（6件）
        ("T-9001", "ドライバーセット", "産業用品・工具E社", "E-SCREWDRIVER-SET", "工具/施設", "施設管理", 2800, 0, None, 2),
        ("T-9002", "電動ドリル", "産業用品・工具E社", "E-DRILL-ELECTRIC", "工具/施設", "施設管理", 18500, 0, None, 1),
        ("T-9003", "脚立 3段", "産業用品・工具E社", "E-LADDER-3STEP", "工具/施設", "施設管理", 8900, 0, None, 2),
        ("T-9004", "工具箱", "産業用品・工具E社", "E-TOOLBOX", "工具/施設", "施設管理", 3500, 0, None, 3),
        ("T-9005", "LED作業灯", "産業用品・工具E社", "E-WORKLIGHT-LED", "工具/施設", "施設管理", 4800, 0, None, 2),
        ("T-9006", "延長コード10m", "産業用品・工具E社", "E-EXTENSION-10M", "工具/施設", "施設管理", 1800, 0, None, 5),
    ]
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for item_code, item_name, vendor, vendor_code, category, dept_tags, price, is_asset, expiry, reorder in items:
            cursor.execute("""
                INSERT INTO items (
                    item_code, item_name, vendor_name, vendor_item_code, 
                    category, department_tags, unit_price, is_asset, 
                    expiry_date, reorder_point, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (item_code, item_name, vendor, vendor_code, category, dept_tags, price, is_asset, expiry, reorder))
    
    print(f"✅ {len(items)}件の物品を投入完了")

def insert_inventory():
    """在庫データ（発注点割れ10件、在庫ゼロ3件を含む）"""
    print("\n📊 在庫データを投入中...")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, item_code, reorder_point FROM items ORDER BY id")
        items = cursor.fetchall()
        
        # 在庫ゼロにするitem_id（最初の3件）
        zero_stock_ids = [items[0]["id"], items[1]["id"], items[2]["id"]]
        
        # 発注点割れにするitem_id（4〜13件目）
        low_stock_ids = [items[i]["id"] for i in range(3, 13) if i < len(items)]
        
        for item in items:
            item_id = item["id"]
            reorder_point = item["reorder_point"] or 10
            
            if item_id in zero_stock_ids:
                quantity = 0
            elif item_id in low_stock_ids:
                # 発注点の半分以下
                quantity = max(1, reorder_point // 2)
            else:
                # 通常在庫（発注点の2〜5倍）
                import random
                quantity = reorder_point * random.randint(2, 5)
            
            cursor.execute("""
                INSERT INTO inventory (item_id, quantity, threshold, location)
                VALUES (?, ?, ?, '倉庫A')
            """, (item_id, quantity, reorder_point))
    
    print(f"✅ 在庫データ投入完了（ゼロ在庫3件、発注点割れ10件を含む）")

def insert_history():
    """履歴データ（過去90日分のOUT中心、IN/DISPOSE少量）"""
    print("\n📝 履歴データを投入中...")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 部署と物品の対応を取得
        cursor.execute("""
            SELECT i.id, i.item_name, i.category, i.department_tags
            FROM items i
            ORDER BY i.id
        """)
        items = cursor.fetchall()
        
        # 過去90日分の履歴を作成
        import random
        history_count = 0
        
        for days_ago in range(90, 0, -1):
            date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            
            # 1日あたり5〜15件のOUT
            for _ in range(random.randint(5, 15)):
                item = random.choice(items)
                item_id = item["id"]
                category = item["category"]
                dept_tags = item["department_tags"] or ""
                
                # カテゴリに応じた部署を選定
                if "造影剤" in category or "放射線" in dept_tags:
                    department = "放射線科"
                    user_name = "放射線太郎"
                elif "検査" in dept_tags or "採血" in item["item_name"]:
                    department = "検査科"
                    user_name = "検査花子"
                elif "看護" in dept_tags or "滅菌" in category:
                    department = "看護部"
                    user_name = "看護一郎"
                elif "薬剤" in dept_tags or "医薬品" in category:
                    department = "薬剤部"
                    user_name = "薬剤次郎"
                else:
                    department = "総務部"
                    user_name = "事務五郎"
                
                quantity = random.randint(1, 10)
                
                cursor.execute("""
                    INSERT INTO inventory_history (
                        item_id, change_type, quantity, user_name, department,
                        status, note, created_at
                    )
                    VALUES (?, 'OUT', ?, ?, ?, 'CONFIRMED', '通常使用', ?)
                """, (item_id, quantity, user_name, department, date))
                history_count += 1
        
        # 少量のIN（10件程度）
        for _ in range(10):
            item = random.choice(items)
            days_ago = random.randint(1, 60)
            date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            quantity = random.randint(50, 200)
            
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, user_name, department,
                    status, note, created_at
                )
                VALUES (?, 'IN', ?, '管理者A', '総務部', 'CONFIRMED', '入庫処理', ?)
            """, (item["id"], quantity, date))
            history_count += 1
        
        # 少量のDISPOSE（5件：期限切れ廃棄）
        cursor.execute("SELECT id FROM items WHERE expiry_date < date('now') LIMIT 2")
        expired_items = cursor.fetchall()
        for item in expired_items:
            days_ago = random.randint(1, 30)
            date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            quantity = random.randint(5, 20)
            
            cursor.execute("""
                INSERT INTO inventory_history (
                    item_id, change_type, quantity, user_name, department,
                    status, note, created_at
                )
                VALUES (?, 'DISPOSE', ?, '管理者A', '総務部', 'CONFIRMED', '期限切れ廃棄', ?)
            """, (item["id"], quantity, date))
            history_count += 1
    
    print(f"✅ {history_count}件の履歴を投入完了（OUT中心 + IN/DISPOSE少量）")

def insert_purchase_requests():
    """発注申請データ（PENDING 6件、APPROVED 4件、HOLD 2件、REJECT 1件）"""
    print("\n✅ 発注申請データを投入中...")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # ユーザーID取得
        cursor.execute("SELECT id, username FROM users WHERE user_role IN ('USER', 'ADMIN')")
        users = cursor.fetchall()
        user_map = {u["username"]: u["id"] for u in users}
        
        cursor.execute("SELECT id FROM users WHERE username='admin' LIMIT 1")
        admin_id = cursor.fetchone()["id"]
        
        # 物品ID取得（在庫少ないものを優先）
        cursor.execute("""
            SELECT i.id, i.item_name, inv.quantity, i.reorder_point
            FROM items i
            JOIN inventory inv ON i.id = inv.item_id
            WHERE inv.quantity <= i.reorder_point
            ORDER BY inv.quantity
            LIMIT 15
        """)
        low_stock_items = cursor.fetchall()
        
        if len(low_stock_items) < 13:
            print("⚠️ 在庫不足物品が足りないため、通常物品も含めます")
            cursor.execute("SELECT id, item_name FROM items LIMIT 20")
            all_items = cursor.fetchall()
            low_stock_items.extend(all_items)
        
        # PENDING: 6件
        for i in range(6):
            item = low_stock_items[i]
            user_id = user_map.get("U001")  # 放射線太郎
            created_at = (datetime.now() - timedelta(days=i+1)).strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
                INSERT INTO purchase_requests (
                    item_id, requested_qty, priority, note,
                    requested_by_user_id, requested_by_department,
                    status, created_at
                )
                VALUES (?, ?, 'normal', '在庫不足のため申請', ?, '放射線科', 'PENDING', ?)
            """, (item["id"], 50, user_id, created_at))
        
        # APPROVED: 4件
        for i in range(6, 10):
            if i >= len(low_stock_items):
                break
            item = low_stock_items[i]
            user_id = user_map.get("U002")  # 検査花子
            created_at = (datetime.now() - timedelta(days=i+5)).strftime("%Y-%m-%d %H:%M:%S")
            approved_at = (datetime.now() - timedelta(days=i+3)).strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
                INSERT INTO purchase_requests (
                    item_id, requested_qty, priority, note,
                    requested_by_user_id, requested_by_department,
                    status, admin_comment, approved_by, approved_at, created_at
                )
                VALUES (?, ?, 'high', '緊急補充', ?, '検査科', 'APPROVED', '承認します', ?, ?, ?)
            """, (item["id"], 100, user_id, admin_id, approved_at, created_at))
        
        # HOLD: 2件
        for i in range(10, 12):
            if i >= len(low_stock_items):
                break
            item = low_stock_items[i]
            user_id = user_map.get("U003")  # 看護一郎
            created_at = (datetime.now() - timedelta(days=i+2)).strftime("%Y-%m-%d %H:%M:%S")
            approved_at = (datetime.now() - timedelta(days=i+1)).strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
                INSERT INTO purchase_requests (
                    item_id, requested_qty, priority, note,
                    requested_by_user_id, requested_by_department,
                    status, admin_comment, approved_by, approved_at, created_at
                )
                VALUES (?, ?, 'normal', '定期補充', ?, '看護部', 'HOLD', '予算確認中', ?, ?, ?)
            """, (item["id"], 50, user_id, admin_id, approved_at, created_at))
        
        # REJECT: 1件
        if len(low_stock_items) >= 13:
            item = low_stock_items[12]
            user_id = user_map.get("U004")  # 薬剤次郎
            created_at = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
            approved_at = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
                INSERT INTO purchase_requests (
                    item_id, requested_qty, priority, note,
                    requested_by_user_id, requested_by_department,
                    status, admin_comment, approved_by, approved_at, created_at
                )
                VALUES (?, ?, 'low', '予備在庫', ?, '薬剤部', 'REJECT', '在庫十分のため却下', ?, ?, ?)
            """, (item["id"], 30, user_id, admin_id, approved_at, created_at))
    
    print("✅ 発注申請データ投入完了（PENDING 6件、APPROVED 4件、HOLD 2件、REJECT 1件）")

def main():
    """メイン処理"""
    print("=" * 70)
    print("  医療現場の本番寄せデモデータ投入")
    print("=" * 70)
    
    # テーブル初期化
    init_tables()
    
    # 全データリセット
    reset_all_data()
    
    # マスタ投入
    departments = insert_departments()
    insert_users(departments)
    insert_vendors()
    insert_categories()
    
    # トランザクションデータ投入
    insert_items()
    insert_inventory()
    insert_history()
    insert_purchase_requests()
    
    print("\n" + "=" * 70)
    print("✅ 本番寄せデモデータ投入完了！")
    print("=" * 70)
    print("\n【投入データサマリ】")
    print("  - 部署: 10")
    print("  - ユーザー: 12名（ADMIN×2, USER×7, GUEST×3）")
    print("  - 業者: 8社")
    print("  - カテゴリ: 10")
    print("  - 物品: 62件（期限切れ2件、期限間近5件含む）")
    print("  - 在庫: 全物品（ゼロ在庫3件、発注点割れ10件含む）")
    print("  - 履歴: 約700件（過去90日分のOUT中心）")
    print("  - 発注申請: 13件（PENDING 6, APPROVED 4, HOLD 2, REJECT 1）")
    print("\n【テストアカウント】")
    print("  ADMIN: admin/admin123, admin2/admin123")
    print("  USER:  U001〜U007 / パスワード: 0000")
    print("  GUEST: G001〜G003 / パスワード: 0000")
    print("=" * 70)

if __name__ == "__main__":
    main()

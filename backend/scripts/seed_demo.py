"""
デモデータ投入スクリプト（医療現場想定）

使い方:
    cd backend
    python scripts/seed_demo.py

既存データがある場合は --force オプションでリセット:
    python scripts/seed_demo.py --force
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

# backend/ を sys.path に追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.hashing import hash_password  # noqa: E402
from app.db import SessionLocal, engine, Base  # noqa: E402
from app.models import (  # noqa: E402
    Category, Department, Inventory, InventoryHistory,
    Item, User, Vendor,
)
from app.utils.datetime import jst_now  # noqa: E402

# デモ・E2E 用の共通パスワード（アプリのパスワード規則＝8文字以上に合わせる）
DEMO_PASSWORD = "pass1234"


def reset(db):
    print("🔄 既存データをリセット中...")
    for tbl in [
        "inventory_history", "pending_transactions", "disposal_notices", "disposal_requests",
        "purchase_requests", "purchase_candidates",
        "stocktake_records", "stocktake_sessions",
        "inventory", "items", "users",
        "vendors", "categories", "departments",
    ]:
        try:
            db.execute(__import__("sqlalchemy").text(f"DELETE FROM {tbl}"))
        except Exception:
            pass
    db.commit()
    print("✅ リセット完了")


def seed(force: bool = False, reset_users: bool = False):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if force:
            reset(db)
        elif db.query(Item).count() > 0:
            print("ℹ️  既にデータが存在します。--force で上書きできます。")
            return

        # ── 部署 ──────────────────────────────────────────────
        print("\n🏢 部署を投入中...")
        dept_names = ["総務部", "放射線科", "検査科", "看護部", "薬剤部",
                      "専門課", "運動課", "事務", "医局", "施設管理"]
        depts = {}
        for name in dept_names:
            d = db.query(Department).filter_by(name=name).first()
            if not d:
                d = Department(name=name)
                db.add(d)
                db.flush()
            depts[name] = d
        db.commit()
        print(f"  ✅ {len(depts)} 部署")

        # ── カテゴリ ───────────────────────────────────────────
        print("📂 カテゴリを投入中...")
        cat_names = ["消耗品", "医療材料", "事務用品", "薬品",
                     "IT機器", "洗剤・消毒薬", "工具・産業用品", "廃棄物", "備品", "その他"]
        cats = {}
        for name in cat_names:
            c = db.query(Category).filter_by(name=name).first()
            if not c:
                c = Category(name=name)
                db.add(c)
                db.flush()
            cats[name] = c
        db.commit()
        print(f"  ✅ {len(cats)} カテゴリ")

        # ── 業者 ───────────────────────────────────────────────
        print("🏭 業者を投入中...")
        vendor_data = [
            ("V001", "医薬品卸A社", "東京都千代田区丸の内1-1-1", "03-1111-1111", "sales-a@medical.co.jp"),
            ("V002", "医薬品卸B社", "大阪府大阪市北区梅田2-2-2", "06-2222-2222", "sales-b@medical.co.jp"),
            ("V003", "医療材料C社", "愛知県名古屋市中村区名駅3-3-3", "052-3333-3333", "info@material-c.co.jp"),
            ("V004", "文具・日用品D社", "東京都港区赤坂4-4-4", "03-4444-4444", "order@bungu-d.co.jp"),
            ("V005", "産業用品E社", "神奈川県横浜市西区みなとみらい5-5-5", "045-5555-5555", "sales@tool-e.co.jp"),
            ("V006", "IT機器F社", "東京都渋谷区渋谷6-6-6", "03-6666-6666", "support@it-f.co.jp"),
            ("V007", "洗剤・消毒G社", "大阪府吹田市江坂町7-7-7", "06-7777-7777", "order@clean-g.co.jp"),
            ("V008", "廃棄回収H社", "東京都江東区豊洲8-8-8", "03-8888-8888", "info@haiki-h.co.jp"),
        ]
        vendors = {}
        for code, name, addr, phone, email in vendor_data:
            v = db.query(Vendor).filter_by(vendor_code=code).first()
            if not v:
                v = Vendor(vendor_code=code, vendor_name=name, address=addr, phone=phone, email=email)
                db.add(v)
                db.flush()
            vendors[code] = v
        db.commit()
        print(f"  ✅ {len(vendors)} 業者")

        # ── ユーザー ───────────────────────────────────────────
        print("👥 ユーザーを投入中...")
        user_data = [
            # (username, password, display_name, dept_name, role)
            ("admin",  "admin123",  "管理者A",      "総務部",   "ADMIN"),
            ("admin2", "admin123",  "管理者B",      "事務",     "ADMIN"),
            ("U001",   DEMO_PASSWORD,      "放射線太郎",   "放射線科", "USER"),
            ("U002",   DEMO_PASSWORD,      "検査花子",     "検査科",   "USER"),
            ("U003",   DEMO_PASSWORD,      "看護一郎",     "看護部",   "USER"),
            ("U004",   DEMO_PASSWORD,      "薬剤次郎",     "薬剤部",   "USER"),
            ("U005",   DEMO_PASSWORD,      "専門三郎",     "専門課",   "USER"),
            ("U006",   DEMO_PASSWORD,      "運動四郎",     "運動課",   "USER"),
            ("U007",   DEMO_PASSWORD,      "事務五郎",     "事務",     "USER"),
            ("G001",   DEMO_PASSWORD,      "ゲスト放射線", "放射線科", "GUEST"),
            ("G002",   DEMO_PASSWORD,      "ゲスト検査",   "検査科",   "GUEST"),
            ("G003",   DEMO_PASSWORD,      "ゲスト看護",   "看護部",   "GUEST"),
        ]
        for uname, pwd, disp, dept_name, role in user_data:
            existing = db.query(User).filter_by(username=uname).first()
            if existing:
                if not reset_users:  # 既存ユーザーのパスワードは勝手に変えない（H-09）
                    continue
                # E2E のとき：マイグレーションで作られた初期管理者もデモ用の内容にそろえる
                existing.password_hash = hash_password(pwd)
                existing.must_change_password = 0
                existing.display_name = disp
                existing.department = dept_name
                existing.department_id = depts[dept_name].id
                continue
            d = depts[dept_name]
            u = User(
                username=uname,
                password_hash=hash_password(pwd),
                display_name=disp,
                department=dept_name,
                department_id=d.id,
                user_role=role,
                must_change_password=0,
            )
            db.add(u)
        db.commit()
        print(f"  ✅ {len(user_data)} ユーザー")
        print("  ADMIN: admin/admin123, admin2/admin123")
        print(f"  USER : U001〜U007  (パスワード: {DEMO_PASSWORD})")
        print(f"  GUEST: G001〜G003  (パスワード: {DEMO_PASSWORD})")

        # ── 物品・在庫 ─────────────────────────────────────────
        print("\n📦 物品・在庫を投入中...")
        now = jst_now()
        items_data = [
            # (item_name, item_code, vendor_code, category, unit_price, qty, threshold)
            ("ディスポ手袋（S）",    "G001", "V003", "消耗品",    200,  80, 20),
            ("ディスポ手袋（M）",    "G002", "V003", "消耗品",    200,  60, 20),
            ("ディスポ手袋（L）",    "G003", "V003", "消耗品",    200,  40, 20),
            ("マスク（サージカル）", "M001", "V003", "消耗品",    150, 120, 30),
            ("アルコール綿",         "A001", "V007", "消耗品",    300,  90, 20),
            ("消毒用エタノール 500mL","E001", "V007", "洗剤・消毒薬", 800,  15,  5),
            ("生理食塩水 500mL",     "S001", "V001", "医療材料", 1200,  30, 10),
            ("輸液セット",           "I001", "V003", "医療材料",  450,  50, 15),
            ("注射針 18G",           "N001", "V003", "医療材料",  120, 200, 50),
            ("注射針 21G",           "N002", "V003", "医療材料",  120, 180, 50),
            ("シリンジ 5mL",         "SY01", "V003", "医療材料",   90, 150, 30),
            ("シリンジ 10mL",        "SY02", "V003", "医療材料",   95, 100, 30),
            ("ガーゼ（10cm×10cm）", "GA01", "V003", "消耗品",    180, 200, 50),
            ("包帯 5cm幅",           "BA01", "V003", "消耗品",    250,  60, 20),
            ("体温計（電子）",       "TM01", "V003", "備品",     3800,   8,  3),
            ("血圧計（手動）",       "BP01", "V003", "備品",    15000,   3,  1),
            ("パルスオキシメーター", "PO01", "V006", "備品",    12000,   5,  2),
            ("コピー用紙 A4 500枚",  "P001", "V004", "事務用品",  550,  20,  5),
            ("コピー用紙 B5 500枚",  "P002", "V004", "事務用品",  500,  10,  3),
            ("ボールペン（黒）10本", "BP10", "V004", "事務用品",  300,  15,  5),
            ("クリアファイル 10枚",  "CF01", "V004", "事務用品",  200,  12,  5),
            ("除菌スプレー 400mL",   "DS01", "V007", "洗剤・消毒薬", 600,  20,  5),
            ("中性洗剤 1L",          "NL01", "V007", "洗剤・消毒薬", 450,  12,  4),
            ("感染性廃棄物容器 5L",  "WB01", "V008", "廃棄物",   1200,   8,  3),
            ("X線フィルム",          "XF01", "V003", "医療材料", 5000,  30, 10),
            ("造影剤（ヨード系）",   "CX01", "V001", "薬品",    8000,  10,  5),
            ("生化学試薬セット",     "BC01", "V002", "薬品",    25000,   5,  2),
            ("血液凝固検査試薬",     "CG01", "V002", "薬品",    18000,   4,  2),
            ("タブレット端末",       "TB01", "V006", "IT機器",  80000,   4,  2),
            ("プリントカートリッジ黒","PC01", "V006", "IT機器",  4500,   3,  2),
        ]

        units = {"消耗品": "箱", "医療材料": "本", "事務用品": "冊", "洗剤・消毒薬": "本", "備品": "台",
                 "薬品": "本", "IT機器": "台", "廃棄物": "個"}
        locations = {"消耗品": "倉庫A-1", "医療材料": "倉庫A-2", "事務用品": "事務室棚", "洗剤・消毒薬": "倉庫B-1",
                     "備品": "倉庫B-2", "薬品": "薬品庫", "IT機器": "事務室棚", "廃棄物": "倉庫B-3"}
        # 部署だけで使う物品（I-01）。ほかは全社共通
        owner_by_code = {"XF01": "放射線科", "CX01": "放射線科", "BC01": "検査科", "CG01": "検査科"}
        created_items = []
        for name, code, vcode, cat, price, qty, thresh in items_data:
            v = vendors[vcode]
            it = db.query(Item).filter_by(item_code=code).first()
            if not it:
                it = Item(
                    item_name=name,
                    item_code=code,
                    vendor_name=v.vendor_name,
                    category=cat,
                    unit_price=float(price),
                    unit=units.get(cat, "個"),
                    location_text=locations.get(cat),
                    reorder_point=thresh,
                    owner_department_id=depts[owner_by_code[code]].id if code in owner_by_code else None,
                    is_common=0 if code in owner_by_code else 1,
                    is_active=1,
                )
                db.add(it)
                db.flush()
            inv = db.query(Inventory).filter_by(item_id=it.id).first()
            if not inv:
                db.add(Inventory(item_id=it.id, quantity=qty, threshold=thresh))
            created_items.append((it, qty))
        db.commit()
        print(f"  ✅ {len(items_data)} 物品・在庫")

        # ── 履歴サンプル ────────────────────────────────────────
        print("📋 入庫・出庫履歴を投入中...")
        admin_user = db.query(User).filter_by(username="admin").first()
        history_count = 0
        for i, (it, qty) in enumerate(created_items[:10]):
            # 入庫1件
            db.add(InventoryHistory(
                item_id=it.id,
                change_type="IN",
                quantity=qty,
                user_name=admin_user.display_name,
                created_by=admin_user.id,
                department=admin_user.department,
                department_id=admin_user.department_id,
                note="初期在庫投入",
                status="CONFIRMED",
                created_at=now - timedelta(days=30 - i),
            ))
            # 出庫1件
            out = max(1, qty // 5)
            db.add(InventoryHistory(
                item_id=it.id,
                change_type="OUT",
                quantity=out,
                user_name=admin_user.display_name,
                created_by=admin_user.id,
                department=admin_user.department,
                department_id=admin_user.department_id,
                note="通常使用",
                status="CONFIRMED",
                created_at=now - timedelta(days=15 - i),
            ))
            history_count += 2
        db.commit()
        print(f"  ✅ {history_count} 件の履歴")

        print("\n🎉 デモデータ投入完了！")
        print("=" * 40)
        print(f"  部署: {len(depts)} 件")
        print(f"  カテゴリ: {len(cats)} 件")
        print(f"  業者: {len(vendors)} 件")
        print(f"  ユーザー: {len(user_data)} 件")
        print(f"  物品: {len(items_data)} 件")
        print(f"  履歴: {history_count} 件")
        print("=" * 40)
        print("▶ http://localhost:3000 でログインして確認してください")

    finally:
        db.close()


if __name__ == "__main__":
    # 日本語 Windows（cp932）で出力をリダイレクトすると絵文字で落ちるため UTF-8 に固定
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="デモデータ投入スクリプト")
    parser.add_argument("--force", action="store_true", help="既存データを削除して再投入")
    parser.add_argument("--reset-users", action="store_true", help="既存のデモ用ユーザーのパスワードを初期値に戻す（E2E 用）")
    args = parser.parse_args()
    from app.config import settings

    if settings.is_production:  # 本番の DB にデモデータを入れない（H-09）
        print("本番設定（APP_ENV=production）ではデモデータを入れられません", file=sys.stderr)
        raise SystemExit(2)
    seed(force=args.force, reset_users=args.reset_users)

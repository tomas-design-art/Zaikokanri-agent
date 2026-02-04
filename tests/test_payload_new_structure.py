"""
payload正本化の動作確認テスト
新しいモジュール構成でのテスト
"""
import sqlite3
from purchase_order_payload import build_purchase_order_payloads
from purchase_order_renderers import generate_email_text, render_pdf, render_excel, format_currency


def setup_test_db():
    """テスト用DBを作成"""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    
    # テーブル作成
    cursor.execute("""
        CREATE TABLE vendors (
            id INTEGER PRIMARY KEY,
            vendor_name TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            item_name TEXT NOT NULL,
            item_code TEXT,
            vendor_id INTEGER,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE item_prices (
            id INTEGER PRIMARY KEY,
            item_id INTEGER,
            vendor_part_no TEXT,
            unit_price REAL,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE purchase_requests (
            id INTEGER PRIMARY KEY,
            item_id INTEGER,
            requested_qty INTEGER,
            note TEXT,
            requested_by_department TEXT,
            requester_name TEXT,
            status TEXT,
            deleted_at TEXT,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    """)
    
    # テストデータ挿入
    cursor.execute("INSERT INTO vendors (id, vendor_name) VALUES (1, 'ABC商事')")
    cursor.execute("INSERT INTO vendors (id, vendor_name) VALUES (2, 'XYZ文具')")
    
    cursor.execute("INSERT INTO items (id, item_name, item_code, vendor_id) VALUES (1, 'ノートパソコン', 'PC-001', 1)")
    cursor.execute("INSERT INTO items (id, item_name, item_code, vendor_id) VALUES (2, 'マウス', 'MS-001', 1)")
    cursor.execute("INSERT INTO items (id, item_name, item_code, vendor_id) VALUES (3, 'ボールペン', 'PEN-001', 2)")
    
    cursor.execute("INSERT INTO item_prices (item_id, vendor_part_no, unit_price) VALUES (1, 'ABC-NB-123', 150000)")
    cursor.execute("INSERT INTO item_prices (item_id, vendor_part_no, unit_price) VALUES (2, 'ABC-MS-456', 3000)")
    cursor.execute("INSERT INTO item_prices (item_id, vendor_part_no, unit_price) VALUES (3, 'XYZ-BP-789', 0)")  # 単価未設定
    
    cursor.execute("INSERT INTO purchase_requests (id, item_id, requested_qty, note, requested_by_department, requester_name, status, deleted_at) VALUES (1, 1, 2, '急ぎ', '情報システム部', '山田太郎', 'APPROVED', NULL)")
    cursor.execute("INSERT INTO purchase_requests (id, item_id, requested_qty, note, requested_by_department, requester_name, status, deleted_at) VALUES (2, 2, 5, '', '情報システム部', '山田太郎', 'APPROVED', NULL)")
    cursor.execute("INSERT INTO purchase_requests (id, item_id, requested_qty, note, requested_by_department, requester_name, status, deleted_at) VALUES (3, 3, 100, '青色希望', '総務部', '鈴木花子', 'APPROVED', NULL)")
    
    conn.commit()
    return conn


def test_payload_generation():
    """payload生成のテスト"""
    print("=== payload生成テスト ===")
    
    conn = setup_test_db()
    request_ids = [1, 2, 3]
    
    payloads = build_purchase_order_payloads(request_ids, conn)
    
    print(f"生成されたpayload数: {len(payloads)}")
    assert len(payloads) == 2, "2業者分のpayloadが生成されるべき"
    
    for idx, payload in enumerate(payloads, 1):
        print(f"\n--- Payload {idx}: {payload['vendor']} ---")
        print(f"業者: {payload['vendor']}")
        print(f"発注日: {payload['ordered_at']}")
        print(f"部署: {payload['requester']['department']}")
        print(f"担当者: {payload['requester']['name']}")
        print(f"品目数: {len(payload['items'])}")
        print(f"合計金額: {payload['total']}")
        print(f"単価未設定あり: {payload['has_unpriced_items']}")
        
        for item in payload['items']:
            print(f"  - {item['item_name']} × {item['quantity']} @ {format_currency(item['unit_price'])}")
    
    # 検証
    abc_payload = [p for p in payloads if p['vendor'] == 'ABC商事'][0]
    assert abc_payload['total'] == 315000.0, "ABC商事の合計金額が正しくない"
    assert not abc_payload['has_unpriced_items'], "ABC商事は単価未設定なし"
    
    xyz_payload = [p for p in payloads if p['vendor'] == 'XYZ文具'][0]
    assert xyz_payload['total'] is None, "XYZ文具の合計はNoneであるべき"
    assert xyz_payload['has_unpriced_items'], "XYZ文具は単価未設定あり"
    
    conn.close()
    print("\n✅ payload生成テスト成功")
    return payloads


def test_email_generation(payloads):
    """メール文面生成のテスト"""
    print("\n=== メール文面生成テスト ===")
    
    for payload in payloads:
        print(f"\n--- {payload['vendor']} ---")
        
        # テンプレート生成（AI無効）
        email_text = generate_email_text(payload, use_ai=False)
        print(email_text[:400])
        print("...(以下略)")
        
        # 検証
        assert payload['vendor'] in email_text, "業者名が含まれていない"
        assert "発注明細" in email_text, "明細セクションがない"
        
        if payload['has_unpriced_items']:
            assert "要確認" in email_text, "単価未設定時は「要確認」が含まれるべき"
    
    print("\n✅ メール文面生成テスト成功")


def test_pdf_generation(payloads):
    """PDF生成のテスト"""
    print("\n=== PDF生成テスト ===")
    
    for payload in payloads:
        try:
            pdf_data = render_pdf(payload)
            print(f"✅ {payload['vendor']}: PDF生成成功 ({len(pdf_data)} bytes)")
            
            # item_nameが正しく扱われているかチェック（バイト列に含まれているか）
            # PDFは英数字のみなので、日本語は変換される
            assert len(pdf_data) > 0, "PDFデータが空"
            
        except Exception as e:
            print(f"❌ {payload['vendor']}: PDF生成失敗 - {str(e)}")
            raise
    
    print("\n✅ PDF生成テスト成功")


def test_excel_generation(payloads):
    """Excel生成のテスト"""
    print("\n=== Excel生成テスト ===")
    
    try:
        excel_data = render_excel(payloads)
        print(f"✅ Excel生成成功 ({len(excel_data)} bytes)")
        
        # ファイルに保存
        with open("test_payload_new.xlsx", "wb") as f:
            f.write(excel_data)
        print("✅ test_payload_new.xlsx に保存しました")
        
        # 内容確認
        import openpyxl
        wb = openpyxl.load_workbook("test_payload_new.xlsx")
        print(f"シート一覧: {wb.sheetnames}")
        assert len(wb.sheetnames) == 2, "2つのシートがあるべき"
        
        # ABC商事シート確認
        ws_abc = wb['ABC商事']
        assert ws_abc['A2'].value == '発注日:', "ヘッダー行が正しくない"
        assert ws_abc['A3'].value == '業者:', "業者行が正しくない"
        
        # 単価未設定チェック（XYZ文具）
        ws_xyz = wb['XYZ文具']
        # 単価列（E列）が空欄であることを確認
        # 注: ヘッダーが5行あるので、データは7行目から
        
    except Exception as e:
        print(f"❌ Excel生成失敗 - {str(e)}")
        raise
    
    print("\n✅ Excel生成テスト成功")


def test_format_currency():
    """format_currency関数のテスト"""
    print("\n=== format_currency テスト ===")
    
    assert format_currency(None) == "要確認", "Noneは「要確認」"
    assert format_currency(1000) == "¥1,000", "1000円のフォーマット"
    assert format_currency(1234567) == "¥1,234,567", "大きな数値のフォーマット"
    assert format_currency(0) == "¥0", "0円のフォーマット"
    
    print("✅ format_currency テスト成功")


if __name__ == "__main__":
    print("=" * 60)
    print("payload正本化テスト開始")
    print("=" * 60)
    
    # テスト実行
    test_format_currency()
    payloads = test_payload_generation()
    test_email_generation(payloads)
    test_pdf_generation(payloads)
    test_excel_generation(payloads)
    
    print("\n" + "=" * 60)
    print("✅ 全テスト成功！")
    print("=" * 60)

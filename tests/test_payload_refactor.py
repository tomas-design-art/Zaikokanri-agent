"""
payload統一リファクタリングの動作確認テスト
"""
from order_output import build_purchase_order_payloads, generate_email_text, render_pdf, render_excel


def test_build_payloads():
    """payload生成のテスト"""
    print("=== payload生成テスト ===")
    
    # テストデータ
    selected_requests = [
        {
            "id": 1,
            "vendor_name": "ABC商事",
            "item_name": "ノートパソコン",
            "item_code": "PC-001",
            "vendor_part_no": "ABC-NB-123",
            "requested_qty": 2,
            "unit_price": 150000,
            "requested_by_department": "情報システム部",
            "requester_name": "山田太郎",
            "note": "急ぎでお願いします"
        },
        {
            "id": 2,
            "vendor_name": "ABC商事",
            "item_name": "マウス",
            "item_code": "MS-001",
            "vendor_part_no": "ABC-MS-456",
            "requested_qty": 5,
            "unit_price": 3000,
            "requested_by_department": "情報システム部",
            "requester_name": "山田太郎",
            "note": ""
        },
        {
            "id": 3,
            "vendor_name": "XYZ文具",
            "item_name": "ボールペン",
            "item_code": "PEN-001",
            "vendor_part_no": "XYZ-BP-789",
            "requested_qty": 100,
            "unit_price": 0,  # 単価未設定
            "requested_by_department": "総務部",
            "requester_name": "鈴木花子",
            "note": "青色希望"
        }
    ]
    
    payloads = build_purchase_order_payloads(selected_requests)
    
    print(f"生成されたpayload数: {len(payloads)}")
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
            print(f"  - {item['item_name']} × {item['quantity']} @ ¥{item['unit_price']:,.0f}")
    
    return payloads


def test_email_generation(payloads):
    """メール文面生成のテスト"""
    print("\n=== メール文面生成テスト ===")
    
    for payload in payloads:
        print(f"\n--- {payload['vendor']} ---")
        email_text = generate_email_text(payload, draft_text="よろしくお願いします。")
        print(email_text[:500])  # 先頭500文字のみ表示
        print("...(以下略)")


def test_pdf_generation(payloads):
    """PDF生成のテスト"""
    print("\n=== PDF生成テスト ===")
    
    for payload in payloads:
        try:
            pdf_data = render_pdf(payload)
            print(f"✅ {payload['vendor']}: PDF生成成功 ({len(pdf_data)} bytes)")
        except Exception as e:
            print(f"❌ {payload['vendor']}: PDF生成失敗 - {str(e)}")


def test_excel_generation(payloads):
    """Excel生成のテスト"""
    print("\n=== Excel生成テスト ===")
    
    try:
        excel_data = render_excel(payloads)
        print(f"✅ Excel生成成功 ({len(excel_data)} bytes)")
        
        # ファイルに保存
        with open("test_output_payload.xlsx", "wb") as f:
            f.write(excel_data)
        print("✅ test_output_payload.xlsx に保存しました")
    except Exception as e:
        print(f"❌ Excel生成失敗 - {str(e)}")


if __name__ == "__main__":
    # payload生成
    payloads = test_build_payloads()
    
    # メール文面生成
    test_email_generation(payloads)
    
    # PDF生成
    test_pdf_generation(payloads)
    
    # Excel生成
    test_excel_generation(payloads)
    
    print("\n=== テスト完了 ===")

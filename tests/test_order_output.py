"""
発注書出力機能のテストスクリプト
"""
from order_output import generate_email_text, generate_pdf, generate_excel

# テストデータ
test_vendor = "サンプル文具株式会社"
test_items = [
    {
        "item_name": "コピー用紙A4",
        "item_code": "PAPER-A4-001",
        "vendor_part_no": "VP-PAPER-001",
        "requested_qty": 10,
        "unit_price": 500,
        "note": "白色、500枚入り"
    },
    {
        "item_name": "ボールペン黒",
        "item_code": "PEN-BK-001",
        "vendor_part_no": "VP-PEN-BK",
        "requested_qty": 50,
        "unit_price": 100,
        "note": "0.5mm"
    },
    {
        "item_name": "付箋セット",
        "item_code": "NOTE-SET-001",
        "vendor_part_no": "",
        "requested_qty": 5,
        "unit_price": 0,  # 単価未設定
        "note": ""
    }
]

test_draft = """【AI生成文案】
発注書のサンプル文案です。
業者名: サンプル文具株式会社
発注日: 2026年2月1日
"""

test_department = "総務部"
test_requester = "山田太郎"

print("=" * 80)
print("1. メール文面生成テスト")
print("=" * 80)

email_text = generate_email_text(test_vendor, test_items, test_draft, test_department, test_requester)
print(email_text)
print("\n✅ メール文面生成成功\n")

print("=" * 80)
print("2. PDF生成テスト")
print("=" * 80)

try:
    pdf_data = generate_pdf(test_vendor, test_items, test_draft, test_department, test_requester)
    print(f"PDFデータサイズ: {len(pdf_data)} bytes")
    
    # PDFファイルに保存
    with open("test_purchase_order.pdf", "wb") as f:
        f.write(pdf_data)
    print("✅ PDF生成成功（test_purchase_order.pdf に保存）\n")
except Exception as e:
    print(f"❌ PDF生成エラー: {e}\n")

print("=" * 80)
print("3. Excel生成テスト")
print("=" * 80)

vendor_groups = {
    test_vendor: test_items,
    "別の業者": [
        {
            "item_name": "クリップ",
            "item_code": "CLIP-001",
            "vendor_part_no": "VP-CLIP",
            "requested_qty": 100,
            "unit_price": 10,
            "note": "大サイズ"
        }
    ]
}

try:
    excel_data = generate_excel(vendor_groups)
    print(f"Excelデータサイズ: {len(excel_data)} bytes")
    
    # Excelファイルに保存
    with open("test_purchase_order.xlsx", "wb") as f:
        f.write(excel_data)
    print("✅ Excel生成成功（test_purchase_order.xlsx に保存）\n")
except Exception as e:
    print(f"❌ Excel生成エラー: {e}\n")

print("=" * 80)
print("✅ 全テスト完了")
print("=" * 80)

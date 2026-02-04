"""テスト用: 発注候補データをAIに渡して文案を生成するスクリプト
- DBに発注候補があれば利用、なければサンプルデータでテスト
"""
from dotenv import load_dotenv
load_dotenv()
import os
import openai
from db import get_reorder_candidates

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    print("ERROR: OPENAI_API_KEY not set in environment.")
    raise SystemExit(1)

client = openai.OpenAI(api_key=API_KEY)

candidates = get_reorder_candidates()
if not candidates:
    print("No reorder candidates from DB — using sample data for test.")
    candidates = [
        {
            'item_id': 1,
            'item_name': '使い捨て手袋 Lサイズ',
            'item_code': 'GLV-L-001',
            'current_stock': 50,
            'threshold': 100,
            'recent_30_out': 80,
            'recommended_qty': 110,
            'unit_price': 2.5,
            'vendor_name': '医療資材株式会社'
        },
        {
            'item_id': 2,
            'item_name': '消毒用アルコール 500ml',
            'item_code': 'ALC-500',
            'current_stock': 20,
            'threshold': 50,
            'recent_30_out': 60,
            'recommended_qty': 100,
            'unit_price': 5.0,
            'vendor_name': '衛生商事'
        },
        {
            'item_id': 3,
            'item_name': '綿棒 100本',
            'item_code': 'QTB-100',
            'current_stock': 10,
            'threshold': 30,
            'recent_30_out': 40,
            'recommended_qty': 70,
            'unit_price': 1.2,
            'vendor_name': '医療資材株式会社'
        }
    ]

# Group by vendor
from collections import defaultdict
vendor_groups = defaultdict(list)
for r in candidates:
    vendor_groups[r.get('vendor_name')].append(r)

# Build user content
content_lines = []
for vendor, group in vendor_groups.items():
    content_lines.append(f"業者: {vendor}")
    for r in group:
        content_lines.append(
            f"- {r.get('item_name')} | code:{r.get('item_code', '')} | 現在庫:{r.get('current_stock')} | 発注点:{r.get('threshold')} | 直近30日OUT:{r.get('recent_30_out')} | 推奨発注量:{r.get('recommended_qty')} | 単価:{r.get('unit_price')}"
        )
    content_lines.append("")

user_content = "\n".join(content_lines)

system_prompt = (
    "あなたは日本語でビジネス文（発注書の文案）を作成するアシスタントです。\n"
    "以下の条件で出力してください。\n"
    "1) 業者別に分けて、各業者ごとに発注書の文案を作成すること。\n"
    "2) 各文案は 件名、宛先（宛名）、発注明細（物品名・品目コード・数量・単価・小計）、合計金額、締め文 を含めること。\n"
    "3) 出力は日本語のビジネス文で丁寧なトーンとすること。\n"
    "4) 実際の発注は行わない。文案のみを作る。\n"
    "5) 将来PDF化しやすいよう、最初にJSON形式（キー: vendor, subject, to, items[], total）を出力し、その後に人間が使える本文（改行入り）を表示すること。\n"
)

messages = [{"role": "user", "content": user_content}]

print("Calling OpenAI... (this may take a few seconds)")
try:
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "system", "content": system_prompt}] + messages,
        max_tokens=1500,
        temperature=0.5
    )
    ai_text = response.choices[0].message.content
    print("\n=== AI Result ===\n")
    print(ai_text)
    # Also save to file
    with open("order_draft_test.txt", "w", encoding="utf-8") as f:
        f.write(ai_text)
    print("\nSaved output to order_draft_test.txt")
except Exception as e:
    print(f"AI call failed: {e}")

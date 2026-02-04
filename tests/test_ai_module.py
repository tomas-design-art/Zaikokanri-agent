"""
ai.py の動作確認スクリプト
"""

import os
from dotenv import load_dotenv

# .env読み込み
load_dotenv()

from ai import generate_purchase_order_text, call_openai_chat

def test_template_generation():
    """テンプレート生成のテスト（APIキーなしでも動作）"""
    print("=" * 60)
    print("【テスト1】テンプレート生成（フォールバック）")
    print("=" * 60)
    
    # APIキーを一時的に削除してテスト
    original_key = os.environ.get("OPENAI_API_KEY")
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    
    payload = {
        "vendor": "テスト業者株式会社",
        "items": [
            {"name": "コピー用紙A4", "code": "PAPER-A4-001", "qty": 10, "unit_price": 500},
            {"name": "ボールペン黒", "code": "PEN-BK-001", "qty": 50, "unit_price": 100},
            {"name": "付箋セット", "code": "NOTE-SET-001", "qty": 5, "unit_price": 0},  # 単価未設定
        ],
        "total": None,
        "department": "総務部",
        "requester_name": "山田太郎"
    }
    
    result = generate_purchase_order_text(payload)
    print(result)
    print("\n")
    
    # 元に戻す
    if original_key:
        os.environ["OPENAI_API_KEY"] = original_key


def test_ai_generation():
    """AI生成のテスト（APIキーが設定されている場合のみ）"""
    print("=" * 60)
    print("【テスト2】AI文案生成（OPENAI_API_KEYが必要）")
    print("=" * 60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print("⚠️ OPENAI_API_KEYが未設定のためスキップ")
        print("   .envファイルに正しいAPIキーを設定してください")
        return
    
    payload = {
        "vendor": "サンプル文具株式会社",
        "items": [
            {"name": "消しゴム", "code": "ERS-001", "qty": 20, "unit_price": 80},
            {"name": "定規30cm", "code": "RUL-30-001", "qty": 15, "unit_price": 150},
        ],
        "total": 3850,
        "department": "営業部",
        "requester_name": "佐藤花子"
    }
    
    result = generate_purchase_order_text(payload)
    print(result)
    print("\n")


def test_call_openai_chat():
    """call_openai_chat関数の直接テスト"""
    print("=" * 60)
    print("【テスト3】call_openai_chat関数テスト")
    print("=" * 60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        print("⚠️ OPENAI_API_KEYが未設定のためフォールバックメッセージを返します")
    
    messages = [{"role": "user", "content": "こんにちは！簡単な挨拶をお願いします。"}]
    system_prompt = "あなたは親切なアシスタントです。"
    
    result = call_openai_chat(messages, system_prompt)
    print(result)
    print("\n")


if __name__ == "__main__":
    print("\n🧪 ai.py 動作確認テスト開始\n")
    
    test_template_generation()
    test_ai_generation()
    test_call_openai_chat()
    
    print("=" * 60)
    print("✅ テスト完了")
    print("=" * 60)

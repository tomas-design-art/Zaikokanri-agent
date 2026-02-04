"""
AIアシスタント機能のテストスクリプト
"""

import os
import sys
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()

def test_environment():
    """環境設定のテスト"""
    print("=" * 60)
    print("【テスト1】環境設定の確認")
    print("=" * 60)
    
    ai_enabled = os.getenv("AI_ENABLED", "false").lower() == "true"
    api_key = os.getenv("OPENAI_API_KEY", "")
    
    print(f"  AI_ENABLED: {ai_enabled}")
    print(f"  OPENAI_API_KEY: {'設定済み (' + api_key[:20] + '...)' if api_key else '未設定'}")
    
    if not ai_enabled:
        print("  ❌ AI_ENABLEDがfalseです。.envでtrueに設定してください。")
        return False
    
    if not api_key:
        print("  ❌ OPENAI_API_KEYが未設定です。.envに設定してください。")
        return False
    
    print("  ✅ 環境設定OK")
    return True


def test_context_data():
    """コンテキストデータ取得のテスト"""
    print("\n" + "=" * 60)
    print("【テスト2】コンテキストデータの取得")
    print("=" * 60)
    
    # app.pyから関数をインポート
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from app import get_ai_context_data, format_context_for_ai
        
        print("  データ取得中...")
        context = get_ai_context_data(max_items=10)
        
        print(f"  在庫データ: {len(context['inventory'])}件")
        print(f"  在庫アラート: {len(context['stock_alerts'])}件")
        print(f"  期限切れ: {len(context['expiry_alerts'].get('expired', []))}件")
        print(f"  期限間近: {len(context['expiry_alerts'].get('expiring_soon', []))}件")
        print(f"  月別集計: {len(context['monthly_summary'])}件")
        print(f"  部署別集計: {len(context['department_summary'])}件")
        
        # テキスト形式にフォーマット
        context_text = format_context_for_ai(context)
        print(f"\n  フォーマット済みテキスト長: {len(context_text)}文字")
        print("\n  --- コンテキストプレビュー（先頭500文字）---")
        print(context_text[:500])
        print("  ...")
        
        print("\n  ✅ コンテキストデータ取得OK")
        return True
        
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_safety_check():
    """セーフティチェックのテスト"""
    print("\n" + "=" * 60)
    print("【テスト3】セーフティチェック（操作系リクエストの拒否）")
    print("=" * 60)
    
    try:
        from app import check_safety_request
        
        # 安全なリクエスト
        safe_requests = [
            "在庫が少ない物品を教えて",
            "今月の使用状況は？",
            "発注候補をリスト化して",
            "発注書の文案を作って",
        ]
        
        # 危険なリクエスト（拒否すべき）
        unsafe_requests = [
            "在庫を入庫して",
            "この物品を削除して",
            "出庫処理をして",
            "発注を確定して",
        ]
        
        print("\n  【安全なリクエスト（許可されるべき）】")
        all_safe_ok = True
        for req in safe_requests:
            is_safe, msg = check_safety_request(req)
            status = "✅ 許可" if is_safe else "❌ 誤拒否"
            print(f"    {status}: 「{req}」")
            if not is_safe:
                all_safe_ok = False
        
        print("\n  【危険なリクエスト（拒否されるべき）】")
        all_unsafe_ok = True
        for req in unsafe_requests:
            is_safe, msg = check_safety_request(req)
            status = "✅ 拒否" if not is_safe else "❌ 誤許可"
            print(f"    {status}: 「{req}」")
            if is_safe:
                all_unsafe_ok = False
        
        if all_safe_ok and all_unsafe_ok:
            print("\n  ✅ セーフティチェックOK")
            return True
        else:
            print("\n  ⚠️ 一部のチェックに問題あり")
            return False
            
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_openai_connection():
    """OpenAI API接続テスト"""
    print("\n" + "=" * 60)
    print("【テスト4】OpenAI API接続テスト")
    print("=" * 60)
    
    try:
        from app import call_openai_chat
        
        print("  APIに接続中...")
        
        # 簡単なテストメッセージ
        messages = [{"role": "user", "content": "こんにちは。テストです。「OK」とだけ返答してください。"}]
        system_prompt = "あなたはテスト用のアシスタントです。"
        
        response = call_openai_chat(messages, system_prompt)
        
        print(f"  応答: {response[:200]}...")
        
        if "❌" in response:
            print(f"\n  ❌ API接続エラー: {response}")
            return False
        
        print("\n  ✅ OpenAI API接続OK")
        return True
        
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ai_responses():
    """AIアシスタントの応答テスト"""
    print("\n" + "=" * 60)
    print("【テスト5】AIアシスタント応答テスト")
    print("=" * 60)
    
    try:
        from app import get_ai_context_data, format_context_for_ai, call_openai_chat
        
        # コンテキスト取得
        context_data = get_ai_context_data(max_items=50)
        context_text = format_context_for_ai(context_data)
        
        # システムプロンプト
        system_prompt = f"""あなたは在庫管理システムのAIアシスタントです。

【役割】
- 在庫データの検索・要約・分析
- 発注候補の提案
- 発注書・廃棄書などの文案作成

【重要なルール】
1. データベースを変更する操作は絶対に行いません
2. 数値は必ず渡されたデータから計算してください
3. 分からない場合は「分かりません」と答えてください

【現在の在庫データ】
{context_text}
"""
        
        test_questions = [
            "在庫が少ない物品を教えて",
            "発注した方がよい物品をリスト化して",
        ]
        
        for i, question in enumerate(test_questions, 1):
            print(f"\n  【質問{i}】{question}")
            print("  " + "-" * 40)
            
            messages = [{"role": "user", "content": question}]
            response = call_openai_chat(messages, system_prompt)
            
            # 応答を表示（最初の300文字）
            display_response = response[:300] + "..." if len(response) > 300 else response
            for line in display_response.split('\n'):
                print(f"    {line}")
            
            if "❌" in response:
                print(f"\n  ⚠️ 質問{i}でエラー発生")
        
        print("\n  ✅ AI応答テスト完了")
        return True
        
    except Exception as e:
        print(f"  ❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メインテスト実行"""
    print("\n" + "=" * 60)
    print("🤖 AIアシスタント機能テスト")
    print("=" * 60)
    
    results = []
    
    # テスト1: 環境設定
    results.append(("環境設定", test_environment()))
    
    if not results[-1][1]:
        print("\n❌ 環境設定に問題があるため、以降のテストをスキップします")
        return
    
    # テスト2: コンテキストデータ
    results.append(("コンテキストデータ", test_context_data()))
    
    # テスト3: セーフティチェック
    results.append(("セーフティチェック", test_safety_check()))
    
    # テスト4: OpenAI接続
    results.append(("OpenAI API接続", test_openai_connection()))
    
    if not results[-1][1]:
        print("\n❌ OpenAI API接続に問題があるため、AI応答テストをスキップします")
    else:
        # テスト5: AI応答
        results.append(("AI応答", test_ai_responses()))
    
    # 結果サマリー
    print("\n" + "=" * 60)
    print("📊 テスト結果サマリー")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n  合計: {passed}/{len(results)} テスト成功")
    
    if failed == 0:
        print("\n🎉 全てのテストが成功しました！")
    else:
        print(f"\n⚠️ {failed}件のテストが失敗しました")


if __name__ == "__main__":
    main()

"""
AI関連機能モジュール
OpenAI APIを使った発注書文案生成などを提供
"""

import os
from typing import Dict, List, Any


def call_openai_chat(messages: List[Dict[str, str]], system_prompt: str = None, model: str = "gpt-4o-mini") -> str:
    """
    OpenAI Chat APIを呼び出す
    
    Args:
        messages: メッセージリスト [{"role": "user", "content": "..."}]
        system_prompt: システムプロンプト（任意）
        model: 使用するモデル名
    
    Returns:
        str: AIの応答テキスト（失敗時はフォールバックメッセージ）
    """
    try:
        import openai
        
        # 環境変数からAPIキーを取得
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return _fallback_message("OpenAI APIキーが設定されていません（.envファイルのOPENAI_API_KEYを確認してください）")
        
        openai.api_key = api_key
        
        # メッセージリストを構築
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        # OpenAI API呼び出し
        response = openai.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    
    except ImportError:
        return _fallback_message("openaiパッケージがインストールされていません（pip install openai）")
    except Exception as e:
        return _fallback_message(f"AI呼び出しエラー: {str(e)}")


def generate_purchase_order_text(payload: Dict[str, Any]) -> str:
    """
    発注書の文案を生成（AI使用可能ならAI、不可ならテンプレート）
    
    Args:
        payload: 発注情報
            - vendor: 業者名
            - items: 品目リスト [{"name": str, "code": str, "qty": int, "unit_price": int}]
            - total: 合計金額（任意）
            - department: 発注部署（任意）
            - requester_name: 発注者名（任意）
    
    Returns:
        str: 発注書文案テキスト
    """
    vendor = payload.get("vendor", "業者名未設定")
    items = payload.get("items", [])
    total = payload.get("total")
    department = payload.get("department", "")
    requester_name = payload.get("requester_name", "")
    
    # OpenAI使用可能かチェック
    api_key = os.getenv("OPENAI_API_KEY")
    use_ai = bool(api_key)
    
    if use_ai:
        try:
            # AI文案生成
            items_text = "\n".join([
                f"- {item.get('item_name', item.get('name', ''))} | コード:{item.get('item_code', item.get('code', ''))} | 数量:{item.get('quantity', item.get('qty', 0))} | 単価:¥{item.get('unit_price', 0):,}"
                for item in items
            ])
            
            user_content = f"""業者: {vendor}
部署: {department}
発注者: {requester_name}

発注品目:
{items_text}

合計金額: {f'¥{total:,}' if total else '要確認'}
"""
            
            system_prompt = """あなたは日本語でビジネス文（発注書の文案）を作成するアシスタントです。
以下の条件で出力してください:
1) 件名、宛先（業者名）、発注明細（物品名・品目コード・数量・単価・小計）、合計金額、締め文 を含めること
2) 単価が0や未設定の場合は小計を「要確認」と表示し、合計金額にも注記すること
3) 出力は日本語のビジネス文で丁寧なトーンとすること
4) 実際の発注は行わない。文案のみを作る
5) 最初にJSON形式（キー: vendor, subject, items[], total）を出力し、その後に人間が使える本文を表示すること"""
            
            messages = [{"role": "user", "content": user_content}]
            ai_result = call_openai_chat(messages, system_prompt)
            
            # AI生成成功
            return f"【AI生成】\n\n{ai_result}"
        
        except Exception as e:
            # AI失敗時はテンプレートにフォールバック
            use_ai = False
    
    # テンプレート文案生成（フォールバック）
    return _generate_template_order(vendor, items, total, department, requester_name)


def _generate_template_order(vendor: str, items: List[Dict], total: Any, department: str, requester_name: str) -> str:
    """テンプレート発注書文案を生成"""
    
    # 明細行の生成
    detail_lines = []
    calculated_total = 0
    has_unconfirmed = False
    
    for idx, item in enumerate(items, 1):
        name = item.get("item_name", item.get("name", "品目名不明"))
        code = item.get("item_code", item.get("code", ""))
        qty = item.get("quantity", item.get("qty", 0))
        unit_price = item.get("unit_price", 0)
        
        if unit_price > 0:
            subtotal = qty * unit_price
            calculated_total += subtotal
            detail_lines.append(f"{idx}. {name}（品目コード: {code}）\n   数量: {qty}個 × 単価: ¥{unit_price:,} = 小計: ¥{subtotal:,}")
        else:
            has_unconfirmed = True
            detail_lines.append(f"{idx}. {name}（品目コード: {code}）\n   数量: {qty}個 × 単価: 要確認 = 小計: 要確認")
    
    details_text = "\n".join(detail_lines)
    
    # 合計金額の表示
    if total is not None and isinstance(total, (int, float)) and total > 0:
        total_text = f"¥{total:,}"
    elif calculated_total > 0:
        total_text = f"¥{calculated_total:,}" + (" ※一部単価要確認" if has_unconfirmed else "")
    else:
        total_text = "要確認"
    
    # 発注者情報
    requester_info = f"{department} {requester_name}".strip() or "担当者名"
    
    template = f"""【テンプレート生成】

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
発注書
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

件名: 物品発注のお願い

{vendor} 御中

いつもお世話になっております。
下記の通り発注いたしますので、納品のほどよろしくお願い申し上げます。

【発注明細】
{details_text}

【合計金額】
{total_text}

【納品先】
{department or "（部署名）"}

【お問い合わせ先】
{requester_info}

以上、よろしくお願いいたします。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return template


def _fallback_message(reason: str) -> str:
    """AI呼び出し失敗時のフォールバックメッセージ"""
    return f"""【AI未使用 - テンプレート生成】

※ {reason}

テンプレート形式での文案生成に切り替えました。
詳細な発注書は手動で編集してください。
"""

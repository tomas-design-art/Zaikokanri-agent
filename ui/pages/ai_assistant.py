"""AIアシスタントページ"""

import os
import streamlit as st
from zoneinfo import ZoneInfo

from db import get_db_connection, get_stock_alerts, get_expiry_alerts
from utils.auth import is_logged_in

AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"


def get_ai_context_data(max_items: int = 50) -> dict:
    """
    AIアシスタントに渡すコンテキストデータを取得
    
    Args:
        max_items: 在庫データの最大件数（トークン節約のため制限）
    
    Returns:
        dict: AIに渡すコンテキストデータ
    """
    from datetime import datetime
    
    context = {
        "inventory": [],
        "stock_alerts": [],
        "expiry_alerts": {"expired": [], "expiring_soon": []},
        "monthly_summary": [],
        "department_summary": []
    }
    
    try:
        # 1. 在庫一覧（上位N件）
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    i.item_name,
                    i.item_code,
                    i.category,
                    i.vendor_name,
                    i.unit_price,
                    i.department_tags,
                    i.expiry_date,
                    i.reorder_point,
                    inv.quantity,
                    inv.location
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.is_active = 1
                ORDER BY i.item_name
                LIMIT ?
            """, (max_items,))
            
            rows = cursor.fetchall()
            context["inventory"] = [dict(row) for row in rows]
            
            # 2. 月別集計（今年のデータ）
            current_year = datetime.now(ZoneInfo('Asia/Tokyo')).year
            cursor.execute("""
                SELECT 
                    strftime('%Y-%m', ih.created_at) as month,
                    ih.department,
                    ih.change_type as action,
                    SUM(ABS(ih.quantity)) as total_quantity,
                    SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
                FROM inventory_history ih
                LEFT JOIN items i ON ih.item_id = i.id
                WHERE strftime('%Y', ih.created_at) = ?
                  AND ih.change_type IN ('OUT', 'DISPOSE')
                GROUP BY month, ih.department, ih.change_type
                ORDER BY month DESC
                LIMIT 100
            """, (str(current_year),))
            
            rows = cursor.fetchall()
            context["monthly_summary"] = [dict(row) for row in rows]
            
            # 3. 部署別集計（今年）
            cursor.execute("""
                SELECT 
                    ih.department,
                    ih.change_type as action,
                    SUM(ABS(ih.quantity)) as total_quantity,
                    SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
                FROM inventory_history ih
                LEFT JOIN items i ON ih.item_id = i.id
                WHERE strftime('%Y', ih.created_at) = ?
                  AND ih.change_type IN ('OUT', 'DISPOSE')
                GROUP BY ih.department, ih.change_type
                ORDER BY total_amount DESC
            """, (str(current_year),))
            
            rows = cursor.fetchall()
            context["department_summary"] = [dict(row) for row in rows]
        
        # 4. 在庫アラート
        context["stock_alerts"] = get_stock_alerts()
        
        # 5. 期限アラート
        context["expiry_alerts"] = get_expiry_alerts()
        
    except Exception as e:
        print(f"❌ AIコンテキスト取得エラー: {e}")
    
    return context


def format_context_for_ai(context: dict) -> str:
    """
    AIに渡すコンテキストデータをテキスト形式にフォーマット
    """
    from datetime import datetime
    
    lines = []
    lines.append(f"=== 在庫管理システムデータ（{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y年%m月%d日 %H:%M')}時点）===\n")
    
    # 在庫一覧
    lines.append("【在庫一覧】")
    if context["inventory"]:
        for item in context["inventory"]:
            expiry_info = f", 期限:{item['expiry_date']}" if item.get('expiry_date') else ""
            reorder_info = f", 発注点:{item['reorder_point']}" if item.get('reorder_point') else ""
            lines.append(
                f"- {item['item_name']} | カテゴリ:{item['category']} | "
                f"在庫数:{item['quantity']} | 単価:{item['unit_price']}円 | "
                f"部署:{item.get('department_tags', '全社')}{reorder_info}{expiry_info}"
            )
    else:
        lines.append("- データなし")
    lines.append("")
    
    # 在庫アラート
    lines.append("【在庫不足アラート】")
    if context["stock_alerts"]:
        for alert in context["stock_alerts"]:
            lines.append(
                f"- ⚠️ {alert['item_name']} | 在庫数:{alert['quantity']} | "
                f"発注点:{alert['reorder_point']} | 業者:{alert.get('vendor_name', '不明')}"
            )
    else:
        lines.append("- 在庫不足なし")
    lines.append("")
    
    # 期限アラート
    lines.append("【期限アラート】")
    expired = context["expiry_alerts"].get("expired", [])
    expiring_soon = context["expiry_alerts"].get("expiring_soon", [])
    
    if expired:
        lines.append("期限切れ:")
        for item in expired:
            lines.append(f"  - 🔴 {item['item_name']} | 期限:{item['expiry_date']} | 在庫数:{item['quantity']}")
    
    if expiring_soon:
        lines.append("期限間近（30日以内）:")
        for item in expiring_soon:
            lines.append(f"  - ⚠️ {item['item_name']} | 期限:{item['expiry_date']} | 在庫数:{item['quantity']}")
    
    if not expired and not expiring_soon:
        lines.append("- 期限アラートなし")
    lines.append("")
    
    # 月別集計
    lines.append("【月別消費・廃棄サマリ（今年）】")
    if context["monthly_summary"]:
        for row in context["monthly_summary"][:20]:  # 上位20件
            lines.append(
                f"- {row['month']} | {row['department']} | {row['action']}: "
                f"{row['total_quantity']}個, {int(row['total_amount']):,}円"
            )
    else:
        lines.append("- データなし")
    lines.append("")
    
    # 部署別集計
    lines.append("【部署別消費・廃棄サマリ（今年）】")
    if context["department_summary"]:
        for row in context["department_summary"]:
            lines.append(
                f"- {row['department']} | {row['action']}: "
                f"{row['total_quantity']}個, {int(row['total_amount']):,}円"
            )
    else:
        lines.append("- データなし")
    
    return "\n".join(lines)


def check_safety_request(user_message: str) -> tuple:
    """
    ユーザーの入力が操作系（入庫・出庫・削除など）かチェック
    
    Returns:
        tuple: (is_safe: bool, warning_message: str)
    """
    # 操作系キーワード
    operation_keywords = [
        "入庫して", "入庫する", "入庫を", "入庫処理",
        "出庫して", "出庫する", "出庫を", "出庫処理",
        "削除して", "削除する", "削除を", "削除処理",
        "廃棄して", "廃棄する", "廃棄を", "廃棄処理",
        "追加して", "追加する", "追加を",
        "登録して", "登録する", "登録を",
        "更新して", "更新する", "更新を",
        "変更して", "変更する", "変更を",
        "編集して", "編集する", "編集を",
        "発注して", "発注する", "発注を確定",
        "承認して", "承認する",
        "取り消して", "キャンセルして",
        "処理して", "実行して",
    ]
    
    for keyword in operation_keywords:
        if keyword in user_message:
            return (False, "⚠️ 在庫の操作（入庫・出庫・削除など）はAIアシスタントからは行えません。\n通常の操作画面から行ってください。")
    
    return (True, "")


def call_openai_chat(messages: list, system_prompt: str) -> str:
    """
    OpenAI APIを呼び出してチャット応答を取得
    
    Args:
        messages: チャット履歴
        system_prompt: システムプロンプト
    
    Returns:
        str: AIの応答
    """
    import openai
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "❌ OpenAI APIキーが設定されていません。環境変数 `OPENAI_API_KEY` を設定してください。"
    
    try:
        client = openai.OpenAI(api_key=api_key)
        
        # メッセージ構築
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)
        
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=full_messages,
            max_tokens=2000,
            temperature=0.7
        )
        
        return response.choices[0].message.content
    
    except openai.AuthenticationError:
        return "❌ OpenAI APIキーが無効です。正しいAPIキーを設定してください。"
    except openai.RateLimitError:
        return "❌ OpenAI APIのレート制限に達しました。しばらく待ってから再試行してください。"
    except Exception as e:
        return f"❌ AI応答エラー: {str(e)}"


def show_ai_assistant_page():
    """AIアシスタントページ（閲覧専用・DB更新なし）"""
    st.header("🤖 AIアシスタント")
    
    # 権限チェック
    if not is_logged_in():
        st.warning("⚠️ AIアシスタントを利用するにはログインが必要です")
        return
    
    # AI機能が無効の場合
    if not AI_ENABLED:
        st.error("🚫 AI機能は無効になっています。管理者に連絡してください。")
        st.info("💡 AI機能を有効にするには、環境変数 `AI_ENABLED=true` を設定してください。")
        return
    
    # OpenAI APIキーチェック
    if not os.getenv("OPENAI_API_KEY"):
        st.error("🚫 OpenAI APIキーが設定されていません。")
        st.info("💡 環境変数 `OPENAI_API_KEY` を設定してください。")
        return
    
    # 説明文
    st.info("""
    💡 **在庫状況や発注候補について質問できます**
    
    このアシスタントは在庫データを参照して、検索・要約・提案を行います。
    ※ 在庫の操作（入庫・出庫・削除など）は行いません。
    """)
    
    # 質問例の表示
    with st.expander("📝 質問の例", expanded=False):
        st.markdown("""
        - 「在庫が少ない物品を教えて」
        - 「今月、どの部署が一番使ってる？」
        - 「発注した方がよい物品をリスト化して」
        - 「期限切れの物品は？」
        - 「廃棄が多いカテゴリは？」
        - 「発注書の文案を作って」
        - 「〇〇の在庫状況を教えて」
        """)
    
    st.divider()
    
    # チャット履歴の初期化
    if "ai_chat_history" not in st.session_state:
        st.session_state.ai_chat_history = []
    
    # チャット履歴の表示
    chat_container = st.container()
    with chat_container:
        if not st.session_state.ai_chat_history:
            st.caption("💬 質問を入力してください")
        else:
            for message in st.session_state.ai_chat_history:
                if message["role"] == "user":
                    st.chat_message("user").markdown(message["content"])
                else:
                    st.chat_message("assistant").markdown(message["content"])
    
    st.divider()
    
    # 入力フォーム
    col1, col2 = st.columns([5, 1])
    
    with col1:
        user_input = st.text_input(
            "質問を入力",
            placeholder="例: 在庫が少ない物品を教えて",
            key="ai_user_input",
            label_visibility="collapsed"
        )
    
    with col2:
        send_button = st.button("📤 送信", use_container_width=True, type="primary")
    
    # 履歴クリアボタン
    col_clear, col_space = st.columns([1, 5])
    with col_clear:
        if st.button("🗑️ 履歴クリア", use_container_width=True):
            st.session_state.ai_chat_history = []
            st.rerun()
    
    # 送信処理
    if send_button and user_input:
        # セーフティチェック
        is_safe, warning_msg = check_safety_request(user_input)
        
        if not is_safe:
            # 操作系リクエストは拒否
            st.session_state.ai_chat_history.append({"role": "user", "content": user_input})
            st.session_state.ai_chat_history.append({"role": "assistant", "content": warning_msg})
            st.rerun()
        else:
            # コンテキストデータを取得
            with st.spinner("📊 在庫データを取得中..."):
                context_data = get_ai_context_data(max_items=50)
                context_text = format_context_for_ai(context_data)
            
            # システムプロンプト構築
            system_prompt = f"""あなたは在庫管理システムのAIアシスタントです。

【役割】
- 在庫データの検索・要約・分析
- 発注候補の提案
- 発注書・廃棄書などの文案作成
- ユーザーの質問への回答

【重要なルール】
1. データベースを変更する操作は絶対に行いません（入庫・出庫・削除・更新など）
2. 数値は必ず渡されたデータから計算してください。推測しないでください。
3. 分からない場合は「分かりません」と正直に答えてください
4. 操作系の依頼（入庫して、削除してなど）には「通常の操作画面から行ってください」と案内してください
5. 回答はMarkdown形式で見やすく整形してください

【現在の在庫データ】
{context_text}
"""
            
            # ユーザーメッセージを追加
            st.session_state.ai_chat_history.append({"role": "user", "content": user_input})
            
            # AI応答を取得
            with st.spinner("🤖 回答を生成中..."):
                # OpenAI形式のメッセージ履歴を構築（最新5往復まで）
                messages_for_api = []
                recent_history = st.session_state.ai_chat_history[-10:]  # 最新10メッセージ
                for msg in recent_history:
                    messages_for_api.append({"role": msg["role"], "content": msg["content"]})
                
                ai_response = call_openai_chat(messages_for_api, system_prompt)
            
            # AI応答を追加
            st.session_state.ai_chat_history.append({"role": "assistant", "content": ai_response})
            
            st.rerun()

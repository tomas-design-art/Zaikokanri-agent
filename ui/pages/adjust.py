"""在庫調整ページ"""

import streamlit as st

from utils.auth import (
    require_role, get_current_user
)
from repositories.history_repo import process_adjust
from repositories.inventory_query import get_all_items_for_adjust


def show_adjust_page():
    """在庫調整ページ（管理者専用）"""
    st.header("🔧 在庫調整")
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "在庫調整は管理者のみ使用できます"):
        return
    
    st.info("💡 管理者専用機能：在庫数量を直接調整できます。棚卸しや誤差修正などにご使用ください。")
    
    # 前回の調整成功メッセージを表示
    if "last_adjust_success" in st.session_state and st.session_state.last_adjust_success:
        success_data = st.session_state.last_adjust_success
        
        st.success("### ✅ 在庫調整が完了しました！")
        st.balloons()
        
        st.markdown("---")
        st.subheader("📋 調整完了内容")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**物品名:** {success_data['item_name']}")
            st.write(f"**調整前:** {success_data['old_quantity']} 個")
            st.write(f"**調整後:** {success_data['new_quantity']} 個")
        with col2:
            diff = success_data['new_quantity'] - success_data['old_quantity']
            direction = "増加 ⬆️" if diff > 0 else "減少 ⬇️"
            st.write(f"**変動:** {direction} {abs(diff)} 個")
            st.write(f"**理由:** {success_data['reason']}")
            st.write(f"**調整者:** {success_data['user_name']}")
        
        st.markdown("---")
        
        if st.button("🔄 続けて調整する", use_container_width=True):
            st.session_state.last_adjust_success = None
            st.rerun()
        
        return
    
    # 全物品を取得
    items = get_all_items_for_adjust()
    
    if not items:
        st.warning("⚠️ 調整対象の物品がありません")
        return
    
    st.subheader("📝 調整対象を選択")
    
    # 物品選択
    item_options = {
        f"{item['item_name']} (現在: {item.get('quantity', 0)}個) [{item.get('category', '-')}]": item['id']
        for item in items
    }
    
    selected_item_display = st.selectbox(
        "物品を選択",
        options=list(item_options.keys()),
        help="調整する物品を選択してください",
        key="adjust_item_select"
    )
    
    selected_item_id = item_options[selected_item_display]
    selected_item = next(item for item in items if item['id'] == selected_item_id)
    
    # 現在の在庫情報を表示
    current_quantity = selected_item.get('quantity', 0) or 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("現在在庫", f"{current_quantity} 個")
    with col2:
        st.metric("保管場所", selected_item.get('location') or "未設定")
    with col3:
        st.metric("カテゴリ", selected_item.get('category', '-'))
    
    st.divider()
    
    # 調整フォーム
    with st.form("adjust_form", clear_on_submit=True):
        st.subheader("🔢 調整内容を入力")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_quantity = st.number_input(
                "調整後の数量",
                min_value=0,
                max_value=100000,
                value=current_quantity,
                step=1,
                help="調整後の在庫数量を入力してください（0以上）"
            )
        
        with col2:
            # 差分をリアルタイム表示するため計算
            diff = new_quantity - current_quantity
            if diff > 0:
                st.info(f"⬆️ {diff} 個 増加")
            elif diff < 0:
                st.info(f"⬇️ {abs(diff)} 個 減少")
            else:
                st.info("変更なし")
        
        # 理由（必須）
        reason = st.text_area(
            "調整理由 *（必須）",
            placeholder="例: 棚卸し差異修正、破損廃棄、システム誤差修正など",
            height=100,
            help="調整理由は必須です。監査のため詳細に記録してください。"
        )
        
        # ユーザー情報（自動）
        current_user = get_current_user()
        st.caption(f"📝 調整者: {current_user.get('display_name', '')} ({current_user.get('department', '')})")
        
        st.divider()
        
        # 送信ボタン
        col1, col2 = st.columns([3, 1])
        with col1:
            st.warning("⚠️ 調整操作は取り消せません。内容をよく確認してください。")
        with col2:
            submitted = st.form_submit_button(
                "🔧 調整を実行",
                type="primary",
                use_container_width=True
            )
        
        if submitted:
            # バリデーション
            if not reason or reason.strip() == "":
                st.error("❌ 調整理由を入力してください（必須）")
            elif new_quantity == current_quantity:
                st.warning("⚠️ 数量に変更がありません")
            else:
                # 調整処理実行
                result = process_adjust(
                    item_id=selected_item_id,
                    new_quantity=new_quantity,
                    user_name=current_user.get("display_name", ""),
                    department=current_user.get("department", ""),
                    reason=reason.strip()
                )
                
                if result["success"]:
                    # 成功データをsession_stateに保存
                    st.session_state.last_adjust_success = {
                        'item_name': selected_item['item_name'],
                        'old_quantity': current_quantity,
                        'new_quantity': new_quantity,
                        'reason': reason.strip(),
                        'user_name': current_user.get("display_name", "")
                    }
                    st.rerun()
                else:
                    st.error(result["message"])

"""承認管理ページ"""

import streamlit as st

from utils.auth import (
    get_current_user, get_user_display_name,
    is_admin, require_min_role
)
from utils.validation import validate_required_string
from utils.logger import log_approve, log_reject
from repositories.pending_repo import (
    get_pending_transactions,
    approve_pending_transaction,
    reject_pending_transaction,
)
from repositories.inventory_repo import get_item_by_id
from ui.components.refresh_button import show_refresh_button


def show_approval_page():
    """承認管理ページ（USER/ADMIN専用）"""
    st.header("✅ 承認管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：USER以上
    if not require_min_role("USER", "承認管理は一般ユーザー以上のみ使用できます"):
        return
    
    # 前回の処理結果メッセージを表示
    if "approval_success_message" in st.session_state and st.session_state.approval_success_message:
        st.success(st.session_state.approval_success_message)
        st.session_state.approval_success_message = None
    
    if "approval_error_message" in st.session_state and st.session_state.approval_error_message:
        st.error(st.session_state.approval_error_message)
        st.session_state.approval_error_message = None
    
    current_user = get_current_user()
    user_dept_id = current_user.get("department_id")
    
    # ADMINは全部署、USERは自部署のみ
    if is_admin():
        st.info("💡 管理者として全部署の承認待ち申請を表示しています。")
        pending_list = get_pending_transactions()  # 全件
    else:
        dept_name = current_user.get("department", "")
        st.info(f"💡 「{dept_name}」部署の承認待ち申請を表示しています。")
        pending_list = get_pending_transactions(department_id=user_dept_id)  # 自部署のみ
    
    if not pending_list:
        st.success("🎉 承認待ちの申請はありません")
        return
    
    st.subheader(f"📋 承認待ち申請: {len(pending_list)} 件")
    
    for pending in pending_list:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 2])
            
            with col1:
                # 申請種別
                change_type_label = "➖ 出庫" if pending['change_type'] == 'OUT' else "➕ 入庫"
                st.markdown(f"### {change_type_label}")
                
                # 物品情報
                st.markdown(f"**物品:** {pending.get('item_name', 'N/A')} ({pending.get('item_code', 'N/A')})")
                st.markdown(f"**数量:** {pending['quantity']} 個")
                
                # 申請者情報
                st.caption(f"👤 申請者: {pending['actor_name']}")
                st.caption(f"🏢 部署: {pending.get('department_name', 'N/A')}")
                
                if pending.get('note'):
                    st.caption(f"📝 備考: {pending['note']}")
                
                st.caption(f"🕒 申請日時: {pending['created_at']}")
            
            with col2:
                # 現在在庫確認
                item = get_item_by_id(pending['item_id'])
                if item:
                    current_qty = item.get('quantity', 0)
                    st.metric("現在在庫", f"{current_qty} 個")
                    
                    # 出庫の場合、在庫が足りるかチェック
                    if pending['change_type'] == 'OUT':
                        if current_qty < pending['quantity']:
                            st.error(f"⚠️ 在庫不足！")
                else:
                    st.warning("物品が見つかりません")
            
            with col3:
                # 承認・却下ボタン
                st.write("**操作:**")
                
                # 二重実行防止フラグ
                processing_key = f"processing_approval_{pending['id']}"
                is_processing = st.session_state.get(processing_key, False)
                
                # 却下理由入力
                reject_key = f"reject_reason_{pending['id']}"
                
                # 承認ボタン（二重実行防止対応）
                if st.button("✅ 承認", key=f"approve_{pending['id']}", use_container_width=True, type="primary", disabled=is_processing):
                    st.session_state[processing_key] = True
                    # 在庫チェック（出庫の場合）
                    if pending['change_type'] == 'OUT':
                        item = get_item_by_id(pending['item_id'])
                        if item and item.get('quantity', 0) < pending['quantity']:
                            st.session_state.approval_error_message = "❌ 在庫が不足しているため承認できません"
                            if processing_key in st.session_state:
                                del st.session_state[processing_key]
                            st.rerun()
                        else:
                            result = approve_pending_transaction(pending['id'], current_user['id'])
                            if result["success"]:
                                item_name = pending.get('item_name', '物品')
                                qty = pending['quantity']
                                actor = pending['actor_name']
                                log_approve(get_user_display_name(), pending['id'], "pending_transaction")
                                st.session_state.approval_success_message = f"✅ 1件の申請を承認しました: {item_name} {qty}個（申請者: {actor}）"
                            else:
                                st.session_state.approval_error_message = result["message"]
                            if processing_key in st.session_state:
                                del st.session_state[processing_key]
                            st.rerun()
                    else:
                        result = approve_pending_transaction(pending['id'], current_user['id'])
                        if result["success"]:
                            item_name = pending.get('item_name', '物品')
                            qty = pending['quantity']
                            actor = pending['actor_name']
                            log_approve(get_user_display_name(), pending['id'], "pending_transaction")
                            st.session_state.approval_success_message = f"✅ 1件の申請を承認しました: {item_name} {qty}個（申請者: {actor}）"
                        else:
                            st.session_state.approval_error_message = result["message"]
                        if processing_key in st.session_state:
                            del st.session_state[processing_key]
                        st.rerun()
                
                # 却下ボタン
                with st.expander("却下する場合"):
                    reject_reason = st.text_input("却下理由", key=reject_key, placeholder="理由を入力")
                    reject_processing_key = f"processing_reject_{pending['id']}"
                    is_reject_processing = st.session_state.get(reject_processing_key, False)
                    if st.button("❌ 却下", key=f"reject_{pending['id']}", use_container_width=True, disabled=is_reject_processing):
                        # 却下理由バリデーション
                        ok, reason_clean, err = validate_required_string(reject_reason, field_name="却下理由", min_length=1)
                        if not ok:
                            st.warning("却下理由を入力してください")
                        else:
                            st.session_state[reject_processing_key] = True
                            result = reject_pending_transaction(pending['id'], current_user['id'], reason_clean)
                            if result["success"]:
                                item_name = pending.get('item_name', '物品')
                                log_reject(get_user_display_name(), pending['id'], "pending_transaction", reason_clean)
                                st.session_state.approval_success_message = f"❌ 1件の申請を却下しました: {item_name}（理由: {reason_clean}）"
                            else:
                                st.session_state.approval_error_message = result["message"]
                            if reject_processing_key in st.session_state:
                                del st.session_state[reject_processing_key]
                            st.rerun()

"""発注申請管理ページ（ADMIN）"""

import os
import streamlit as st
from zoneinfo import ZoneInfo

from utils.auth import require_role, get_current_user
from repositories.base import get_db_connection
from repositories.department_repo import get_all_departments
from repositories.purchase_request_repo import (
    get_purchase_requests,
    get_purchase_request_counts,
    approve_purchase_request,
    hold_purchase_request,
    reject_purchase_request,
    reset_purchase_request_to_pending,
    delete_purchase_request,
    mark_requests_ordered,
)
from ui.components.refresh_button import show_refresh_button
from ui.pages.purchase_request import handle_purchase_request_error

AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"


def show_purchase_request_admin_page():
    """✅ 発注申請管理ページ（ADMIN向け）- 承認から発注書作成まで完結"""
    st.header("✅ 発注申請管理")
    show_refresh_button()

    # 権限チェック（共通関数使用）
    if not require_role("ADMIN", "このページは管理者のみアクセスできます"):
        return

    import pandas as pd
    from collections import defaultdict
    
    current_user = get_current_user()
    user_id = current_user.get("id")
    
    # 発注書作成画面の表示フラグ
    if "show_order_creation" not in st.session_state:
        st.session_state.show_order_creation = False
    
    # 発注書作成画面を表示中の場合
    if st.session_state.show_order_creation:
        show_order_creation_screen(user_id)
        return
    
    # ========== メイン画面 ==========
    
    # ステータス別件数
    counts = get_purchase_request_counts()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("承認待ち", f"{counts.get('pending', 0)}件")
    with col2:
        st.metric("承認済み", f"{counts.get('approved', 0)}件")
    with col3:
        st.metric("保留", f"{counts.get('on_hold', 0)}件")
    with col4:
        st.metric("却下", f"{counts.get('rejected', 0)}件")

    st.divider()
    
    # 部署フィルタ（状態保持）
    if "pr_dept_filter" not in st.session_state:
        st.session_state.pr_dept_filter = "全て"
    
    all_dept_options = ["全て"] + [d['name'] for d in get_all_departments()]
    try:
        current_index = all_dept_options.index(st.session_state.pr_dept_filter)
    except ValueError:
        current_index = 0
    
    dept_filter = st.selectbox(
        "部署で絞る", 
        options=all_dept_options,
        index=current_index,
        key="pr_dept_filter"
    )
    query_dept = None if dept_filter == "全て" else dept_filter
    
    query_dept = None if dept_filter == "全て" else dept_filter
    
    # 入庫待ち件数を取得（部署フィルタ適用後）
    waiting_for_receipt = get_purchase_requests(status="ORDERED", department=query_dept)
    waiting_count = len(waiting_for_receipt) if waiting_for_receipt else 0

    # ========== ステータスタブ ==========
    tab_pending, tab_approved, tab_hold, tab_rejected, tab_waiting = st.tabs([
        f"📋 承認待ち ({counts.get('pending', 0)}件)",
        f"✅ 承認済み ({counts.get('approved', 0)}件)",
        f"⏸ 保留 ({counts.get('on_hold', 0)}件)",
        f"❌ 却下 ({counts.get('rejected', 0)}件)",
        f"🚚 入庫待ち ({waiting_count}件)"
    ])

    # ========== タブ1: 承認待ち（PENDING） ==========
    with tab_pending:
        pending_requests = get_purchase_requests(status="PENDING", department=query_dept)
        
        if not pending_requests:
            st.info("承認待ちの申請はありません")
        else:
            # CSV出力
            df_pending = pd.DataFrame(pending_requests)
            csv_pending = df_pending.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_pending, file_name="pending_requests.csv", mime="text/csv")
            
            st.caption("💡 各申請を承認・保留・却下できます。連続して処理可能です。")
            st.divider()
            
            # 一覧表示
            for req in pending_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    # 申請情報の表示
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個 / 発注点: {req.get('threshold', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.info(f"📝 備考: {req['note']}")
                    
                    with col_action:
                        # 承認・保留・却下アクションフォーム
                        with st.form(f"action_form_{rid}"):
                            admin_comment = st.text_area(
                                "管理コメント",
                                value=req.get('admin_comment') or "",
                                key=f"comment_{rid}",
                                height=60,
                                placeholder="保留/却下時は必須",
                                help="保留または却下する場合は理由を入力してください"
                            )
                            
                            col_a, col_h, col_r = st.columns(3)
                            with col_a:
                                approve_btn = st.form_submit_button("✔", help="承認", use_container_width=True)
                            with col_h:
                                hold_btn = st.form_submit_button("⏸", help="保留", use_container_width=True)
                            with col_r:
                                reject_btn = st.form_submit_button("❌", help="却下", use_container_width=True)
                            
                            if approve_btn:
                                res = approve_purchase_request(rid, user_id, comment=admin_comment)
                                if res.get('success'):
                                    st.success("✔ 承認しました")
                                    st.rerun()
                                else:
                                    handle_purchase_request_error(res, rid, user_id)
                            
                            if hold_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 保留理由を入力してください")
                                else:
                                    res = hold_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("⏸ 保留にしました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                            
                            if reject_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 却下理由を入力してください")
                                else:
                                    res = reject_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("❌ 却下しました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                    
                    st.divider()

    # ========== タブ2: 承認済み（APPROVED） ==========
    with tab_approved:
        approved_requests = get_purchase_requests(status="APPROVED", department=query_dept)
        
        if not approved_requests:
            st.info("承認済みの申請はありません")
        else:
            # CSV出力
            df_approved = pd.DataFrame(approved_requests)
            csv_approved = df_approved.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_approved, file_name="approved_requests.csv", mime="text/csv")
            
            st.caption("💡 発注する申請にチェックを入れて「発注書を作成」ボタンを押してください。")
            
            # チェックボックス選択用のセッション管理
            if "selected_request_ids" not in st.session_state:
                st.session_state.selected_request_ids = []
            
            # 全選択/全解除
            col_select, col_clear, col_space = st.columns([1, 1, 3])
            with col_select:
                if st.button("✔ 全て選択", use_container_width=True):
                    st.session_state.selected_request_ids = [req['id'] for req in approved_requests]
                    # 各チェックボックスのSession Stateも更新
                    for req in approved_requests:
                        st.session_state[f"check_{req['id']}"] = True
                    st.rerun()
            with col_clear:
                if st.button("◻ 全て解除", use_container_width=True):
                    st.session_state.selected_request_ids = []
                    # 各チェックボックスのSession Stateも更新
                    for req in approved_requests:
                        st.session_state[f"check_{req['id']}"] = False
                    st.rerun()
            
            st.divider()
            
            # 一覧表示（チェックボックス付き）
            for req in approved_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    col_check, col_info = st.columns([1, 10])
                    
                    with col_check:
                        is_checked = rid in st.session_state.selected_request_ids
                        
                        # チェックボックスの状態をセッションで管理
                        checkbox_key = f"check_{rid}"
                        
                        # Session Stateに値を設定（valueパラメータは使わない）
                        if checkbox_key not in st.session_state or st.session_state.get(f"_force_update_{rid}", False):
                            st.session_state[checkbox_key] = is_checked
                            if f"_force_update_{rid}" in st.session_state:
                                del st.session_state[f"_force_update_{rid}"]
                        
                        if st.checkbox("選択", key=checkbox_key, label_visibility="collapsed"):
                            if rid not in st.session_state.selected_request_ids:
                                st.session_state.selected_request_ids.append(rid)
                        else:
                            if rid in st.session_state.selected_request_ids:
                                st.session_state.selected_request_ids.remove(rid)
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.caption(f"📝 {req['note']}")
                        if req.get('admin_comment'):
                            st.caption(f"💬 管理コメント: {req['admin_comment']}")
                    
                    st.divider()
            
            # 発注書作成・保留・却下ボタン
            selected_count = len(st.session_state.selected_request_ids)
            if selected_count > 0:
                st.markdown(f"### 📦 選択中: {selected_count}件")
                
                col_order, col_hold, col_reject = st.columns(3)
                
                with col_order:
                    if st.button("📝 発注書を作成", type="primary", use_container_width=True):
                        # 選択された申請を一時保存して発注書作成画面へ
                        st.session_state.order_creation_request_ids = st.session_state.selected_request_ids.copy()
                        st.session_state.show_order_creation = True
                        st.rerun()
                
                with col_hold:
                    if st.button("⏸ 選択を保留に", use_container_width=True):
                        st.session_state.show_hold_form = True
                
                with col_reject:
                    if st.button("❌ 選択を却下に", use_container_width=True):
                        st.session_state.show_reject_form = True
                
                # 保留フォームの表示
                if st.session_state.get("show_hold_form", False):
                    with st.form("bulk_hold_form"):
                        st.subheader("⏸ 選択した申請を保留にする")
                        hold_reason = st.text_area(
                            "保留理由（必須）",
                            placeholder="保留する理由を入力してください",
                            height=100
                        )
                        
                        col_submit, col_cancel = st.columns(2)
                        with col_submit:
                            submit_hold = st.form_submit_button("⏸ 保留にする", type="primary", use_container_width=True)
                        with col_cancel:
                            cancel_hold = st.form_submit_button("キャンセル", use_container_width=True)
                        
                        if submit_hold:
                            if not hold_reason or hold_reason.strip() == "":
                                st.error("⚠️ 保留理由を入力してください")
                            else:
                                success_count = 0
                                for req_id in st.session_state.selected_request_ids:
                                    res = hold_purchase_request(req_id, user_id, comment=hold_reason)
                                    if res.get('success'):
                                        success_count += 1
                                
                                if success_count > 0:
                                    st.success(f"⏸ {success_count}件を保留にしました")
                                    st.session_state.selected_request_ids = []
                                    st.session_state.show_hold_form = False
                                    st.rerun()
                        
                        if cancel_hold:
                            st.session_state.show_hold_form = False
                            st.rerun()
                
                # 却下フォームの表示
                if st.session_state.get("show_reject_form", False):
                    with st.form("bulk_reject_form"):
                        st.subheader("❌ 選択した申請を却下にする")
                        reject_reason = st.text_area(
                            "却下理由（必須）",
                            placeholder="却下する理由を入力してください",
                            height=100
                        )
                        
                        col_submit, col_cancel = st.columns(2)
                        with col_submit:
                            submit_reject = st.form_submit_button("❌ 却下にする", type="primary", use_container_width=True)
                        with col_cancel:
                            cancel_reject = st.form_submit_button("キャンセル", use_container_width=True)
                        
                        if submit_reject:
                            if not reject_reason or reject_reason.strip() == "":
                                st.error("⚠️ 却下理由を入力してください")
                            else:
                                success_count = 0
                                for req_id in st.session_state.selected_request_ids:
                                    res = reject_purchase_request(req_id, user_id, comment=reject_reason)
                                    if res.get('success'):
                                        success_count += 1
                                
                                if success_count > 0:
                                    st.success(f"❌ {success_count}件を却下にしました")
                                    st.session_state.selected_request_ids = []
                                    st.session_state.show_reject_form = False
                                    st.rerun()
                        
                        if cancel_reject:
                            st.session_state.show_reject_form = False
                            st.rerun()

    # ========== タブ3: 保留（ON_HOLD） ==========
    with tab_hold:
        hold_requests = get_purchase_requests(status="ON_HOLD", department=query_dept)
        
        if not hold_requests:
            st.info("保留中の申請はありません")
        else:
            # CSV出力
            df_hold = pd.DataFrame(hold_requests)
            csv_hold = df_hold.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_hold, file_name="hold_requests.csv", mime="text/csv")
            
            st.caption("💡 保留中の申請を承認または却下できます。")
            st.divider()
            
            # 一覧表示
            for req in hold_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    # 申請情報の表示
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.caption(f"📝 備考: {req['note']}")
                        
                        if req.get('admin_comment'):
                            st.warning(f"⏸ 保留理由: {req['admin_comment']}")
                    
                    with col_action:
                        # 承認・却下・削除フォーム
                        with st.form(f"hold_action_form_{rid}"):
                            admin_comment = st.text_area(
                                "管理コメント更新",
                                value=req.get('admin_comment') or "",
                                key=f"hold_comment_{rid}",
                                height=60,
                                placeholder="コメントを更新（任意）",
                                help="承認または却下する際のコメント"
                            )
                            
                            col_a, col_r, col_d = st.columns(3)
                            with col_a:
                                approve_btn = st.form_submit_button("✔", help="承認", use_container_width=True)
                            with col_r:
                                reject_btn = st.form_submit_button("❌", help="却下", use_container_width=True)
                            with col_d:
                                delete_btn = st.form_submit_button("🗑️", help="削除", use_container_width=True)
                            
                            if approve_btn:
                                res = approve_purchase_request(rid, user_id, comment=admin_comment)
                                if res.get('success'):
                                    st.success("✔ 承認しました")
                                    st.rerun()
                                else:
                                    handle_purchase_request_error(res, rid, user_id)
                            
                            if reject_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 却下理由を入力してください")
                                else:
                                    res = reject_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("❌ 却下しました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                            
                            if delete_btn:
                                res = delete_purchase_request(rid, user_id)
                                if res.get('success'):
                                    st.success("🗑️ 削除しました")
                                    st.rerun()
                                else:
                                    st.error(res.get('message'))
                    
                    st.divider()

    # ========== タブ4: 却下（REJECTED） ==========
    with tab_rejected:
        rejected_requests = get_purchase_requests(status="REJECTED", department=query_dept)
        
        if not rejected_requests:
            st.info("却下された申請はありません")
        else:
            # CSV出力
            df_rejected = pd.DataFrame(rejected_requests)
            csv_rejected = df_rejected.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_rejected, file_name="rejected_requests.csv", mime="text/csv")
            
            st.caption("💡 却下された申請を確認できます。承認に戻すこともできます。")
            st.divider()
            
            # 一覧表示
            for req in rejected_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    # 申請情報の表示
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.caption(f"📝 備考: {req['note']}")
                        
                        if req.get('admin_comment'):
                            st.error(f"❌ 却下理由: {req['admin_comment']}")
                    
                    with col_action:
                        # 承認待ち・保留・削除フォーム
                        with st.form(f"reject_action_form_{rid}"):
                            admin_comment = st.text_area(
                                "管理コメント更新",
                                value=req.get('admin_comment') or "",
                                key=f"reject_comment_{rid}",
                                height=60,
                                placeholder="コメントを更新（任意）",
                                help="承認待ちまたは保留する際のコメント"
                            )
                            
                            col_p, col_h, col_d = st.columns(3)
                            with col_p:
                                pending_btn = st.form_submit_button("🔄", help="承認待ちに戻す", use_container_width=True)
                            with col_h:
                                hold_btn = st.form_submit_button("⏸", help="保留", use_container_width=True)
                            with col_d:
                                delete_btn = st.form_submit_button("🗑️", help="削除", use_container_width=True)
                            
                            if pending_btn:
                                res = reset_purchase_request_to_pending(rid, user_id, comment=admin_comment)
                                if res.get('success'):
                                    st.success("🔄 承認待ちに戻しました")
                                    st.rerun()
                                else:
                                    st.error(res.get('message'))
                            
                            if hold_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 保留理由を入力してください")
                                else:
                                    res = hold_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("⏸ 保留にしました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                            
                            if delete_btn:
                                res = delete_purchase_request(rid, user_id)
                                if res.get('success'):
                                    st.success("🗑️ 削除しました")
                                    st.rerun()
                                else:
                                    st.error(res.get('message'))
                    
                    st.divider()

    # ========== タブ5: 入庫待ち（ORDERED） ==========
    with tab_waiting:
        st.caption("💡 発注処理が完了し、現場での入庫待ちの申請です。")
        
        if not waiting_for_receipt:
            st.info("入庫待ちの申請はありません")
        else:
            # CSV出力
            df_waiting = pd.DataFrame(waiting_for_receipt)
            csv_waiting = df_waiting.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_waiting, file_name="waiting_for_receipt.csv", mime="text/csv")
            
            st.divider()
            
            # 一覧表示
            for req in waiting_for_receipt:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container(border=True):
                    st.markdown(f"### {req['item_name']} {priority_badge}")
                    
                    # 基本情報
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write("**📋 申請情報**")
                        st.caption(f"👤 申請者: {req.get('requester_name', '')} ({req['requested_by_department']})")
                        st.caption(f"📅 申請日: {req.get('created_at', '')[:10] if req.get('created_at') else ''}")
                        st.caption(f"📦 希望数量: {req['requested_qty']}個")
                        if req.get('note'):
                            st.caption(f"📝 申請メモ: {req['note']}")
                    
                    with col2:
                        st.write("**✅ 承認・発注情報**")
                        if req.get('approved_at'):
                            st.caption(f"✅ 承認日: {req['approved_at'][:10]}")
                        if req.get('ordered_at'):
                            st.caption(f"🚚 発注日: {req['ordered_at'][:10]}")
                        if req.get('order_channel'):
                            channel_map = {'email': 'メール', 'pdf': 'PDF', 'excel': 'Excel'}
                            st.caption(f"📤 発注方法: {channel_map.get(req['order_channel'], req['order_channel'])}")
                        if req.get('generated_document_name'):
                            st.caption(f"📄 発注書: {req['generated_document_name']}")
                    
                    with col3:
                        st.write("**📦 物品情報**")
                        st.caption(f"品目コード: {req.get('item_code', '-')}")
                        st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                        st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        st.caption(f"💰 合計: ¥{req['requested_qty'] * req.get('unit_price', 0):,.0f}")
                    
                    if req.get('admin_comment'):
                        st.info(f"💬 管理者コメント: {req['admin_comment']}")
                    
                    # 入庫ページへのリンク案内
                    st.success("📍 入庫処理は「➕ 入庫」→「🚚 発注品入庫」タブで行えます")
                    
                st.divider()


def show_order_creation_screen(user_id: int):
    """発注書作成画面（メール文面・PDF・Excel出力対応）"""
    from datetime import datetime
    from purchase_order_payload import build_purchase_order_payloads
    from purchase_order_renderers import generate_email_text, render_pdf, render_excel
    
    st.header("📝 発注書作成")
    
    # 戻るボタン
    if st.button("← 発注申請管理に戻る"):
        st.session_state.show_order_creation = False
        for key in ["order_creation_request_ids", "order_draft_text", "po_generated",
                    "last_output_channel", "last_document_name", "order_payloads"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
    
    st.divider()
    
    # 選択された申請IDを取得
    request_ids = st.session_state.get("order_creation_request_ids", [])
    if not request_ids:
        st.error("申請が選択されていません。発注申請管理画面に戻ってください。")
        return
    
    # ========== payload生成（正本データ） ==========
    if "order_payloads" not in st.session_state:
        # DBからpayloadを一度だけ生成
        with get_db_connection() as conn:
            st.session_state.order_payloads = build_purchase_order_payloads(request_ids, conn)
    
    payloads = st.session_state.order_payloads
    
    if not payloads:
        st.error("発注データの生成に失敗しました。")
        return
    
    # ========== 単価未設定チェック ==========
    total_unpriced = sum(1 for p in payloads if p.get("has_unpriced_items", False))
    
    if total_unpriced > 0:
        unconfirmed_items = []
        for payload in payloads:
            if payload.get("has_unpriced_items"):
                for item in payload.get("items", []):
                    if item.get("unit_price") is None:
                        unconfirmed_items.append({
                            'vendor': payload.get("vendor", "不明業者"),
                            'item_name': item.get("item_name", ""),
                            'item_code': item.get("item_code", ""),
                            'qty': item.get("quantity", 0)
                        })
        
        st.warning(f"⚠️ **単価未設定の品目が {len(unconfirmed_items)}件 あります。発注書の金額は「要確認」となります。**")
        with st.expander(f"📋 単価未設定の品目一覧 ({len(unconfirmed_items)}件)", expanded=False):
            for item in unconfirmed_items:
                st.write(f"- **{item['item_name']}** ({item['item_code']}) × {item['qty']}個 - 業者: {item['vendor']}")
    
    # ========== 発注明細テーブル表示 ==========
    total_items = sum(len(p.get("items", [])) for p in payloads)
    st.subheader(f"📦 発注対象: {total_items}件（{len(payloads)}業者）")
    
    for payload in payloads:
        vendor = payload.get("vendor", "不明業者")
        items = payload.get("items", [])
        with st.expander(f"🏢 {vendor} ({len(items)}件)", expanded=True):
            for item in items:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"**{item.get('item_name', '')}**")
                    st.caption(f"品目コード: {item.get('item_code', '')}")
                with col2:
                    st.write(f"数量: {item.get('quantity', 0)}個")
                with col3:
                    unit_price = item.get('unit_price')
                    if unit_price is not None:
                        st.write(f"単価: ¥{unit_price:,.0f}")
                    else:
                        st.warning("単価: 未設定")
    
    st.divider()
    
    # ========== AI文案生成・編集エリア ==========
    st.subheader("📝 発注文案の生成・編集")
    
    # テンプレート文案を生成する関数
    def generate_template_draft(payloads_list):
        """テンプレート発注文案を生成（payloadベース）"""
        all_drafts = []
        for payload in payloads_list:
            vendor = payload.get("vendor", "不明業者")
            items = payload.get("items", [])
            has_unpriced = payload.get("has_unpriced_items", False)
            total = payload.get("total")
            
            draft_lines = [f"【{vendor} 御中】", ""]
            draft_lines.append("いつもお世話になっております。")
            draft_lines.append("下記の通り発注いたしますので、納品のほどよろしくお願い申し上げます。")
            draft_lines.append("")
            draft_lines.append("【発注明細】")
            
            for idx, item in enumerate(items, 1):
                item_name = item.get("item_name", "")
                item_code = item.get("item_code", "")
                qty = item.get("quantity", 0)
                unit_price = item.get("unit_price")
                subtotal = item.get("subtotal")
                
                if unit_price is not None and subtotal is not None:
                    draft_lines.append(f"{idx}. {item_name}（{item_code}）× {qty}個 @ ¥{unit_price:,.0f} = ¥{subtotal:,.0f}")
                else:
                    draft_lines.append(f"{idx}. {item_name}（{item_code}）× {qty}個 @ 単価未設定 = 要確認")
            
            draft_lines.append("")
            if has_unpriced or total is None:
                draft_lines.append("【合計金額】要確認")
            else:
                draft_lines.append(f"【合計金額】¥{total:,.0f}")
            draft_lines.append("")
            draft_lines.append("以上、よろしくお願いいたします。")
            
            all_drafts.append("\n".join(draft_lines))
        
        return "\n\n" + "="*60 + "\n\n".join(all_drafts)
    
    # 初期表示: テンプレート文案
    if "order_draft_text" not in st.session_state:
        st.session_state.order_draft_text = generate_template_draft(payloads)
    
    # AI生成ボタン（AI有効時のみ表示）
    import os
    can_use_ai = AI_ENABLED and os.getenv("OPENAI_API_KEY")
    
    if can_use_ai:
        # DEBUG: AI入力データの確認
        if st.checkbox("🔧 DEBUG: AI入力データを表示", key="debug_ai_input"):
            st.write("DEBUG payloads (AI input):", payloads)

        if st.button("🤖 AIで文案を生成", use_container_width=True):
            try:
                with st.spinner("🤖 AI文案を生成中..."):
                    # payloadごとにAI文案を生成
                    all_drafts = []
                    for payload in payloads:
                        draft = generate_email_text(payload, use_ai=True)
                        all_drafts.append(draft)
                    
                    # 複数業者の場合は区切り線で結合
                    st.session_state.order_draft_text = "\n\n" + "="*80 + "\n\n".join(all_drafts)
                    st.success("✅ AI文案を生成しました")
                    st.rerun()
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                st.error(f"⚠️ AI生成に失敗しました。テンプレート文案を使用してください。\n\nエラー: {str(e)}\n\n詳細:\n{error_detail}")
    
    # 文案編集エリア
    edited_draft = st.text_area(
        "発注文案（編集可能）",
        value=st.session_state.order_draft_text,
        height=300,
        help="この文案はメール出力に反映されます"
    )
    
    # 編集内容を保存
    if edited_draft != st.session_state.order_draft_text:
        st.session_state.order_draft_text = edited_draft
    
    # テンプレートに戻すボタン
    if st.button("🔄 テンプレート文案に戻す", use_container_width=True):
        st.session_state.order_draft_text = generate_template_draft(payloads)
        st.rerun()
    
    st.divider()
    
    # ========== 出力ボタン ==========
    st.subheader("📤 発注書の出力")
    st.caption("いずれかの形式で出力してください。出力後に「発注済み確定」ボタンが有効になります。")
    
    col_email, col_pdf, col_excel = st.columns(3)
    
    with col_email:
        if st.button("📧 メール文面を生成", use_container_width=True, type="primary"):
            email_texts = []
            for payload in payloads:
                # 編集済みdraft_textをメール文面として使用
                email_text = st.session_state.order_draft_text
                email_texts.append(email_text)
            
            st.session_state.email_output = st.session_state.order_draft_text
            st.session_state.po_generated = True
            st.session_state.last_output_channel = "email"
            st.session_state.last_document_name = f"email_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d_%H%M%S')}.txt"
            st.success("✅ メール文面を生成しました")
    
    with col_pdf:
        if st.button("📄 PDFで発注書出力", use_container_width=True, type="primary"):
            # 最初の業者のPDFを生成
            first_payload = payloads[0]
            
            try:
                pdf_data = render_pdf(first_payload)
                st.session_state.pdf_output = pdf_data
                st.session_state.po_generated = True
                st.session_state.last_output_channel = "pdf"
                st.session_state.last_document_name = f"purchase_order_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d_%H%M%S')}.pdf"
                st.success("✅ PDFを生成しました")
            except Exception as e:
                st.error(f"❌ PDF生成エラー: {str(e)}")
    
    with col_excel:
        if st.button("📊 Excelで発注書出力", use_container_width=True, type="primary"):
            try:
                excel_data = render_excel(payloads)
                st.session_state.excel_output = excel_data
                st.session_state.po_generated = True
                st.session_state.last_output_channel = "excel"
                st.session_state.last_document_name = f"purchase_order_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d_%H%M%S')}.xlsx"
                st.success("✅ Excelを生成しました")
            except Exception as e:
                st.error(f"❌ Excel生成エラー: {str(e)}")
    
    st.divider()
    
    # ========== 出力結果の表示・ダウンロード ==========
    if st.session_state.get("email_output"):
        st.subheader("📧 生成されたメール文面")
        st.code(st.session_state.email_output, language="text")
        st.download_button(
            "📥 メール文面をダウンロード",
            data=st.session_state.email_output.encode("utf-8"),
            file_name=st.session_state.get("last_document_name", "email.txt"),
            mime="text/plain",
            use_container_width=True
        )
        st.divider()
    
    if st.session_state.get("pdf_output"):
        st.subheader("📄 生成されたPDF発注書")
        st.success("PDFが生成されました。ダウンロードボタンからダウンロードしてください。")
        st.download_button(
            "📥 PDFをダウンロード",
            data=st.session_state.pdf_output,
            file_name=st.session_state.get("last_document_name", "purchase_order.pdf"),
            mime="application/pdf",
            use_container_width=True
        )
        st.divider()
    
    if st.session_state.get("excel_output"):
        st.subheader("📊 生成されたExcel発注書")
        st.success("Excelファイルが生成されました。ダウンロードボタンからダウンロードしてください。")
        st.download_button(
            "📥 Excelをダウンロード",
            data=st.session_state.excel_output,
            file_name=st.session_state.get("last_document_name", "purchase_order.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.divider()
    
    # ========== 発注済み確定ボタン ==========
    if st.session_state.get("po_generated", False):
        st.subheader("✅ 発注済みに確定")
        st.warning("⚠️ この操作を実行すると、選択した申請が「発注済み（ORDERED）」になります。")
        
        if st.button("✅ 発注済みに確定する", type="primary", use_container_width=True):
            # 二重実行防止
            if st.session_state.get("order_finalized", False):
                st.error("既に発注済みに確定しています。")
            else:
                result = mark_requests_ordered(
                    request_ids, 
                    user_id,
                    order_channel=st.session_state.get("last_output_channel"),
                    document_name=st.session_state.get("last_document_name")
                )
                
                if result.get("success"):
                    st.balloons()
                    st.success(f"🎉 {result['count']}件を発注済みにしました！")
                    st.session_state.order_finalized = True
                    
                    # セッションクリア
                    import time
                    time.sleep(2)
                    
                    # クリーンアップ
                    for key in ["order_creation_request_ids", "order_draft_text", "email_output", 
                                "pdf_output", "excel_output", "po_generated", 
                                "last_output_channel", "last_document_name", "order_finalized", "order_payloads"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    
                    st.session_state.selected_request_ids = []
                    st.session_state.show_order_creation = False
                    st.rerun()
                else:
                    st.error(result.get("message"))
    else:
        st.info("💡 メール文面・PDF・Excelのいずれかを生成すると、発注済み確定ボタンが表示されます。")

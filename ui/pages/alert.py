"""アラートページ"""

import streamlit as st
import pandas as pd

from db import get_stock_alerts, get_expiry_alerts, check_items_ordered_status
from utils.auth import is_logged_in, get_current_user, is_admin, is_guest
from ui.components.refresh_button import show_refresh_button


def set_menu(menu_id: str):
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1
    st.rerun()


def show_alert_page():
    """アラート画面（在庫不足・期限切れ/間近）"""
    from datetime import datetime
    
    st.header("🚨 アラート")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック
    if not is_logged_in():
        st.warning("⚠️ アラートを確認するにはログインが必要です")
        return
    
    # 部署フィルタリング（ADMINは全体、USER/GUESTは自部署のみ）
    current_user = get_current_user()
    user_dept = current_user.get("department") if current_user else None
    
    if is_admin():
        department_filter = None  # ADMINは全部署+全社共通
    else:
        department_filter = user_dept  # USER/GUESTは自部署のみ
        if user_dept:
            st.info(f"📍 表示範囲: **{user_dept}** の物品のみ")
    
    # セクション切替（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["📦 在庫不足", "⏰ 期限"],
        horizontal=True,
        key="alert_section",
    )

    if section == "📦 在庫不足":
        st.subheader("📦 在庫不足アラート")
        st.caption("在庫数が発注点以下の物品を表示します")
        
        stock_alerts = get_stock_alerts(department_name=department_filter)
        
        # 申請済み状態を取得
        if stock_alerts:
            item_ids = [item['id'] for item in stock_alerts]
            order_status_map = check_items_ordered_status(item_ids)
        else:
            order_status_map = {}
        
        if not stock_alerts:
            st.success("✅ 在庫不足の物品はありません")
        else:
            st.warning(f"⚠️ 在庫不足の物品が **{len(stock_alerts)}件** あります")
            
            # 発注申請ボタンの表示（USER/ADMINのみ）
            show_purchase_button = not is_guest()
            
            # 列ヘッダー
            if show_purchase_button:
                header_cols = st.columns([3, 1, 1, 1, 1, 1, 1, 1.5])
            else:
                header_cols = st.columns([3, 1, 1, 1, 1, 1, 1])
            
            with header_cols[0]:
                st.markdown("**物品名**")
            with header_cols[1]:
                st.markdown("**品目コード**")
            with header_cols[2]:
                st.markdown("**カテゴリ**")
            with header_cols[3]:
                st.markdown("**在庫数**")
            with header_cols[4]:
                st.markdown("**発注点**")
            with header_cols[5]:
                st.markdown("**保管場所**")
            with header_cols[6]:
                st.markdown("**業者名**")
            if show_purchase_button:
                with header_cols[7]:
                    st.markdown("**操作**")
            
            # 在庫数が少ない順にソート
            stock_alerts_sorted = sorted(stock_alerts, key=lambda x: x['quantity'])
            
            # 各行に発注申請ボタンを追加
            for idx, item in enumerate(stock_alerts_sorted):
                with st.container():
                    if show_purchase_button:
                        cols = st.columns([3, 1, 1, 1, 1, 1, 1, 1.5])
                    else:
                        cols = st.columns([3, 1, 1, 1, 1, 1, 1])
                    
                    # 申請済み状態を確認
                    item_info = order_status_map.get(item['id'])
                    status_badge = ""
                    if item_info:
                        status = item_info.get('status')
                        qty = item_info.get('qty', 0)
                        # 入庫完了は表示しない（まだ不足しているなら追加申請が必要）
                        if status == 'ordered':
                            status_badge = f"✅ 発注済（{qty}個）"
                        elif status == 'pending':
                            status_badge = f"📝 申請済（{qty}個）"
                    
                    with cols[0]:
                        if status_badge:
                            st.write(f"**{item['item_name']}** {status_badge}")
                        else:
                            st.write(f"**{item['item_name']}**")
                    with cols[1]:
                        st.write(item['item_code'])
                    with cols[2]:
                        st.write(item['category'])
                    with cols[3]:
                        st.write(f"{item['quantity']}")
                    with cols[4]:
                        st.write(f"{item['reorder_point']}")
                    with cols[5]:
                        st.write(item['location'])
                    with cols[6]:
                        st.write(item.get('vendor_name', ''))
                    if show_purchase_button:
                        with cols[7]:
                            if st.button("📝 発注申請", key=f"purchase_stock_{idx}_{item['id']}"):
                                # セッションステートに選択した物品情報を保存
                                st.session_state.prefill_purchase_item_id = item['id']
                                st.session_state.prefill_purchase_quantity = max(item['reorder_point'] - item['quantity'], 1)
                                st.session_state.prefill_purchase_reason = "在庫不足アラート"
                                set_menu("purchase_request")
            
            st.info("💡 発注点を見直す場合は「物品マスター管理」から編集してください")
    
    if section == "⏰ 期限":
        st.subheader("⏰ 期限アラート")
        st.caption("期限切れまたは期限間近（30日以内）の物品を表示します")
        
        # GUESTは廃棄申請権限がないため、期限アラートを表示しない
        if is_guest():
            st.info("📍 ゲストユーザーは期限アラートを表示できません。廃棄申請権限はUSER/ADMINのみです。")
            return
        
        # 部署フィルタリングを適用（ADMINは全体、USERは自部署のみ）
        expiry_alerts = get_expiry_alerts(department_name=department_filter)
        expired = expiry_alerts.get("expired", [])
        expiring_soon = expiry_alerts.get("expiring_soon", [])
        
        total_count = len(expired) + len(expiring_soon)
        
        if total_count == 0:
            st.success("✅ 期限アラートはありません")
        else:
            # サマリー表示
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("合計", f"{total_count}件")
            with col2:
                st.metric("期限切れ", f"{len(expired)}件", delta=None, delta_color="off")
            with col3:
                st.metric("期限間近", f"{len(expiring_soon)}件", delta=None, delta_color="off")
            
            st.divider()
            
            # 期限切れ
            if expired:
                st.error(f"🔴 **期限切れ: {len(expired)}件**")
                
                df_expired = pd.DataFrame(expired)
                
                # 廃棄申請ボタンの追加（USER/ADMINのみ）
                show_disposal_button = not is_guest()
                
                # 列ヘッダー
                header_cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                with header_cols[0]:
                    st.markdown("**物品名**")
                with header_cols[1]:
                    st.markdown("**品目コード**")
                with header_cols[2]:
                    st.markdown("**カテゴリ**")
                with header_cols[3]:
                    st.markdown("**使用期限**")
                with header_cols[4]:
                    st.markdown("**在庫数**")
                with header_cols[5]:
                    st.markdown("**保管場所**")
                with header_cols[6]:
                    st.markdown("**操作**")
                
                # 各行に廃棄申請ボタンを追加
                for idx, item in enumerate(expired):
                    with st.container():
                        cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                        
                        with cols[0]:
                            st.write(f"**{item['item_name']}**")
                        with cols[1]:
                            st.write(item['item_code'])
                        with cols[2]:
                            st.write(item['category'])
                        with cols[3]:
                            st.write(item['expiry_date'])
                        with cols[4]:
                            st.write(f"{item['quantity']}")
                        with cols[5]:
                            st.write(item['location'])
                        with cols[6]:
                            if show_disposal_button:
                                if st.button("🗑️ 廃棄申請する", key=f"disposal_expired_{idx}_{item['id']}"):
                                    # セッションステートに選択した物品情報を保存
                                    st.session_state.prefill_disposal_item_id = item['id']
                                    st.session_state.prefill_disposal_quantity = 1
                                    st.session_state.prefill_disposal_reason = "期限アラート"
                                    set_menu("disposal_request")
                
                st.divider()
            
            # 期限間近
            if expiring_soon:
                st.warning(f"⚠️ **期限間近（30日以内）: {len(expiring_soon)}件**")
                
                df_expiring = pd.DataFrame(expiring_soon)
                
                # 廃棄申請ボタンの追加（USER/ADMINのみ）
                show_disposal_button = not is_guest()
                
                # 列ヘッダー
                header_cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                with header_cols[0]:
                    st.markdown("**物品名**")
                with header_cols[1]:
                    st.markdown("**品目コード**")
                with header_cols[2]:
                    st.markdown("**カテゴリ**")
                with header_cols[3]:
                    st.markdown("**使用期限**")
                with header_cols[4]:
                    st.markdown("**在庫数**")
                with header_cols[5]:
                    st.markdown("**保管場所**")
                with header_cols[6]:
                    st.markdown("**操作**")
                
                # 各行に廃棄申請ボタンを追加
                for idx, item in enumerate(expiring_soon):
                    with st.container():
                        cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                        
                        with cols[0]:
                            st.write(f"**{item['item_name']}**")
                        with cols[1]:
                            st.write(item['item_code'])
                        with cols[2]:
                            st.write(item['category'])
                        with cols[3]:
                            st.write(item['expiry_date'])
                        with cols[4]:
                            st.write(f"{item['quantity']}")
                        with cols[5]:
                            st.write(item['location'])
                        with cols[6]:
                            if show_disposal_button:
                                if st.button("🗑️ 廃棄申請する", key=f"disposal_expiring_{idx}_{item['id']}"):
                                    # セッションステートに選択した物品情報を保存
                                    st.session_state.prefill_disposal_item_id = item['id']
                                    st.session_state.prefill_disposal_quantity = 1
                                    st.session_state.prefill_disposal_reason = "期限アラート"
                                    set_menu("disposal_request")
                
                st.divider()
            
            st.info("💡 期限切れ物品は廃棄処理を検討してください")

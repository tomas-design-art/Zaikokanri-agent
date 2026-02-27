"""ダッシュボードページ"""

import streamlit as st
import pandas as pd

from utils.auth import get_current_user, is_guest, get_user_department
from ui.components.refresh_button import show_refresh_button
from repositories.stats_repo import (
    get_monthly_outbound_total,
    get_stock_alert_count,
    get_expired_count,
)
from repositories.disposal_repo import get_disposal_count
from repositories.inventory_query import get_inventory_list, get_total_count
from utils.date_utils import parse_db_ts_to_jst

def set_menu(menu_id: str):
    """メニューIDを設定して画面遷移"""
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1
    st.rerun()


def show_dashboard_page():
    """🏠 ダッシュボードページ（KPI表示）"""

    st.header("🏠 ダッシュボード")

    # ロール判定（GUESTは部署フィルタあり）
    current_user = get_current_user()
    user_role = current_user.get("user_role")
    user_dept = current_user.get("department")

    # 部署フィルタの設定
    department_filter = user_dept if user_role == "GUEST" else None

    # GUEST向けに表示範囲を明示
    if user_role == "GUEST":
        st.caption(f"📍 表示範囲: {user_dept} + 全社共通")

    st.subheader("📊 今月のKPI")

    # KPIデータ取得
    monthly_out = get_monthly_outbound_total(department_name=department_filter)
    stock_alert_count = get_stock_alert_count(department_name=department_filter)
    expired_count = get_expired_count(department_name=department_filter)
    disposal_pending = get_disposal_count(status="PENDING")

    # KPIカード表示（4列）
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="📤 今月の出庫数量",
            value=f"{monthly_out:,}",
            help="今月の出庫（OUT）数量の合計"
        )

    with col2:
        st.metric(
            label="⚠️ 在庫不足件数",
            value=f"{stock_alert_count}件",
            delta=None,
            delta_color="off",
            help="在庫数が発注点以下の物品数"
        )

    with col3:
        st.metric(
            label="🔴 期限切れ件数",
            value=f"{expired_count}件",
            delta=None,
            delta_color="off",
            help="使用期限が過ぎている物品数"
        )

    with col4:
        # 廃棄待ちはADMIN/USERのみ表示（GUESTは廃棄申請を見ない想定）
        if user_role in ["ADMIN", "USER"]:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value=f"{disposal_pending}件",
                delta=None,
                delta_color="off",
                help="承認待ちの廃棄申請数"
            )
        else:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value="-",
                help="この情報は管理者のみ表示されます"
            )

    st.divider()

    # クイックリンク
    st.subheader("🔗 クイックアクセス")

    link_col1, link_col2, link_col3, link_col4 = st.columns(4)

    with link_col1:
        if st.button("📦 在庫一覧", use_container_width=True):
            set_menu("inventory")

    with link_col2:
        if st.button("🚨 アラート", use_container_width=True):
            set_menu("alert")

    with link_col3:
        if user_role in ["ADMIN", "USER"]:
            if st.button("➕ 入庫", use_container_width=True):
                set_menu("inbound")
        elif user_role == "GUEST":
            if st.button("➖ 出庫（申請）", use_container_width=True):
                set_menu("outbound")

    with link_col4:
        if user_role in ["ADMIN", "USER"]:
            if st.button("➖ 出庫", use_container_width=True):
                set_menu("outbound")

    st.divider()

    # 補足情報
    st.info("💡 左側メニューから各機能にアクセスできます")

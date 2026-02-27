"""在庫一覧ページ"""

import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import can_inbound, get_current_user, is_admin, is_guest
from ui.components.refresh_button import show_refresh_button
from repositories.inventory_query import get_inventory_list, get_total_count, get_categories
from repositories.pending_repo import get_pending_count
from repositories.stats_repo import get_monthly_outbound_total, get_stock_alert_count, get_expired_count
from repositories.disposal_repo import get_disposal_count
from repositories.purchase_candidate_repo import get_reorder_candidates_count


def show_inventory_page():
    """在庫一覧ページ"""
    st.header("📦 在庫一覧")
    
    # 更新ボタン
    show_refresh_button()
    
    # ========== 承認待ち通知（USER/ADMIN向け） ==========
    if can_inbound():  # USER/ADMINのみ表示
        current_user = get_current_user()
        user_dept_id = current_user.get("department_id")
        
        # ADMINは全部署、USERは自部署のみ
        if is_admin():
            pending_count = get_pending_count()  # 全件
        else:
            pending_count = get_pending_count(department_id=user_dept_id)  # 自部署のみ
        
        if pending_count > 0:
            st.warning(f"⚠️ **承認待ち申請が {pending_count} 件** あります。「📋 承認管理」ページで確認してください。")
    
    # ========== KPI カード ==========
    
    # ロール判定（GUESTは部署フィルタあり）
    current_user = get_current_user()
    user_role = current_user.get("user_role")
    user_dept = current_user.get("department")
    department_filter = user_dept if user_role == "GUEST" else None
    
    # GUEST向けに表示範囲を明示
    if user_role == "GUEST":
        st.caption(f"📍 表示範囲: {user_dept} + 全社共通")
    
    # KPI取得
    monthly_out = get_monthly_outbound_total(department_name=department_filter)
    stock_alert_count = get_stock_alert_count(department_name=department_filter)
    expired_count = get_expired_count(department_name=department_filter)
    disposal_pending = get_disposal_count(status="PENDING")
    reorder_count = get_reorder_candidates_count(department_name=department_filter)
    
    # KPIカード表示（5列）
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    
    with kpi_col1:
        st.metric(
            label="📤 今月の出庫数量",
            value=f"{monthly_out:,}",
            help="今月の出庫（OUT）数量の合計"
        )
    
    with kpi_col2:
        st.metric(
            label="⚠️ 在庫不足件数",
            value=f"{stock_alert_count}件",
            help="在庫数が発注点以下の物品数"
        )
    
    with kpi_col3:
        st.metric(
            label="🔴 期限切れ件数",
            value=f"{expired_count}件",
            help="使用期限が過ぎている物品数"
        )
    
    with kpi_col4:
        if user_role in ["ADMIN", "USER"]:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value=f"{disposal_pending}件",
                help="承認待ちの廃棄申請数"
            )
        else:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value="-",
                help="この情報は管理者のみ表示されます"
            )
    
    with kpi_col5:
        st.metric(
            label="📦 発注候補件数",
            value=f"{reorder_count}件",
            help="消耗品で在庫不足＋直近30日OUT履歴あり"
        )
    
    st.divider()
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")
    
    # 検索フォーム
    col1, col2, col3, col4 = st.columns([3, 2, 1.5, 1])
    
    with col1:
        search_query = st.text_input(
            "🔍 検索",
            placeholder="品目名、品目コード、業者名などで検索",
            key="search_query"
        )
    
    with col2:
        categories = ["すべて"] + get_categories()
        category_filter = st.selectbox(
            "カテゴリ",
            options=categories,
            key="category_filter"
        )
    
    with col3:
        asset_filter = st.selectbox(
            "種別",
            options=["すべて", "消耗品", "資産"],
            key="asset_filter"
        )
    
    with col4:
        st.write("")  # スペース調整
        st.write("")
        search_button = st.button("🔎 検索", use_container_width=True)
    
    # ページネーション設定
    items_per_page = st.selectbox(
        "表示件数",
        options=[50, 100, 200, 500],
        index=1,
        key="items_per_page"
    )
    
    # ページ番号（セッションステートで管理）
    if "current_page" not in st.session_state:
        st.session_state.current_page = 1
    
    # 部署フィルタ（GUESTユーザーのみ適用）
    department_name_filter = None
    if is_guest():
        current_user = get_current_user()
        user_dept = current_user.get("department")
        if user_dept:
            department_name_filter = user_dept
            st.info(f"📋 表示範囲：**{user_dept}** のみ")
    
    # 総件数取得
    total_count = get_total_count(search_query, category_filter, asset_filter, department_name=department_name_filter)
    total_pages = (total_count + items_per_page - 1) // items_per_page
    
    # ページ情報とCSV出力ボタン
    col_info, col_csv = st.columns([3, 1])
    with col_info:
        st.info(f"📊 全 {total_count} 件中 {min(items_per_page, total_count)} 件を表示")
    with col_csv:
        if total_count > 0:
            # 全件取得してCSV出力用データを作成
            df_all = get_inventory_list(search_query, category_filter, asset_filter, limit=total_count, offset=0, department_name=department_name_filter)
            if not df_all.empty:
                # 種別を日本語化
                df_all['asset_type'] = df_all['is_asset'].map({0: '消耗品', 1: '資産'})
                
                csv_df = pd.DataFrame({
                    "品目名": df_all["item_name"],
                    "品目コード": df_all["item_code"],
                    "カテゴリ": df_all["category"],
                    "種別": df_all["asset_type"],
                    "在庫数": df_all["quantity"],
                    "閾値": df_all["threshold"],
                    "保管場所": df_all["location"].fillna("未設定"),
                    "業者名": df_all["vendor_name"].fillna(""),
                    "単価": df_all["unit_price"],
                    "部署タグ": df_all["department_tags"].fillna("")
                })
                
                csv_data = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                filename = f"inventory_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
                
                st.download_button(
                    label="📥 CSV出力",
                    data=csv_data,
                    file_name=filename,
                    mime="text/csv",
                    use_container_width=True,
                    help="現在のフィルタ条件で絞り込まれた在庫をCSV出力します"
                )
    
    # データ取得
    offset = (st.session_state.current_page - 1) * items_per_page
    df = get_inventory_list(search_query, category_filter, asset_filter, items_per_page, offset, department_name=department_name_filter)
    
    if not df.empty:
        # 在庫アラート表示
        alert_items = df[df["quantity"] <= df["threshold"]]
        if not alert_items.empty:
            st.warning(f"⚠️ 在庫が閾値以下の品目が {len(alert_items)} 件あります")
        
        # データ表示（カラム名を日本語化）
        display_df = df[[
            "alert_status", "item_name", "item_code", "category",
            "quantity", "threshold", "location", "vendor_name", "unit_price"
        ]].copy()
        
        display_df.columns = [
            "状態", "品目名", "品目コード", "カテゴリ",
            "在庫数", "閾値", "保管場所", "業者名", "単価"
        ]
        
        # データフレーム表示（Streamlitのデータフレームは自動でページネーション）
        st.dataframe(
            display_df,
            width='stretch',
            hide_index=True
        )
        
        # ページネーションコントロール
        if total_pages > 1:
            col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
            
            with col1:
                if st.button("⏮️ 最初", disabled=(st.session_state.current_page == 1)):
                    st.session_state.current_page = 1
                    st.rerun()
            
            with col2:
                if st.button("◀️ 前へ", disabled=(st.session_state.current_page == 1)):
                    st.session_state.current_page -= 1
                    st.rerun()
            
            with col3:
                st.write(f"ページ {st.session_state.current_page} / {total_pages}")
            
            with col4:
                if st.button("次へ ▶️", disabled=(st.session_state.current_page == total_pages)):
                    st.session_state.current_page += 1
                    st.rerun()
            
            with col5:
                if st.button("最後 ⏭️", disabled=(st.session_state.current_page == total_pages)):
                    st.session_state.current_page = total_pages
                    st.rerun()
    else:
        st.info("🔍 該当する在庫データがありません")

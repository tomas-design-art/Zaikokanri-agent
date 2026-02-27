"""統計・集計ページ"""

import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import is_logged_in, is_guest
from ui.components.refresh_button import show_refresh_button
from db import get_db_connection, get_all_departments, get_category_names


def show_statistics_page():
    """集計ページ（USER/ADMIN専用）"""
    st.header("📊 集計")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック：USER/ADMINのみ
    if not is_logged_in():
        st.warning("⚠️ 集計を表示するにはログインが必要です")
        return
    
    if is_guest():
        st.error("🚫 この機能はゲストユーザーは使用できません")
        return
    
    st.info("💡 部署別・月別の出庫（消費）状況を確認できます")
    
    # フィルタ設定
    st.subheader("🔍 集計条件")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # 開始月
        current_date = datetime.now(ZoneInfo('Asia/Tokyo')).date()
        default_start = current_date.replace(month=1, day=1)  # 今年の1月
        
        start_date = st.date_input(
            "開始月",
            value=default_start,
            key="stats_start_date"
        )
        start_month = start_date.strftime('%Y-%m')
    
    with col2:
        # 終了月
        end_date = st.date_input(
            "終了月",
            value=current_date,
            key="stats_end_date"
        )
        end_month = end_date.strftime('%Y-%m')
    
    with col3:
        # 部署フィルタ
        departments = get_all_departments(active_only=True)
        dept_options = ["すべて"] + [dept['name'] for dept in departments]
        selected_dept = st.selectbox(
            "部署",
            options=dept_options,
            key="stats_dept"
        )
    
    with col4:
        # カテゴリフィルタ
        category_names = get_category_names()
        category_options = ["すべて"] + category_names
        selected_category = st.selectbox(
            "カテゴリ",
            options=category_options,
            key="stats_category"
        )
    
    # アクション種別
    action_types = st.multiselect(
        "集計対象",
        options=["OUT", "DISPOSE"],
        default=["OUT"],
        help="OUT: 出庫、DISPOSE: 廃棄",
        key="stats_action_types"
    )
    
    if not action_types:
        st.warning("⚠️ 集計対象を選択してください")
        return
    
    st.divider()
    
    # データ取得
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # SQLクエリ構築
        action_filter = "', '".join(action_types)
        
        # 月別サマリ（全体）
        st.subheader("📅 月別サマリ（全体）")
        
        sql_monthly = f"""
            SELECT 
                strftime('%Y-%m', ih.created_at) as month,
                ih.change_type as action,
                SUM(ABS(ih.quantity)) as total_quantity,
                SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
            FROM inventory_history ih
            LEFT JOIN items i ON ih.item_id = i.id
            WHERE ih.change_type IN ('{action_filter}')
              AND strftime('%Y-%m', ih.created_at) >= ?
              AND strftime('%Y-%m', ih.created_at) <= ?
        """
        
        params = [start_month, end_month]
        
        if selected_dept != "すべて":
            sql_monthly += " AND ih.department = ?"
            params.append(selected_dept)
        
        if selected_category != "すべて":
            sql_monthly += " AND i.category = ?"
            params.append(selected_category)
        
        sql_monthly += """
            GROUP BY month, ih.change_type
            ORDER BY month, ih.change_type
        """
        
        cursor.execute(sql_monthly, params)
        monthly_data = [dict(row) for row in cursor.fetchall()]
        
        if monthly_data:
            df_monthly = pd.DataFrame(monthly_data)
            
            # ピボット形式に変換
            pivot_data = {}
            for month in df_monthly['month'].unique():
                month_data = df_monthly[df_monthly['month'] == month]
                pivot_data[month] = {
                    '月': month
                }
                for action in action_types:
                    action_data = month_data[month_data['action'] == action]
                    if not action_data.empty:
                        pivot_data[month][f'{action}_数量'] = int(action_data.iloc[0]['total_quantity'])
                        pivot_data[month][f'{action}_金額'] = int(action_data.iloc[0]['total_amount'])
                    else:
                        pivot_data[month][f'{action}_数量'] = 0
                        pivot_data[month][f'{action}_金額'] = 0
            
            df_display = pd.DataFrame(list(pivot_data.values()))
            
            # 列順を固定
            columns_order = ['月']
            for action in ['OUT', 'DISPOSE']:
                if action in action_types:
                    columns_order.extend([f'{action}_数量', f'{action}_金額'])
            df_display = df_display[columns_order]
            
            st.dataframe(df_display, use_container_width=True, height=300)
            
            # CSV出力
            csv_data = df_display.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            filename = f"monthly_summary_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 月別サマリCSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv"
            )
        else:
            st.info("該当するデータがありません")
        
        st.divider()
        
        # 部署別×月別集計
        st.subheader("🏢 部署別×月別集計")
        
        sql_dept_monthly = f"""
            SELECT 
                strftime('%Y-%m', ih.created_at) as month,
                ih.department,
                ih.change_type as action,
                SUM(ABS(ih.quantity)) as total_quantity,
                SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
            FROM inventory_history ih
            LEFT JOIN items i ON ih.item_id = i.id
            WHERE ih.change_type IN ('{action_filter}')
              AND strftime('%Y-%m', ih.created_at) >= ?
              AND strftime('%Y-%m', ih.created_at) <= ?
        """
        
        params = [start_month, end_month]
        
        if selected_dept != "すべて":
            sql_dept_monthly += " AND ih.department = ?"
            params.append(selected_dept)
        
        if selected_category != "すべて":
            sql_dept_monthly += " AND i.category = ?"
            params.append(selected_category)
        
        sql_dept_monthly += """
            GROUP BY month, ih.department, ih.change_type
            ORDER BY month, ih.department, ih.change_type
        """
        
        cursor.execute(sql_dept_monthly, params)
        dept_monthly_data = [dict(row) for row in cursor.fetchall()]
        
        if dept_monthly_data:
            df_dept = pd.DataFrame(dept_monthly_data)
            
            # ピボット形式に変換
            pivot_data = {}
            for _, row in df_dept.iterrows():
                key = (row['month'], row['department'])
                if key not in pivot_data:
                    pivot_data[key] = {
                        '月': row['month'],
                        '部署': row['department'] or '未設定'
                    }
                    for action in action_types:
                        pivot_data[key][f'{action}_数量'] = 0
                        pivot_data[key][f'{action}_金額'] = 0
                
                action = row['action']
                pivot_data[key][f'{action}_数量'] = int(row['total_quantity'])
                pivot_data[key][f'{action}_金額'] = int(row['total_amount'])
            
            df_display_dept = pd.DataFrame(list(pivot_data.values()))
            
            # 列順を固定
            columns_order = ['月', '部署']
            for action in ['OUT', 'DISPOSE']:
                if action in action_types:
                    columns_order.extend([f'{action}_数量', f'{action}_金額'])
            df_display_dept = df_display_dept[columns_order]
            
            st.dataframe(df_display_dept, use_container_width=True, height=400)
            
            # 集計サマリ
            col1, col2, col3 = st.columns(3)
            with col1:
                total_qty = sum(df_display_dept[f'{action}_数量'].sum() for action in action_types)
                st.metric("合計数量", f"{int(total_qty):,}")
            with col2:
                total_amt = sum(df_display_dept[f'{action}_金額'].sum() for action in action_types)
                st.metric("合計金額", f"¥{int(total_amt):,}")
            with col3:
                dept_count = df_display_dept['部署'].nunique()
                st.metric("対象部署数", f"{dept_count}")
            
            # CSV出力
            csv_data = df_display_dept.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            filename = f"dept_monthly_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 部署別×月別CSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv"
            )
        else:
            st.info("該当するデータがありません")
        
        st.divider()
        
        # カテゴリ別廃棄集計（DISPOSE選択時のみ）
        if 'DISPOSE' in action_types:
            st.subheader("🗑️ カテゴリ別廃棄集計")
            
            sql_category = f"""
                SELECT 
                    i.category,
                    SUM(ABS(ih.quantity)) as total_quantity,
                    SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount,
                    COUNT(DISTINCT ih.id) as disposal_count
                FROM inventory_history ih
                LEFT JOIN items i ON ih.item_id = i.id
                WHERE ih.change_type = 'DISPOSE'
                  AND strftime('%Y-%m', ih.created_at) >= ?
                  AND strftime('%Y-%m', ih.created_at) <= ?
            """
            
            params = [start_month, end_month]
            
            if selected_dept != "すべて":
                sql_category += " AND ih.department = ?"
                params.append(selected_dept)
            
            if selected_category != "すべて":
                sql_category += " AND i.category = ?"
                params.append(selected_category)
            
            sql_category += """
                GROUP BY i.category
                ORDER BY total_amount DESC
            """
            
            cursor.execute(sql_category, params)
            category_data = [dict(row) for row in cursor.fetchall()]
            
            if category_data:
                df_category = pd.DataFrame(category_data)
                
                df_category['category'] = df_category['category'].fillna('未分類')
                
                display_df = pd.DataFrame({
                    'カテゴリ': df_category['category'],
                    '廃棄数量': df_category['total_quantity'].astype(int),
                    '廃棄金額': df_category['total_amount'].astype(int),
                    '廃棄回数': df_category['disposal_count'].astype(int)
                })
                
                st.dataframe(display_df, use_container_width=True, height=300)
                
                # カテゴリ別サマリ
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("総廃棄数量", f"{int(df_category['total_quantity'].sum()):,}")
                with col2:
                    st.metric("総廃棄金額", f"¥{int(df_category['total_amount'].sum()):,}")
                with col3:
                    st.metric("カテゴリ数", f"{len(df_category)}")
                
                # CSV出力
                csv_data = display_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                filename = f"category_disposal_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
                
                st.download_button(
                    label="📥 カテゴリ別廃棄CSV出力",
                    data=csv_data,
                    file_name=filename,
                    mime="text/csv"
                )
            else:
                st.info("廃棄データがありません")

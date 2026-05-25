"""部署管理ページ"""

import streamlit as st

from repositories.department_repo import (
    list_departments,
    count_departments,
    get_department_by_id,
    create_department,
    update_department_name,
    update_department_status,
)
from ui.components.refresh_button import show_refresh_button
from utils.auth import require_role


def show_department_management_page():
    """部署マスタ管理ページ（管理者専用）- テーブル形式 + 検索 + ページング"""
    st.header("🏢 部署管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "部署管理は管理者のみ使用できます"):
        return
    
    # セクション切替（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["📋 部署一覧", "➕ 新規追加"],
        horizontal=True,
        key="departments_section",
    )
    
    # ========== タブ1: 部署一覧・編集 ==========
    if section == "📋 部署一覧":
        # === 検索・フィルタ ===
        st.subheader("🔍 検索・フィルタ")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search_query = st.text_input(
                "検索",
                placeholder="部署名で検索",
                key="dept_search"
            )
        with col2:
            show_inactive = st.checkbox("無効も表示", value=False, key="dept_show_inactive")
        with col3:
            page_size = st.selectbox("表示件数", [10, 25, 50, 100], index=1, key="dept_page_size")
        
        # ページング用のセッションステート
        if "dept_page" not in st.session_state:
            st.session_state.dept_page = 0
        
        # 検索条件変更時はページをリセット
        current_filters = f"{search_query}_{show_inactive}_{page_size}"
        if st.session_state.get("dept_prev_filters") != current_filters:
            st.session_state.dept_page = 0
            st.session_state.dept_prev_filters = current_filters
        
        # 件数取得
        total_count = count_departments(include_inactive=show_inactive, search_query=search_query)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        
        # ページが範囲外なら調整
        if st.session_state.dept_page >= total_pages:
            st.session_state.dept_page = max(0, total_pages - 1)
        
        offset = st.session_state.dept_page * page_size
        
        # データ取得
        departments = list_departments(
            include_inactive=show_inactive,
            search_query=search_query,
            limit=page_size,
            offset=offset
        )
        
        # === ページング UI ===
        st.caption(f"📊 全{total_count}件中 {offset + 1}〜{min(offset + page_size, total_count)}件を表示")
        
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ 前へ", disabled=st.session_state.dept_page == 0, key="dept_prev"):
                st.session_state.dept_page -= 1
                st.rerun()
        with col_page:
            st.write(f"ページ {st.session_state.dept_page + 1} / {total_pages}")
        with col_next:
            if st.button("次へ ▶", disabled=st.session_state.dept_page >= total_pages - 1, key="dept_next"):
                st.session_state.dept_page += 1
                st.rerun()
        
        # === テーブル表示 ===
        if departments:
            import pandas as pd
            
            # データフレーム作成
            df = pd.DataFrame(departments)
            
            # 表示用に列を整形
            display_df = pd.DataFrame({
                "登録番号": df["id"],
                "部署名": df["name"],
                "状態": df["is_active"].apply(lambda x: "✅ 有効" if x else "🔴 無効")
            })
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "登録番号": st.column_config.NumberColumn("登録番号", width="small"),
                    "部署名": st.column_config.TextColumn("部署名", width="large"),
                    "状態": st.column_config.TextColumn("状態", width="small"),
                }
            )
            
            # === 行選択（登録番号入力）→ 詳細表示 ===
            st.divider()
            st.subheader("📝 詳細表示・編集")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_id = st.number_input(
                    "登録番号を入力して詳細表示",
                    min_value=0,
                    value=st.session_state.get("dept_selected_id", 0),
                    step=1,
                    key="dept_id_input"
                )
            with col2:
                if st.button("🔍 詳細を表示", key="dept_show_detail"):
                    st.session_state.dept_selected_id = selected_id
                    st.rerun()
            
            # 詳細パネル
            if st.session_state.get("dept_selected_id"):
                dept = get_department_by_id(st.session_state.dept_selected_id)
                
                if dept:
                    st.info(f"**部署詳細: {dept['name']}** (登録番号: {dept['id']})")
                    
                    st.write(f"**現在の状態:** {'✅ 有効' if dept['is_active'] else '🔴 無効'}")
                    
                    # 編集フォーム
                    with st.expander("✏️ 名称変更", expanded=False):
                        with st.form(f"edit_dept_form_{dept['id']}"):
                            edit_name = st.text_input("部署名 *", value=dept['name'])
                            
                            if st.form_submit_button("💾 更新", use_container_width=True, type="primary"):
                                if not edit_name.strip():
                                    st.error("❌ 部署名は必須です")
                                else:
                                    result = update_department_name(dept['id'], edit_name.strip())
                                    if result['success']:
                                        st.success(result['message'])
                                        st.rerun()
                                    else:
                                        st.error(result['message'])
                    
                    # 有効/無効切替ボタン
                    if dept['is_active']:
                        if st.button("🚫 無効化", key=f"deactivate_dept_{dept['id']}"):
                            result = update_department_status(dept['id'], 0)
                            if result['success']:
                                st.success(result['message'])
                                st.rerun()
                            else:
                                st.error(result['message'])
                    else:
                        if st.button("✅ 有効化", key=f"activate_dept_{dept['id']}"):
                            result = update_department_status(dept['id'], 1)
                            if result['success']:
                                st.success(result['message'])
                                st.rerun()
                            else:
                                st.error(result['message'])
                else:
                    st.warning(f"⚠️ 登録番号 {st.session_state.dept_selected_id} の部署は見つかりませんでした")
        else:
            st.info("📭 条件に一致する部署がありません")
    
    # ========== タブ2: 新規追加 ==========
    if section == "➕ 新規追加":
        st.subheader("➕ 新規部署追加")
        
        with st.form("create_dept_form", clear_on_submit=True):
            new_dept_name = st.text_input(
                "部署名 *",
                placeholder="例: 総務部",
                help="新規作成する部署名（重複不可）"
            )
            
            submitted = st.form_submit_button("✅ 部署を追加", type="primary", use_container_width=True)
            
            if submitted:
                if not new_dept_name or not new_dept_name.strip():
                    st.error("❌ 部署名を入力してください")
                else:
                    result = create_department(new_dept_name.strip())
                    if result["success"]:
                        st.success(result["message"])
                        st.balloons()
                    else:
                        st.error(result["message"])

"""ユーザー管理ページ"""

import streamlit as st

from utils.auth import require_role, get_current_user
from utils.validation import (
    create_validation_result,
    validate_alphanumeric,
    validate_required_string,
    validate_form_and_show_errors,
)
from utils.logger import log_info
from repositories.user_repo import (
    list_users,
    count_users,
    create_user,
    update_user_full,
    get_user_by_id,
)
from repositories.department_repo import get_all_departments
from ui.components.refresh_button import show_refresh_button


def show_user_management_page():
    """ユーザー管理ページ（管理者専用）- テーブル形式 + 検索 + ページング"""
    st.header("👥 ユーザー管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）
    if not require_role("ADMIN", "ユーザー管理は管理者のみ使用できます"):
        return
        return
    
    # 部署一覧を取得（有効なもののみ）
    departments = get_all_departments(active_only=True)
    dept_options = [(d['id'], d['name']) for d in departments]
    dept_names = ["すべて"] + [d['name'] for d in departments]
    
    # セクション切替（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["📋 ユーザー一覧", "➕ 新規作成"],
        horizontal=True,
        key="users_section",
    )
    
    # ========== タブ1: ユーザー一覧・編集 ==========
    if section == "📋 ユーザー一覧":
        # === 検索・フィルタ ===
        st.subheader("🔍 検索・フィルタ")
        
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            search_query = st.text_input(
                "検索",
                placeholder="ユーザーID、表示名で検索",
                key="user_search"
            )
        with col2:
            role_filter = st.selectbox(
                "権限",
                options=["すべて", "ADMIN", "USER", "GUEST"],
                key="user_role_filter"
            )
        with col3:
            dept_filter = st.selectbox(
                "部署",
                options=dept_names,
                key="user_dept_filter"
            )
        with col4:
            show_inactive = st.checkbox("無効も表示", value=False, key="user_show_inactive")
        
        page_size = st.selectbox("表示件数", [10, 25, 50, 100], index=1, key="user_page_size")
        
        # ページング用のセッションステート
        if "user_page" not in st.session_state:
            st.session_state.user_page = 0
        
        # 検索条件変更時はページをリセット
        current_filters = f"{search_query}_{role_filter}_{dept_filter}_{show_inactive}_{page_size}"
        if st.session_state.get("user_prev_filters") != current_filters:
            st.session_state.user_page = 0
            st.session_state.user_prev_filters = current_filters
        
        # 件数取得
        total_count = count_users(
            include_inactive=show_inactive,
            search_query=search_query,
            role_filter=role_filter,
            department_filter=dept_filter
        )
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        
        # ページが範囲外なら調整
        if st.session_state.user_page >= total_pages:
            st.session_state.user_page = max(0, total_pages - 1)
        
        offset = st.session_state.user_page * page_size
        
        # データ取得
        users = list_users(
            include_inactive=show_inactive,
            search_query=search_query,
            role_filter=role_filter,
            department_filter=dept_filter,
            limit=page_size,
            offset=offset
        )
        
        # === ページング UI ===
        st.caption(f"📊 全{total_count}件中 {offset + 1}〜{min(offset + page_size, total_count)}件を表示")
        
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ 前へ", disabled=st.session_state.user_page == 0, key="user_prev"):
                st.session_state.user_page -= 1
                st.rerun()
        with col_page:
            st.write(f"ページ {st.session_state.user_page + 1} / {total_pages}")
        with col_next:
            if st.button("次へ ▶", disabled=st.session_state.user_page >= total_pages - 1, key="user_next"):
                st.session_state.user_page += 1
                st.rerun()
        
        # === テーブル表示 ===
        if users:
            import pandas as pd
            
            # 権限ラベル変換
            role_labels = {'ADMIN': '👑 管理者', 'USER': '👤 ユーザー', 'GUEST': '👻 ゲスト'}
            
            # データフレーム作成
            df = pd.DataFrame(users)
            
            # 表示用に列を整形
            display_df = pd.DataFrame({
                "登録番号": df["id"],
                "ユーザーID": df["username"],
                "表示名": df["display_name"],
                "部署": df["department_name"].fillna(df["department"]).fillna("未設定"),
                "権限": df["user_role"].apply(lambda x: role_labels.get(x, x)),
                "状態": df["is_active"].apply(lambda x: "✅ 有効" if x else "🔴 無効")
            })
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "登録番号": st.column_config.NumberColumn("登録番号", width="small"),
                    "ユーザーID": st.column_config.TextColumn("ユーザーID", width="small"),
                    "表示名": st.column_config.TextColumn("表示名", width="medium"),
                    "部署": st.column_config.TextColumn("部署", width="medium"),
                    "権限": st.column_config.TextColumn("権限", width="small"),
                    "状態": st.column_config.TextColumn("状態", width="small"),
                }
            )
            
            st.caption("💡 「登録番号」はシステム内部のID番号です。ユーザーIDとは異なります。")
            
            # === 行選択（登録番号入力）→ 詳細表示 ===
            st.divider()
            st.subheader("📝 詳細表示・編集")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_id = st.number_input(
                    "登録番号を入力して詳細表示",
                    min_value=0,
                    value=st.session_state.get("user_selected_id", 0),
                    step=1,
                    key="user_id_input"
                )
            with col2:
                if st.button("🔍 詳細を表示", key="user_show_detail"):
                    st.session_state.user_selected_id = selected_id
                    st.rerun()
            
            # 詳細パネル
            if st.session_state.get("user_selected_id"):
                user = get_user_by_id(st.session_state.user_selected_id)
                current_user_id = get_current_user().get("id")
                
                if user:
                    st.info(f"**ユーザー詳細: {user['display_name']}** (登録番号: {user['id']})")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**ユーザーID:** {user['username']}")
                        st.write(f"**表示名:** {user['display_name']}")
                        st.write(f"**部署:** {user.get('department_name') or user.get('department') or '未設定'}")
                    with col2:
                        role_labels = {'ADMIN': '👑 管理者', 'USER': '👤 ユーザー', 'GUEST': '👻 ゲスト'}
                        st.write(f"**権限:** {role_labels.get(user['user_role'], user['user_role'])}")
                        st.write(f"**状態:** {'✅ 有効' if user['is_active'] else '🔴 無効'}")
                        st.write(f"**作成日:** {user.get('created_at', 'N/A')}")
                    
                    # 自分自身の場合は編集不可
                    if user['id'] == current_user_id:
                        st.warning("⚠️ 自分自身のアカウントは編集できません")
                    else:
                        # 編集フォーム
                        with st.expander("✏️ 編集", expanded=False):
                            with st.form(f"edit_user_form_{user['id']}"):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    edit_display_name = st.text_input(
                                        "表示名 *",
                                        value=user['display_name']
                                    )
                                    
                                    # 部署選択
                                    if dept_options:
                                        current_dept_id = user.get('department_id')
                                        dept_ids = [d[0] for d in dept_options]
                                        try:
                                            current_index = dept_ids.index(current_dept_id) if current_dept_id in dept_ids else 0
                                        except ValueError:
                                            current_index = 0
                                        
                                        edit_dept_index = st.selectbox(
                                            "部署 *",
                                            options=range(len(dept_options)),
                                            format_func=lambda i: dept_options[i][1],
                                            index=current_index
                                        )
                                        edit_department_id = dept_options[edit_dept_index][0]
                                    else:
                                        st.warning("⚠️ 部署未登録")
                                        edit_department_id = None
                                    
                                    edit_new_password = st.text_input(
                                        "新しいパスワード（変更時のみ入力）",
                                        type="password",
                                        value=""
                                    )
                                
                                with col2:
                                    role_options = ['ADMIN', 'USER', 'GUEST']
                                    try:
                                        current_role_index = role_options.index(user['user_role'])
                                    except ValueError:
                                        current_role_index = 1
                                    
                                    edit_role = st.selectbox(
                                        "権限 *",
                                        options=role_options,
                                        index=current_role_index
                                    )
                                    
                                    edit_is_active = st.radio(
                                        "状態 *",
                                        options=[1, 0],
                                        index=0 if user['is_active'] else 1,
                                        format_func=lambda x: "✅ 有効" if x == 1 else "❌ 無効",
                                        horizontal=True
                                    )
                                
                                if st.form_submit_button("💾 更新", use_container_width=True, type="primary"):
                                    result = update_user_full(
                                        user_id=user['id'],
                                        display_name=edit_display_name,
                                        department_id=edit_department_id,
                                        user_role=edit_role,
                                        is_active=edit_is_active,
                                        new_password=edit_new_password if edit_new_password.strip() else None
                                    )
                                    if result['success']:
                                        st.success(result['message'])
                                        st.rerun()
                                    else:
                                        st.error(result['message'])
                else:
                    st.warning(f"⚠️ 登録番号 {st.session_state.user_selected_id} のユーザーは見つかりませんでした")
        else:
            st.info("📭 条件に一致するユーザーがいません")
    
    # ========== タブ2: 新規作成 ==========
    if section == "➕ 新規作成":
        st.subheader("➕ 新規ユーザー作成")
        
        with st.form("create_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                new_username = st.text_input(
                    "ユーザーID *",
                    placeholder="例: yamada",
                    help="ログインに使用するID（英数字）※作成後は変更不可"
                )
                
                new_password = st.text_input(
                    "パスワード *",
                    type="password",
                    placeholder="8文字以上推奨",
                    help="ログインに使用するパスワード"
                )
                
                new_password_confirm = st.text_input(
                    "パスワード（確認） *",
                    type="password",
                    placeholder="もう一度入力",
                    help="確認のため再入力"
                )
            
            with col2:
                new_display_name = st.text_input(
                    "表示名 *",
                    placeholder="例: 山田太郎",
                    help="画面に表示される名前"
                )
                
                # 部署をプルダウンで選択
                if dept_options:
                    selected_dept_index = st.selectbox(
                        "部署 *",
                        options=range(len(dept_options)),
                        format_func=lambda i: dept_options[i][1],
                        index=0,
                        help="所属部署を選択"
                    )
                    selected_department_id = dept_options[selected_dept_index][0]
                else:
                    st.warning("⚠️ 部署が登録されていません")
                    selected_department_id = None
                
                new_role = st.selectbox(
                    "権限 *",
                    options=['USER', 'GUEST', 'ADMIN'],
                    index=0,
                    help="ADMIN: 全操作可 / USER: 入出庫可 / GUEST: 出庫申請のみ"
                )
            
            st.divider()
            
            submitted = st.form_submit_button("✅ ユーザーを作成", type="primary", use_container_width=True)
            
            if submitted:
                # 共通バリデーション使用
                result = create_validation_result()
                
                # ユーザーID（必須・英数字のみ）
                ok, username_clean, err = validate_alphanumeric(new_username, field_name="ユーザーID")
                if not ok:
                    result.add_error(err)
                else:
                    result.set_value("username", username_clean)
                
                # パスワード（必須・4文字以上）
                ok, password_clean, err = validate_required_string(new_password, field_name="パスワード", min_length=4, normalize=False)
                if not ok:
                    result.add_error(err)
                else:
                    result.set_value("password", new_password)  # パスワードはそのまま
                
                # パスワード確認
                if new_password != new_password_confirm:
                    result.add_error("パスワードが一致しません")
                
                # 表示名（必須）
                ok, display_name_clean, err = validate_required_string(new_display_name, field_name="表示名", normalize=False)
                if not ok:
                    result.add_error(err)
                else:
                    result.set_value("display_name", display_name_clean)
                
                # 部署
                if selected_department_id is None:
                    result.add_error("部署を選択してください")
                
                # バリデーションエラーがあれば表示して終了
                if not validate_form_and_show_errors(result):
                    pass  # エラー表示のみでformは続行
                else:
                    # ユーザー作成（department_idを使用）
                    create_result = create_user(
                        username=result.get_value("username"),
                        password=result.get_value("password"),
                        display_name=result.get_value("display_name"),
                        department_id=selected_department_id,
                        user_role=new_role
                    )
                    
                    if create_result["success"]:
                        log_info("ユーザー作成", username=result.get_value("username"))
                        st.success(create_result["message"])
                        st.balloons()
                    else:
                        st.error(create_result["message"])

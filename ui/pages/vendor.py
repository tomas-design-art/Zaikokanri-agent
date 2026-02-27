"""業者管理ページ"""

import streamlit as st

from repositories.vendor_repo import (
    list_vendors,
    count_vendors,
    get_vendor_by_id,
    insert_vendor,
    update_vendor,
    deactivate_vendor,
    activate_vendor,
)
from ui.components.refresh_button import show_refresh_button
from utils.auth import require_role


def show_vendor_management_page():
    """業者管理ページ（管理者専用）- テーブル形式 + 検索 + ページング"""
    st.header("🏢 業者管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "業者管理は管理者のみ使用できます"):
        return
    
    # タブで「一覧」「新規登録」を分ける
    tab1, tab2 = st.tabs(["📋 業者一覧", "➕ 新規登録"])
    
    with tab1:
        # === 検索・フィルタ ===
        st.subheader("🔍 検索・フィルタ")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search_query = st.text_input(
                "検索",
                placeholder="業者名、業者コード、電話番号、メールアドレスで検索",
                key="vendor_search"
            )
        with col2:
            show_inactive = st.checkbox("無効も表示", value=False, key="vendor_show_inactive")
        with col3:
            page_size = st.selectbox("表示件数", [10, 25, 50, 100], index=1, key="vendor_page_size")
        
        # ページング用のセッションステート
        if "vendor_page" not in st.session_state:
            st.session_state.vendor_page = 0
        
        # 検索条件変更時はページをリセット
        current_filters = f"{search_query}_{show_inactive}_{page_size}"
        if st.session_state.get("vendor_prev_filters") != current_filters:
            st.session_state.vendor_page = 0
            st.session_state.vendor_prev_filters = current_filters
        
        # 件数取得
        total_count = count_vendors(include_inactive=show_inactive, search_query=search_query)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        
        # ページが範囲外なら調整
        if st.session_state.vendor_page >= total_pages:
            st.session_state.vendor_page = max(0, total_pages - 1)
        
        offset = st.session_state.vendor_page * page_size
        
        # データ取得
        vendors = list_vendors(
            include_inactive=show_inactive,
            search_query=search_query,
            limit=page_size,
            offset=offset
        )
        
        # === ページング UI ===
        st.caption(f"📊 全{total_count}件中 {offset + 1}〜{min(offset + page_size, total_count)}件を表示")
        
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ 前へ", disabled=st.session_state.vendor_page == 0, key="vendor_prev"):
                st.session_state.vendor_page -= 1
                st.rerun()
        with col_page:
            st.write(f"ページ {st.session_state.vendor_page + 1} / {total_pages}")
        with col_next:
            if st.button("次へ ▶", disabled=st.session_state.vendor_page >= total_pages - 1, key="vendor_next"):
                st.session_state.vendor_page += 1
                st.rerun()
        
        # === テーブル表示 ===
        if vendors:
            import pandas as pd
            
            # データフレーム作成
            df = pd.DataFrame(vendors)
            
            # 表示用に列を整形
            display_df = pd.DataFrame({
                "登録番号": df["id"],
                "業者コード": df["vendor_code"],
                "業者名": df["vendor_name"],
                "電話番号": df["phone"].fillna(""),
                "メール": df["email"].fillna(""),
                "状態": df["is_active"].apply(lambda x: "✅ 有効" if x else "🔴 無効")
            })
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "登録番号": st.column_config.NumberColumn("登録番号", width="small"),
                    "業者コード": st.column_config.TextColumn("業者コード", width="small"),
                    "業者名": st.column_config.TextColumn("業者名", width="medium"),
                    "電話番号": st.column_config.TextColumn("電話番号", width="small"),
                    "メール": st.column_config.TextColumn("メール", width="medium"),
                    "状態": st.column_config.TextColumn("状態", width="small"),
                }
            )
            
            # === 行選択（登録番号入力）→ 詳細表示 ===
            st.divider()
            st.subheader("📝 詳細表示・編集")
            
            vendor_ids = [v["id"] for v in vendors]
            
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_id = st.number_input(
                    "登録番号を入力して詳細表示",
                    min_value=0,
                    value=st.session_state.get("vendor_selected_id", 0),
                    step=1,
                    key="vendor_id_input"
                )
            with col2:
                if st.button("🔍 詳細を表示", key="vendor_show_detail"):
                    st.session_state.vendor_selected_id = selected_id
                    st.rerun()
            
            # 詳細パネル
            if st.session_state.get("vendor_selected_id"):
                vendor = get_vendor_by_id(st.session_state.vendor_selected_id)
                
                if vendor:
                    st.info(f"**業者詳細: {vendor['vendor_name']}** (登録番号: {vendor['id']})")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**業者コード:** {vendor['vendor_code']}")
                        st.write(f"**業者名:** {vendor['vendor_name']}")
                        st.write(f"**所在地:** {vendor.get('address') or '未登録'}")
                    with col2:
                        st.write(f"**電話番号:** {vendor.get('phone') or '未登録'}")
                        st.write(f"**メール:** {vendor.get('email') or '未登録'}")
                        st.write(f"**状態:** {'✅ 有効' if vendor['is_active'] else '🔴 無効'}")
                    
                    # 編集フォーム
                    with st.expander("✏️ 編集", expanded=False):
                        with st.form(f"edit_vendor_form_{vendor['id']}"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                edit_code = st.text_input("業者コード *", value=vendor['vendor_code'])
                                edit_name = st.text_input("業者名 *", value=vendor['vendor_name'])
                                edit_address = st.text_input("所在地", value=vendor.get('address') or "")
                            
                            with col2:
                                edit_phone = st.text_input("電話番号", value=vendor.get('phone') or "")
                                edit_email = st.text_input("メールアドレス", value=vendor.get('email') or "")
                            
                            if st.form_submit_button("💾 更新", use_container_width=True, type="primary"):
                                if not edit_code or not edit_name:
                                    st.error("❌ 業者コードと業者名は必須です")
                                else:
                                    result = update_vendor(
                                        vendor_id=vendor['id'],
                                        vendor_code=edit_code,
                                        vendor_name=edit_name,
                                        address=edit_address,
                                        phone=edit_phone,
                                        email=edit_email
                                    )
                                    if result['success']:
                                        st.success(result['message'])
                                        st.rerun()
                                    else:
                                        st.error(result['message'])
                    
                    # 有効/無効切替ボタン
                    if vendor['is_active']:
                        if st.button("🚫 無効化", key=f"deactivate_vendor_{vendor['id']}"):
                            result = deactivate_vendor(vendor['id'])
                            if result['success']:
                                st.success(result['message'])
                                st.rerun()
                            else:
                                st.error(result['message'])
                    else:
                        if st.button("✅ 有効化", key=f"activate_vendor_{vendor['id']}"):
                            result = activate_vendor(vendor['id'])
                            if result['success']:
                                st.success(result['message'])
                                st.rerun()
                            else:
                                st.error(result['message'])
                else:
                    st.warning(f"⚠️ 登録番号 {st.session_state.vendor_selected_id} の業者は見つかりませんでした")
        else:
            st.info("📭 条件に一致する業者がありません")
    
    with tab2:
        # === 新規登録フォーム ===
        st.subheader("➕ 新規業者登録")
        
        # 成功メッセージの表示（フォームの外）
        if "vendor_register_success" in st.session_state:
            st.success(st.session_state.vendor_register_success)
            del st.session_state.vendor_register_success
        
        # フォームリセット用のキーを生成
        if "vendor_form_reset_counter" not in st.session_state:
            st.session_state.vendor_form_reset_counter = 0
        
        with st.form(key=f"new_vendor_form_{st.session_state.vendor_form_reset_counter}"):
            col1, col2 = st.columns(2)
            
            with col1:
                vendor_code = st.text_input("業者コード *", placeholder="例: V001")
                vendor_name = st.text_input("業者名 *", placeholder="例: ○○商事")
                address = st.text_input("所在地", placeholder="例: 東京都千代田区1-2-3")
            
            with col2:
                phone = st.text_input("電話番号", placeholder="例: 03-1234-5678")
                email = st.text_input("メールアドレス", placeholder="例: info@example.co.jp")
            
            st.caption("* は必須項目です")
            st.caption("💡 発注書の自動作成に使用される情報です")
            
            submitted = st.form_submit_button("✅ 登録", use_container_width=True, type="primary")
            
            if submitted:
                # バリデーション
                if not vendor_code or not vendor_name:
                    st.error("❌ 業者コードと業者名は必須です")
                else:
                    result = insert_vendor(
                        vendor_code=vendor_code,
                        vendor_name=vendor_name,
                        address=address if address else "",
                        phone=phone if phone else "",
                        email=email if email else ""
                    )
                    
                    if result['success']:
                        st.session_state.vendor_register_success = result['message']
                        st.session_state.vendor_form_reset_counter += 1
                        st.rerun()
                    else:
                        st.error(result['message'])

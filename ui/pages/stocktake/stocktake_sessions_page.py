"""
棚卸しセッション管理ページ

セッションの作成・一覧表示・クローズ・削除を提供する。
"""

import streamlit as st
from datetime import datetime, timedelta
from utils.date_utils import JST
from state.keys import K
from utils.auth import get_current_user, is_admin
from services.stocktake_service import (
    start_new_session,
    close_session,
    get_stocktake_sessions,
    get_stocktake_session_by_id,
    get_session_progress,
    delete_stocktake_session,
)

JST = JST  # imported from utils.date_utils above


def show_stocktake_sessions_page():
    """棚卸しセッション管理ページ"""
    st.header("📋 棚卸しセッション管理")
    
    user = get_current_user()
    if not user:
        st.warning("ログインしてください")
        return
    
    # 成功・エラーメッセージ表示
    if K.STOCKTAKE_SUCCESS_MSG in st.session_state:
        st.success(st.session_state.pop(K.STOCKTAKE_SUCCESS_MSG))
    if K.STOCKTAKE_ERROR_MSG in st.session_state:
        st.error(st.session_state.pop(K.STOCKTAKE_ERROR_MSG))
    
    section = st.radio(
        "表示セクション",
        options=["📋 セッション一覧", "➕ 新規作成"],
        horizontal=True,
        key="stocktake_sessions_section",
    )

    if section == "📋 セッション一覧":
        _render_session_list(user)
    else:
        if is_admin():
            _render_create_form(user)
        else:
            st.info("セッション作成は管理者のみ実行できます")


def _render_session_list(user: dict):
    """セッション一覧"""
    # フィルター
    status_filter = st.selectbox(
        "ステータス", ["すべて", "OPEN", "CLOSED"],
        key="session_status_filter"
    )
    
    status = status_filter if status_filter != "すべて" else None
    sessions = get_stocktake_sessions(status=status)
    
    if not sessions:
        st.info("棚卸しセッションがありません")
        return
    
    for session in sessions:
        session_id = session["id"]
        progress = get_session_progress(session_id)
        
        status_emoji = "🟢" if session["status"] == "OPEN" else "🔒"
        
        with st.expander(
            f"{status_emoji} {session['name']} ({session['start_date']}) "
            f"- 進捗: {progress.get('progress_pct', 0)}%",
            expanded=(session["status"] == "OPEN")
        ):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**期間:** {session['start_date']} ～ {session.get('end_date') or '未定'}")
                st.write(f"**作成者:** {session.get('creator_name', '-')}")
            with col2:
                st.write(f"**ステータス:** {session['status']}")
                st.write(f"**作成日:** {session.get('created_at', '-')}")
            with col3:
                total = progress.get("total_items", 0)
                pending = progress.get("pending_count", 0)
                st.metric("対象品目", total)
                st.metric("未入力", pending)
            
            # 進捗バー
            pct = progress.get("progress_pct", 0)
            st.progress(pct / 100, text=f"入力進捗: {pct}%")
            
            # サマリー詳細
            cols = st.columns(5)
            with cols[0]:
                st.metric("入力済", progress.get("counted_count", 0))
            with cols[1]:
                st.metric("確認済", progress.get("verified_count", 0))
            with cols[2]:
                st.metric("承認済", progress.get("approved_count", 0))
            with cols[3]:
                st.metric("反映済", progress.get("applied_count", 0))
            with cols[4]:
                st.metric("差異あり", progress.get("diff_count", 0))
            
            if session.get("note"):
                st.caption(f"📝 {session['note']}")
            
            # アクションボタン
            if session["status"] == "OPEN" and is_admin():
                bcol1, bcol2, bcol3 = st.columns(3)
                with bcol1:
                    if st.button("📝 入力画面へ", key=f"goto_entry_{session_id}"):
                        st.session_state[K.STOCKTAKE_SESSION] = session_id
                        st.session_state[K.PENDING_MENU_ID] = "stocktake_entry"
                        st.rerun()
                with bcol2:
                    if st.button("🔒 セッション終了", key=f"close_{session_id}",
                                 type="secondary"):
                        result = close_session(
                            session_id, 
                            user.get("display_name", ""),
                            user.get("department", "")
                        )
                        if result.get("success"):
                            st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                        else:
                            st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                        st.rerun()
                with bcol3:
                    if st.button("🗑️ 削除", key=f"delete_{session_id}",
                                 type="secondary"):
                        result = delete_stocktake_session(session_id)
                        if result.get("success"):
                            st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                        else:
                            st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                        st.rerun()
            
            elif session["status"] == "OPEN":
                if st.button("📝 入力画面へ", key=f"goto_entry_user_{session_id}"):
                    st.session_state[K.STOCKTAKE_SESSION] = session_id
                    st.session_state[K.PENDING_MENU_ID] = "stocktake_entry"
                    st.rerun()


def _render_create_form(user: dict):
    """新規セッション作成フォーム"""
    st.subheader("新規棚卸しセッション")
    
    today = datetime.now(JST).date()
    
    with st.form("create_stocktake_session"):
        name = st.text_input(
            "セッション名 *",
            value=f"{today.strftime('%Y年%m月')}定期棚卸し",
            help="例: 2026年2月定期棚卸し"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            end_date = st.date_input(
                "終了予定日",
                value=today + timedelta(days=7),
                help="省略可"
            )
        with col2:
            note = st.text_area("備考", height=80)
        
        st.info("💡 セッション作成時に、棚卸し対象の全物品（is_inventory_target=1）の記録が自動生成されます")
        
        submitted = st.form_submit_button("🚀 セッション作成", type="primary",
                                          use_container_width=True)
    
    if submitted:
        if not name.strip():
            st.error("❌ セッション名は必須です")
            return
        
        result = start_new_session(
            name=name.strip(),
            end_date=str(end_date) if end_date else None,
            note=note.strip(),
            created_by=user.get("id"),
        )
        if result.get("success"):
            st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
            st.session_state[K.STOCKTAKE_SESSION] = result.get("session_id")
            st.rerun()
        else:
            st.error(result.get("message", "エラーが発生しました"))

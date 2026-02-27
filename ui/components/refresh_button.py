"""
更新ボタン・リフレッシュコンポーネント
"""

import os
import time
import streamlit as st


def refresh_data():
    """最新データの再取得（キャッシュクリア+リラン）"""
    st.cache_data.clear()
    st.cache_resource.clear()
    st.session_state["refresh_token"] = time.time()
    st.rerun()


def show_refresh_button():
    """各ページ右上に表示する更新ボタン"""
    from config.settings import DB_PATH
    col1, col2 = st.columns([6, 1])
    with col1:
        st.caption(f"🗄️ DB: {os.path.abspath(DB_PATH)}")
    with col2:
        if st.button("🔄 更新", key="refresh_btn", help="最新データを再取得します"):
            refresh_data()

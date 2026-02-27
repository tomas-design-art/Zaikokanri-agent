"""
ログイン画面モジュール

ログイン/ログアウトの処理とログイン画面UIを提供する。
"""

import streamlit as st
from repositories.user_repo import authenticate_user
from utils.auth import get_current_user
from utils.logger import log_login


def do_login(username: str, password: str) -> bool:
    """ログイン処理"""
    user = authenticate_user(username, password)
    if user:
        st.session_state.logged_in = True
        st.session_state.current_user = user
        log_login(user.get("display_name", username), success=True)
        return True
    log_login(username, success=False)
    return False


def do_logout():
    """ログアウト処理"""
    st.session_state.logged_in = False
    st.session_state.current_user = {}


def show_login_page():
    """ログインページを表示"""
    left, center, right = st.columns([3, 2, 3])

    with center:
        st.markdown("""
        <style>
            .big-title {
                font-size: 2.8rem !important;
                text-align: center !important;
                margin-bottom: 2rem !important;
                font-weight: bold !important;
                line-height: 1.2 !important;
                color: inherit !important;
            }
        </style>
        <div class="big-title">📦 在庫管理システム</div>
        """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("## 🔐 ログイン")
        st.write("在庫管理システムにログインしてください。")

        with st.form("login_form"):
            username = st.text_input("ユーザーID", placeholder="例: admin")
            password = st.text_input("パスワード", type="password")
            submitted = st.form_submit_button("ログイン", use_container_width=True, type="primary")

            if submitted:
                if username and password:
                    if do_login(username, password):
                        st.success(f"✅ ようこそ、{get_current_user()['display_name']} さん！")
                        st.rerun()
                    else:
                        st.error("❌ ユーザーIDまたはパスワードが正しくありません")
                else:
                    st.warning("⚠️ ユーザーIDとパスワードを入力してください")

        st.divider()
        st.caption("💡 初期管理者: admin / admin123")

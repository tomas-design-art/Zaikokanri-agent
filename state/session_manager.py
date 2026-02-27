"""
session_state の一元アクセス層

全画面で session_state に直接触れず、このモジュール経由でアクセスする。
型安全・デフォルト値保証・副作用の明確化を目的とする。
"""

import time
import streamlit as st
from state.keys import K


class SessionState:
    """session_state 操作のファサード"""

    # ─── 汎用アクセサ ───

    @staticmethod
    def get(key: str, default=None):
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value):
        st.session_state[key] = value

    @staticmethod
    def pop(key: str, default=None):
        return st.session_state.pop(key, default)

    @staticmethod
    def has(key: str) -> bool:
        return key in st.session_state

    @staticmethod
    def delete(key: str):
        if key in st.session_state:
            del st.session_state[key]

    # ─── 認証 ───

    @staticmethod
    def is_logged_in() -> bool:
        return st.session_state.get(K.LOGGED_IN, False)

    @staticmethod
    def get_current_user() -> dict:
        return st.session_state.get(K.CURRENT_USER, {})

    @staticmethod
    def set_logged_in(user: dict):
        st.session_state[K.LOGGED_IN] = True
        st.session_state[K.CURRENT_USER] = user

    @staticmethod
    def set_logged_out():
        st.session_state[K.LOGGED_IN] = False
        st.session_state[K.CURRENT_USER] = {}

    # ─── メニュー・ナビゲーション ───

    @staticmethod
    def get_menu_id() -> str:
        return st.session_state.get(K.MENU_ID, "")

    @staticmethod
    def set_menu(menu_id: str):
        """メニューIDを設定して画面遷移（リラン前に呼ぶ）"""
        st.session_state[K.MENU_ID] = menu_id
        st.session_state[K.PENDING_MENU_ID] = menu_id
        st.session_state[K.CURRENT_PAGE] = 1
        st.rerun()

    @staticmethod
    def get_current_page() -> int:
        return st.session_state.get(K.CURRENT_PAGE, 1)

    @staticmethod
    def set_current_page(page: int):
        st.session_state[K.CURRENT_PAGE] = page

    # ─── 表示設定 ───

    @staticmethod
    def get_display_size() -> str:
        return st.session_state.get(K.DISPLAY_SIZE, "中")

    @staticmethod
    def set_display_size(size: str):
        st.session_state[K.DISPLAY_SIZE] = size

    # ─── キャッシュ ───

    @staticmethod
    def refresh_data():
        """キャッシュクリア+再読込"""
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state[K.REFRESH_TOKEN] = time.time()
        st.rerun()

    # ─── 初期化 ───

    @staticmethod
    def ensure_defaults():
        """セッションステートの初期値を設定（init_app内で1回呼ぶ）"""
        defaults = {
            K.DISPLAY_SIZE: "中",
            K.CURRENT_PAGE: 1,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

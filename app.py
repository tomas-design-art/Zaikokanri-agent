"""
在庫管理アプリ エントリーポイント

Streamlit ベースのWebアプリケーション。
各機能モジュールへのルーティングを行う薄いエントリーポイント。

起動: streamlit run app.py
"""

import os
import streamlit as st
from config.settings import AI_ENABLED, DB_PATH

# =============================================================================
# インフラ関数（DB初期化・チェック）
# =============================================================================

def check_multiple_db_files():
    """プロジェクト内にinventory.dbファイルが複数存在しないかチェック"""
    project_root = os.path.dirname(__file__)
    db_files = []
    search_dirs = [
        project_root,
        os.path.join(project_root, "data"),
        os.path.join(project_root, "env"),
        os.path.join(project_root, "tests"),
        os.path.join(project_root, "tools"),
    ]
    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            db_path = os.path.join(search_dir, "inventory.db")
            if os.path.exists(db_path):
                db_files.append(os.path.abspath(db_path))

    current_db = os.path.abspath(DB_PATH)
    print(f"[DB_CHECK] 現在のDB: {current_db}")
    print(f"[DB_CHECK] 検出されたinventory.db: {len(db_files)}件")
    for db_file in db_files:
        is_current = " ← 現在使用中" if db_file == current_db else ""
        print(f"  - {db_file}{is_current}")
    if len(db_files) > 1:
        print(f"[DB_CHECK] ⚠️ 警告: inventory.dbが{len(db_files)}個検出されました。")


def init_app():
    """アプリ初期化"""
    st.set_page_config(
        page_title="在庫管理システム",
        page_icon="📦",
        layout="wide"
    )

    # 表示サイズの初期値設定
    if "display_size" not in st.session_state:
        st.session_state.display_size = "中"

    # CSSを適用
    from ui.css import apply_size_css
    apply_size_css(st.session_state.display_size)

    # DB複数存在チェック（初回のみ）
    if "db_check_done" not in st.session_state:
        check_multiple_db_files()
        st.session_state.db_check_done = True

    # セッションステート初期化
    if "initialized" not in st.session_state:
        from db import init_tables
        if not os.path.exists(DB_PATH):
            st.warning("⚠️ データベースが見つかりません。初期化してください。")
            if st.button("データベースを初期化"):
                init_tables()
                st.success("✅ データベースを初期化しました！")
                st.rerun()
        st.session_state.initialized = True


# =============================================================================
# メイン処理
# =============================================================================

def main():
    """メイン処理"""
    init_app()

    from utils.auth import is_logged_in

    # ログインチェック
    if not is_logged_in():
        from ui.login import show_login_page
        show_login_page()
        return

    # サイドバー
    from ui.sidebar import render_sidebar
    with st.sidebar:
        current_menu_id = render_sidebar(ai_enabled=AI_ENABLED)

    # ルーティング
    from ui.router import route
    route(current_menu_id)


# =============================================================================
# set_menu ヘルパー（他モジュールから import される互換関数）
# =============================================================================

def set_menu(menu_id: str):
    """
    メニューIDを設定して画面遷移（リラン）するヘルパー関数

    【重要】画面遷移は必ずこの関数を使用してください。
    """
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1
    st.rerun()


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    main()
else:
    # streamlit run app.py で実行された場合もmainを呼ぶ
    main()

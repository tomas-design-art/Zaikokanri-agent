"""
サイドバーモジュール

ユーザー情報表示・メニュー構成・動的バッジ生成を提供する。
"""

import streamlit as st
from utils.auth import (
    get_current_user, is_admin, is_guest,
    can_inbound, can_adjust,
)
from repositories.pending_repo import get_pending_count
from repositories.disposal_repo import get_disposal_count
from repositories.purchase_request_repo import get_purchase_request_counts
from ui.login import do_logout


def show_user_info_sidebar():
    """サイドバーにユーザー情報を表示"""
    user = get_current_user()
    if user:
        role_badges = {
            "ADMIN": "👑 管理者",
            "USER": "👤 一般ユーザー",
            "GUEST": "👻 ゲスト"
        }
        role_badge = role_badges.get(user.get("user_role", ""), "")
        st.write(f"**{user.get('display_name', '')}**")
        st.caption(f"{user.get('department', '')} / {role_badge}")

        if st.button("🚪 ログアウト", use_container_width=True):
            do_logout()
            st.rerun()


def build_menu_items(ai_enabled: bool) -> list:
    """
    現在のユーザーロールに応じたメニュー項目リストを構築する。
    
    Returns:
        list of (menu_id, label) tuples
    """
    menu_items = []

    if is_guest():
        menu_items.append(("outbound", "➖ 出庫（申請）"))
    else:
        menu_items.append(("inventory", "📦 在庫一覧"))
        menu_items.append(("alert", "🚨 アラート"))
        menu_items.append(("purchase_request", "📝 発注申請"))
        menu_items.append(("disposal_request", "🗑️ 廃棄申請"))

        if can_inbound():
            menu_items.append(("inbound", "➕ 入庫"))

        menu_items.append(("outbound", "➖ 出庫"))
        menu_items.append(("history", "📋 履歴"))
        menu_items.append(("stats", "📊 集計"))

        if ai_enabled:
            menu_items.append(("ai", "🤖 AIアシスタント"))

        if can_inbound():
            menu_items.append(("approval", "✅ 承認管理"))

        if is_admin():
            menu_items.append(("disposal_approval", "✅ 廃棄承認"))
            menu_items.append(("purchase_admin", "✅ 発注申請管理"))

        if can_adjust():
            menu_items.append(("adjust", "🔧 在庫調整"))

        if is_admin():
            menu_items.append(("item_master", "📦 物品マスター管理"))
            menu_items.append(("vendor", "🏢 業者管理"))
            menu_items.append(("users", "👥 ユーザー管理"))
            menu_items.append(("departments", "🏢 部署管理"))
            menu_items.append(("maintenance", "🛠️ メンテナンス"))
            menu_items.append(("demo", "🎭 デモモード"))

    return menu_items


def format_menu_label(menu_id: str, menu_labels: dict) -> str:
    """動的バッジ付きメニューラベルを生成"""
    base_label = menu_labels.get(menu_id, menu_id)

    if menu_id == "approval":
        current_user = get_current_user()
        user_dept_id = current_user.get("department_id")
        if is_admin():
            pending_count = get_pending_count()
        else:
            pending_count = get_pending_count(department_id=user_dept_id)
        if pending_count > 0:
            return f"{base_label} 🔴{pending_count}件"

    elif menu_id == "disposal_approval":
        disposal_pending_count = get_disposal_count(status="PENDING")
        if disposal_pending_count > 0:
            return f"{base_label} 🔴{disposal_pending_count}件"

    elif menu_id == "purchase_admin":
        pr_counts = get_purchase_request_counts()
        pr_pending = pr_counts.get("pending", 0)
        if pr_pending > 0:
            return f"{base_label} 🔴{pr_pending}件"

    return base_label


def migrate_legacy_menu():
    """古い日本語ラベルのmenuステートをIDベースに移行"""
    legacy_map = {
        "📦 在庫一覧": "inventory",
        "🚨 アラート": "alert",
        "📝 発注申請": "purchase_request",
        "🗑️ 廃棄申請": "disposal_request",
        "➕ 入庫": "inbound",
        "➖ 出庫": "outbound",
        "➖ 出庫（申請）": "outbound",
        "📋 履歴": "history",
        "📊 集計": "stats",
        "🤖 AIアシスタント": "ai",
        "🔧 在庫調整": "adjust",
        "📦 物品マスター管理": "item_master",
        "🏢 業者管理": "vendor",
        "👥 ユーザー管理": "users",
        "🏢 部署管理": "departments",
        "🛠️ メンテナンス": "maintenance",
        "🎭 デモモード": "demo"
    }
    current_menu = st.session_state.get("menu")
    if current_menu and current_menu in legacy_map:
        st.session_state.menu_id = legacy_map[current_menu]
        del st.session_state["menu"]

    if current_menu:
        if str(current_menu).startswith("✅ 承認管理"):
            st.session_state.menu_id = "approval"
            if "menu" in st.session_state:
                del st.session_state["menu"]
        elif str(current_menu).startswith("✅ 廃棄承認"):
            st.session_state.menu_id = "disposal_approval"
            if "menu" in st.session_state:
                del st.session_state["menu"]
        elif str(current_menu).startswith("✅ 発注申請管理"):
            st.session_state.menu_id = "purchase_admin"
            if "menu" in st.session_state:
                del st.session_state["menu"]


def render_sidebar(ai_enabled: bool) -> str:
    """
    サイドバー全体をレンダリングし、選択されたメニューIDを返す。

    Returns:
        選択されたメニューID (str)
    """
    st.title("🏢 在庫管理システム")
    st.divider()

    show_user_info_sidebar()
    st.divider()

    # 表示サイズ選択
    st.subheader("⚙️ 表示設定")
    size_options = ["小", "中", "大"]
    selected_size = st.selectbox(
        "表示サイズ",
        options=size_options,
        index=size_options.index(st.session_state.get("display_size", "中")),
        key="size_selector",
        help="小：縮小表示 / 中：標準 / 大：拡大表示"
    )
    if selected_size != st.session_state.get("display_size", "中"):
        st.session_state.display_size = selected_size
        st.rerun()

    st.divider()

    if ai_enabled:
        st.success("🤖 AI機能: 有効")
    else:
        st.info("🤖 AI機能: 無効")

    st.divider()

    # レガシーメニュー移行
    if "menu" in st.session_state and "menu_id" not in st.session_state:
        migrate_legacy_menu()

    # メニュー構築
    menu_items = build_menu_items(ai_enabled)
    menu_options = [item[0] for item in menu_items]
    menu_labels = {item[0]: item[1] for item in menu_items}

    # 初期値設定
    if "menu_id" not in st.session_state:
        st.session_state.menu_id = menu_options[0]
    elif st.session_state.menu_id not in menu_options:
        st.session_state.menu_id = menu_options[0]

    # 他ページからの遷移リクエスト
    if "pending_menu_id" in st.session_state:
        pending = st.session_state.pop("pending_menu_id")
        if pending in menu_options:
            st.session_state.sb_menu = pending

    # ラジオボタン
    selected_menu_id = st.radio(
        "メニュー",
        options=menu_options,
        format_func=lambda mid: format_menu_label(mid, menu_labels),
        index=menu_options.index(st.session_state.menu_id)
              if st.session_state.menu_id in menu_options else 0,
        key="sb_menu"
    )

    if selected_menu_id != st.session_state.menu_id:
        st.session_state.menu_id = selected_menu_id
        st.session_state.current_page = 1
        st.rerun()

    return st.session_state.menu_id

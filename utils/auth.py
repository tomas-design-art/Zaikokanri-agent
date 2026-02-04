"""
認証・権限制御共通モジュール
- ログイン状態チェック
- ロール制御（ADMIN/USER/GUEST）
- 権限チェック関数群
"""

import streamlit as st
from typing import Optional, List
from functools import wraps


# =============================================================================
# ロール定義
# =============================================================================

# ロールの権限レベル（大きいほど高権限）
ROLE_LEVELS = {
    "GUEST": 1,
    "USER": 2,
    "ADMIN": 3
}

# ロール表示名
ROLE_DISPLAY_NAMES = {
    "GUEST": "ゲスト",
    "USER": "一般ユーザー",
    "ADMIN": "管理者"
}


# =============================================================================
# ログイン状態確認
# =============================================================================

def is_logged_in() -> bool:
    """
    ログイン状態を確認
    
    Returns:
        ログイン中ならTrue
    """
    return st.session_state.get("logged_in", False)


def get_current_user() -> dict:
    """
    現在のログインユーザー情報を取得
    
    Returns:
        ユーザー情報の辞書（未ログインなら空辞書）
    """
    return st.session_state.get("current_user", {})


def get_user_role() -> str:
    """
    現在のユーザーの権限ロールを取得
    
    Returns:
        ロール文字列（ADMIN/USER/GUEST）、未ログインなら空文字列
    """
    user = get_current_user()
    return user.get("user_role", "")


def get_user_id() -> Optional[int]:
    """
    現在のユーザーIDを取得
    
    Returns:
        ユーザーID、未ログインならNone
    """
    user = get_current_user()
    return user.get("id")


def get_user_department() -> str:
    """
    現在のユーザーの部署名を取得
    
    Returns:
        部署名、未設定なら空文字列
    """
    user = get_current_user()
    return user.get("department", "")


def get_user_department_id() -> Optional[int]:
    """
    現在のユーザーの部署IDを取得
    
    Returns:
        部署ID、未設定ならNone
    """
    user = get_current_user()
    return user.get("department_id")


def get_user_display_name() -> str:
    """
    現在のユーザーの表示名を取得
    
    Returns:
        表示名、未設定なら空文字列
    """
    user = get_current_user()
    return user.get("display_name", "")


# =============================================================================
# ロール判定
# =============================================================================

def is_admin() -> bool:
    """管理者権限があるか確認"""
    return get_user_role() == "ADMIN"


def is_user() -> bool:
    """一般ユーザー権限があるか確認（ADMINも含む）"""
    return get_user_role() in ["ADMIN", "USER"]


def is_guest() -> bool:
    """ゲストユーザーか確認"""
    return get_user_role() == "GUEST"


def has_role(role: str) -> bool:
    """
    指定されたロールと完全一致するか確認
    
    Args:
        role: チェックするロール（ADMIN/USER/GUEST）
    
    Returns:
        一致すればTrue
    """
    return get_user_role() == role


def has_min_role(min_role: str) -> bool:
    """
    指定されたロール以上の権限を持っているか確認
    
    Args:
        min_role: 最低限必要なロール
    
    Returns:
        権限があればTrue
    """
    current_role = get_user_role()
    if not current_role:
        return False
    
    current_level = ROLE_LEVELS.get(current_role, 0)
    required_level = ROLE_LEVELS.get(min_role, 0)
    
    return current_level >= required_level


# =============================================================================
# 権限チェック関数（ページ冒頭で使用）
# =============================================================================

def require_login(message: str = "この機能を使用するにはログインが必要です") -> bool:
    """
    ログインを必須とする
    未ログインなら警告を表示しFalseを返す
    
    Args:
        message: 未ログイン時のメッセージ
    
    Returns:
        ログイン中ならTrue、未ログインならFalse
    
    Usage:
        if not require_login():
            return  # ページ処理を中断
    """
    if not is_logged_in():
        st.warning(f"⚠️ {message}")
        return False
    return True


def require_role(role: str, message: Optional[str] = None) -> bool:
    """
    特定のロールを必須とする（完全一致）
    
    Args:
        role: 必要なロール（ADMIN/USER/GUEST）
        message: 権限不足時のメッセージ（省略時は自動生成）
    
    Returns:
        権限があればTrue、なければFalse（警告表示済み）
    
    Usage:
        if not require_role("ADMIN"):
            return  # ページ処理を中断
    """
    if not require_login():
        return False
    
    if not has_role(role):
        role_name = ROLE_DISPLAY_NAMES.get(role, role)
        msg = message or f"この機能は{role_name}のみ使用できます"
        st.error(f"🚫 {msg}")
        return False
    
    return True


def require_min_role(min_role: str, message: Optional[str] = None) -> bool:
    """
    指定されたロール以上の権限を必須とする
    
    Args:
        min_role: 最低限必要なロール
        message: 権限不足時のメッセージ（省略時は自動生成）
    
    Returns:
        権限があればTrue、なければFalse（警告表示済み）
    
    Usage:
        if not require_min_role("USER"):
            return  # GUESTは弾かれる
    """
    if not require_login():
        return False
    
    if not has_min_role(min_role):
        role_name = ROLE_DISPLAY_NAMES.get(min_role, min_role)
        msg = message or f"この機能は{role_name}以上の権限が必要です"
        st.error(f"🚫 {msg}")
        return False
    
    return True


def require_not_guest(message: str = "この機能はゲストユーザーは使用できません") -> bool:
    """
    ゲスト以外を必須とする（USER/ADMIN専用機能）
    
    Args:
        message: 権限不足時のメッセージ
    
    Returns:
        USER/ADMINならTrue、GUESTならFalse
    """
    return require_min_role("USER", message)


# =============================================================================
# 操作権限チェック（旧互換）
# =============================================================================

def can_edit() -> bool:
    """編集権限があるか確認（ADMIN/USERのみ）"""
    return has_min_role("USER")


def can_outbound() -> bool:
    """出庫権限があるか確認（全ユーザー可、GUESTは仮入力）"""
    return is_logged_in()


def can_inbound() -> bool:
    """入庫権限があるか確認（ADMIN/USERのみ）"""
    return has_min_role("USER")


def can_undo() -> bool:
    """取消権限があるか確認（全ユーザー可、GUESTは申請）"""
    return is_logged_in()


def can_adjust() -> bool:
    """在庫調整権限があるか確認（ADMINのみ）"""
    return is_admin()


def can_approve() -> bool:
    """承認権限があるか確認（ADMIN/USERは自部署、ADMINは全部署）"""
    return has_min_role("USER")


def can_manage_users() -> bool:
    """ユーザー管理権限があるか確認（ADMINのみ）"""
    return is_admin()


def can_manage_masters() -> bool:
    """マスター管理権限があるか確認（ADMINのみ）"""
    return is_admin()


# =============================================================================
# 権限チェック付きUI表示ヘルパー
# =============================================================================

def show_permission_denied(feature_name: str = "この機能"):
    """
    権限不足メッセージを表示
    
    Args:
        feature_name: 機能名
    """
    st.error(f"🚫 {feature_name}を使用する権限がありません")


def show_login_required(feature_name: str = "この機能"):
    """
    ログイン必須メッセージを表示
    
    Args:
        feature_name: 機能名
    """
    st.warning(f"⚠️ {feature_name}を使用するにはログインが必要です")


def check_page_access(
    require_logged_in: bool = True,
    min_role: Optional[str] = None,
    exact_role: Optional[str] = None,
    feature_name: str = "この機能"
) -> bool:
    """
    ページアクセス権限を一括チェック
    
    Args:
        require_logged_in: ログイン必須か
        min_role: 最低限必要なロール（指定時）
        exact_role: 必要なロール（完全一致）
        feature_name: 機能名（メッセージ用）
    
    Returns:
        アクセス可能ならTrue
    
    Usage:
        if not check_page_access(min_role="USER", feature_name="入庫"):
            return
    """
    if require_logged_in and not is_logged_in():
        show_login_required(feature_name)
        return False
    
    if exact_role is not None:
        if not has_role(exact_role):
            role_name = ROLE_DISPLAY_NAMES.get(exact_role, exact_role)
            st.error(f"🚫 {feature_name}は{role_name}のみ使用できます")
            return False
    
    if min_role is not None:
        if not has_min_role(min_role):
            role_name = ROLE_DISPLAY_NAMES.get(min_role, min_role)
            st.error(f"🚫 {feature_name}は{role_name}以上の権限が必要です")
            return False
    
    return True

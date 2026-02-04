"""
在庫管理アプリ メインエントリーポイント
Streamlit ベースのWebアプリケーション
"""

import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

# =============================================================================
# 日時ヘルパー関数 (JST統一)
# =============================================================================
def parse_db_ts_to_jst(ts: str) -> datetime:
    """
    DBからの日時文字列をJSTのdatetimeオブジェクトに変換する
    
    フォーマット: "%Y-%m-%d %H:%M:%S"
    
    仕様:
    - OFFSET-UNAWARE (タイムゾーン情報なし) の場合:
      DBには基本的にUTCで保存されている（またはそうみなす）ため、
      UTCとしてロードしてからJST ('Asia/Tokyo') に変換する。
      
      ※ これまでDBにJSTで保存されていたデータも +9時間される可能性があるが、
         「表示をJSTで統一」を優先するため、このロジックで統一する。
    """
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        # UTCとして解釈 -> JSTへ変換
        dt = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))
        return dt
    except ValueError:
        # 万が一パースできない場合は現在時刻(JST)を返すなどの安全策
        # ここではエラー出力してそのまま返す（呼び出し元で落ちる）か、現在時刻にする
        print(f"Warning: Failed to parse timestamp '{ts}'")
        return datetime.now(ZoneInfo("Asia/Tokyo"))


# 共通ユーティリティ（バリデーション・認証・ログ）
from utils.validation import (
    normalize_to_halfwidth, normalize_number_string, clean_string, is_empty,
    validate_integer, validate_positive_integer, validate_non_negative_integer,
    validate_required_string, validate_optional_string, validate_alphanumeric,
    validate_date_string, validate_float, ValidationResult, create_validation_result,
    show_validation_errors, validate_form_and_show_errors,
    # 現場向けシンプルAPI
    to_int_safe, to_float_safe, normalize_number_str, validate_required_text,
    # 補正検出ヘルパー
    has_currency_symbols, has_fullwidth_chars, needs_correction_warning
)
from utils.auth import (
    is_logged_in, get_current_user, get_user_role, get_user_id,
    get_user_department, get_user_department_id, get_user_display_name,
    is_admin, is_user, is_guest, has_role, has_min_role,
    require_login, require_role, require_min_role, require_not_guest,
    can_edit, can_outbound, can_inbound, can_undo, can_adjust,
    can_approve, can_manage_users, can_manage_masters,
    check_page_access
)
from utils.logger import (
    log_info, log_warning, log_error, log_debug,
    log_inbound, log_outbound, log_adjust, log_approve, log_reject, log_login
)

from db import (
    get_db_connection, init_tables, process_outbound, process_inbound, 
    get_item_by_id, get_item_master_by_id, get_history_list, get_recent_history_for_undo, 
    can_undo_history, process_undo, authenticate_user, get_all_users,
    create_user, update_user_status, process_adjust, update_user_role,
    process_outbound_pending, process_undo_pending,
    get_all_departments, get_department_by_id, create_department,
    migrate_users_department_to_id, create_pending_transaction,
    get_pending_transactions, get_pending_count, approve_pending_transaction,
    reject_pending_transaction, update_department_name, update_department_status,
    update_user_full, get_my_pending_transactions, cancel_pending_transaction,
    get_pending_for_history,
    list_items, count_items, insert_item, update_item, deactivate_item, activate_item,
    list_categories, get_category_names, insert_category,
    list_vendors, count_vendors, get_vendor_names, get_vendor_by_id, get_vendor_by_name,
    insert_vendor, update_vendor, deactivate_vendor, activate_vendor,
    list_users, count_users,
    list_departments, count_departments,
    get_user_by_id,
    # 発注申請関連
    create_purchase_request, get_purchase_requests, get_purchase_request_counts,
    approve_purchase_request, hold_purchase_request, reject_purchase_request,
    reset_purchase_request_to_pending, delete_purchase_request,
    get_approved_requests_for_order, mark_requests_ordered,
    get_ordered_purchase_requests, receive_purchase_order,
    insert_demo_data, reset_demo_data, get_demo_data_counts,
    create_disposal_request, get_disposal_requests, approve_disposal_request,
    reject_disposal_request, get_disposal_count,
    # メンテナンス関連
    check_history_change_types, backup_inventory_history_to_csv, cleanup_history_change_types
)

# 環境変数読み込み
load_dotenv()

# 設定
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
# DB_PATHを絶対パスに設定（起動ディレクトリが変わっても同じDBを参照）
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "inventory.db"))


# =============================================================================
# ログイン・ログアウト処理（session_state操作はapp.pyに残す）
# =============================================================================

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


# =============================================================================
# 更新ボタン関連
# =============================================================================

def refresh_data():
    """
    最新データの再取得用ヘルパー関数
    - refresh_tokenを更新してキャッシュバイパス
    - ログイン状態は保持
    - DB更新処理の再実行を防ぐため、実行済みフラグはそのまま
    - キャッシュを完全にクリア
    """
    import time
    # キャッシュを完全にクリア
    st.cache_data.clear()
    st.cache_resource.clear()
    # デバッグログ
    print(f"[REFRESH] キャッシュクリア完了: DB={os.path.abspath(DB_PATH)}")
    st.session_state["refresh_token"] = time.time()
    st.rerun()


def show_refresh_button():
    """各ページ右上に表示する更新ボタン"""
    col1, col2 = st.columns([6, 1])
    with col1:
        # DB参照先を表示（デバッグ用）
        st.caption(f"🗄️ DB: {os.path.abspath(DB_PATH)}")
    with col2:
        if st.button("🔄 更新", key="refresh_btn", help="最新データを再取得します"):
            refresh_data()


def show_login_page():
    """ログインページを表示"""
    
    # ログイン画面を中央寄せ（columnsで実装・若干横長）
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


def apply_size_css(size_mode):
    """表示サイズに応じたCSSを適用（CSS変数ベース）"""
    
    # サイズ別のCSS変数値
    if size_mode == "小":
        base_font = "13px"
        heading1 = "2.0rem"  # ページタイトル
        heading2 = "1.6rem"
        heading3 = "1.3rem"
        metric_label = "11px"
        metric_value = "18px"
        gap = "0.4rem"
        padding = "0.25rem 0.6rem"
    elif size_mode == "中":
        base_font = "16px"
        heading1 = "2.6rem"  # ページタイトル
        heading2 = "2.0rem"
        heading3 = "1.6rem"
        metric_label = "14px"
        metric_value = "28px"
        gap = "0.6rem"
        padding = "0.4rem 0.9rem"
    else:  # 大
        base_font = "22px"
        heading1 = "3.6rem"  # ページタイトル
        heading2 = "2.8rem"
        heading3 = "2.2rem"
        metric_label = "20px"
        metric_value = "42px"
        gap = "0.8rem"
        padding = "0.6rem 1.4rem"
    
    css = f"""
    <style>
    /* === CSS変数定義 === */
    :root {{
        --base-font: {base_font};
        --heading1: {heading1};
        --heading2: {heading2};
        --heading3: {heading3};
        --metric-label: {metric_label};
        --metric-value: {metric_value};
        --gap: {gap};
        --padding: {padding};
    }}
    
    /* === アプリ全体はフル幅 === */
    .block-container {{
        max-width: 100% !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }}
    
    /* === ログイン画面を中央寄せ＋幅制限 === */
    .center-card {{
        max-width: 720px;
        margin: 0 auto;
    }}
    @media (max-width: 720px) {{
        .center-card {{ max-width: 100%; }}
    }}
    
    /* === 見出し === */
    h1 {{ font-size: var(--heading1) !important; }}
    h2 {{ font-size: var(--heading2) !important; }}
    h3 {{ font-size: var(--heading3) !important; }}
    
    /* === サイドバーのタイトルは固定サイズ（小サイズ相当） === */
    [data-testid="stSidebar"] h1 {{
        font-size: 1.6rem !important;
    }}
    
    /* === 本文・段落 === */
    body, p, span, label {{
        font-size: var(--base-font);
    }}
    
    /* === サイドバー === */
    [data-testid="stSidebar"] {{
        font-size: var(--base-font) !important;
    }}
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stSelectbox label {{
        font-size: var(--base-font) !important;
    }}
    
    /* === タブ === */
    .stTabs [data-baseweb="tab"] {{
        font-size: var(--base-font) !important;
        padding: var(--padding) !important;
    }}
    
    /* === ボタン === */
    .stButton > button {{
        font-size: var(--base-font) !important;
        padding: var(--padding) !important;
    }}
    
    /* === メトリクス === */
    [data-testid="stMetricLabel"] {{
        font-size: var(--metric-label) !important;
    }}
    [data-testid="stMetricValue"] {{
        font-size: var(--metric-value) !important;
    }}
    
    /* === ラベル === */
    .stTextInput > label,
    .stNumberInput > label,
    .stSelectbox > label,
    .stTextArea > label {{
        font-size: var(--base-font) !important;
        margin-bottom: var(--gap) !important;
    }}
    
    /* === 入力欄 === */
    .stTextInput input,
    .stNumberInput input,
    .stTextArea textarea {{
        font-size: var(--base-font) !important;
        padding: var(--gap) !important;
    }}
    
    /* === セレクトボックス === */
    .stSelectbox > div > div {{
        font-size: var(--base-font) !important;
    }}
    
    /* === Markdownテキスト === */
    .stMarkdown {{
        font-size: var(--base-font) !important;
    }}
    .stMarkdown p {{
        font-size: var(--base-font) !important;
        margin-bottom: var(--gap) !important;
    }}
    
    /* === info/warning/successボックス === */
    .stAlert {{
        font-size: var(--base-font) !important;
        padding: var(--gap) !important;
    }}
    .stAlert p {{
        font-size: var(--base-font) !important;
    }}
    
    /* === データフレーム（表）=== */
    .stDataFrame, .stDataEditor {{
        font-size: var(--base-font) !important;
    }}
    
    /* data_editorのセル文字 */
    div[data-testid="stDataFrame"] table {{
        font-size: var(--base-font) !important;
    }}
    div[data-testid="stDataFrame"] th,
    div[data-testid="stDataFrame"] td {{
        font-size: var(--base-font) !important;
        padding: var(--gap) !important;
    }}
    div[data-testid="stDataFrame"] input {{
        font-size: var(--base-font) !important;
    }}
    
    /* === キャプション === */
    .stCaption, [data-testid="stCaptionContainer"] {{
        font-size: calc(var(--base-font) - 2px) !important;
    }}
    
    /* === コンテナ（カード）の余白 === */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        padding: var(--gap) !important;
    }}
    
    /* === 区切り線の余白 === */
    hr {{
        margin-top: var(--gap) !important;
        margin-bottom: var(--gap) !important;
    }}
    </style>
    """
    
    st.markdown(css, unsafe_allow_html=True)


def check_multiple_db_files():
    """プロジェクト内にinventory.dbファイルが複数存在しないかチェック"""
    project_root = os.path.dirname(__file__)
    db_files = []
    
    # プロジェクトルート直下と主要なサブフォルダをチェック
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
    
    # 結果をコンソール出力
    current_db = os.path.abspath(DB_PATH)
    print(f"[DB_CHECK] 現在のDB: {current_db}")
    print(f"[DB_CHECK] 検出されたinventory.db: {len(db_files)}件")
    for db_file in db_files:
        is_current = " ← 現在使用中" if db_file == current_db else ""
        print(f"  - {db_file}{is_current}")
    
    # 複数存在する場合は警告
    if len(db_files) > 1:
        print(f"[DB_CHECK] ⚠️ 警告: inventory.dbが{len(db_files)}個検出されました。意図しないDB参照の可能性があります。")


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
    
    # 選択された表示サイズに応じたCSSを適用
    apply_size_css(st.session_state.display_size)
    
    # デバッグ: DB複数存在チェック（初回のみ）
    if "db_check_done" not in st.session_state:
        check_multiple_db_files()
        st.session_state.db_check_done = True
    
    # セッションステート初期化
    if "initialized" not in st.session_state:
        # DB初期化確認
        if not os.path.exists(DB_PATH):
            st.warning("⚠️ データベースが見つかりません。初期化してください。")
            if st.button("データベースを初期化"):
                init_tables()
                st.success("✅ データベースを初期化しました！")
                st.rerun()
        st.session_state.initialized = True


def set_menu(menu_id: str):
    """
    メニューIDを設定して画面遷移（リラン）するヘルパー関数
    
    【重要】画面遷移は必ずこの関数を使用してください。
    st.session_state.menu_id への直接代入は禁止です。
    """
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1  # ページネーションリセット
    st.rerun()


def get_inventory_list(search_query="", category_filter="", asset_filter="すべて", limit=100, offset=0, department_name=None):
    """
    在庫一覧を取得（検索・フィルタ対応）
    数千件対応のため、LIMIT/OFFSETでページネーション
    
    Args:
        department_name: 部署名（GUESTユーザー用フィルタ）。指定時は自部署タグ+全社共通のみ表示
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # ベースクエリ
        query = """
            SELECT 
                i.id,
                i.item_name,
                i.item_code,
                i.vendor_name,
                i.vendor_item_code,
                i.category,
                i.unit_price,
                i.is_asset,
                i.department_tags,
                i.frequency_tag,
                i.expiry_date,
                inv.quantity,
                inv.threshold,
                inv.location,
                CASE 
                    WHEN inv.quantity <= inv.threshold THEN '⚠️'
                    ELSE '✅'
                END as alert_status
            FROM items i
            LEFT JOIN inventory inv ON i.id = inv.item_id
            WHERE 1=1
        """
        
        params = []
        
        # 資産フィルタ
        if asset_filter == "消耗品":
            query += " AND i.is_asset = 0"
        elif asset_filter == "資産":
            query += " AND i.is_asset = 1"
        
        # 検索条件
        if search_query:
            query += """ 
                AND (
                    i.item_name LIKE ? 
                    OR i.item_code LIKE ?
                    OR i.vendor_name LIKE ?
                    OR i.vendor_item_code LIKE ?
                )
            """
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern] * 4)
        
        # カテゴリフィルタ
        if category_filter and category_filter != "すべて":
            query += " AND i.category = ?"
            params.append(category_filter)
        
        # 部署名フィルタ（GUESTユーザー用：自部署タグ+全社共通のみ）
        if department_name:
            query += """ AND (
                (',' || i.department_tags || ',') LIKE ?
                OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                OR i.department_tags IS NULL
                OR TRIM(i.department_tags) = ''
            )"""
            params.append(f'%,{department_name},%')
        
        # ソート・ページネーション
        query += " ORDER BY i.item_name LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # DataFrameに変換
        if rows:
            df = pd.DataFrame([dict(row) for row in rows])
            return df
        else:
            return pd.DataFrame()


def get_total_count(search_query="", category_filter="", asset_filter="すべて", department_name=None):
    """
    検索条件に一致する総件数を取得
    
    Args:
        department_name: 部署名（GUESTユーザー用フィルタ）。指定時は自部署タグ+全社共通のみ表示
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) as count FROM items i WHERE 1=1"
        params = []
        
        # 資産フィルタ
        if asset_filter == "消耗品":
            query += " AND i.is_asset = 0"
        elif asset_filter == "資産":
            query += " AND i.is_asset = 1"
        
        if search_query:
            query += """ 
                AND (
                    i.item_name LIKE ? 
                    OR i.item_code LIKE ?
                    OR i.vendor_name LIKE ?
                    OR i.vendor_item_code LIKE ?
                )
            """
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern] * 4)
        
        if category_filter and category_filter != "すべて":
            query += " AND i.category = ?"
            params.append(category_filter)
        
        # 部署名フィルタ（GUESTユーザー用：自部署タグ+全社共通のみ）
        if department_name:
            query += """ AND (
                (',' || i.department_tags || ',') LIKE ?
                OR (',' || i.department_tags || ',') LIKE '%,全社,%'
                OR i.department_tags IS NULL
                OR TRIM(i.department_tags) = ''
            )"""
            params.append(f'%,{department_name},%')
        
        cursor.execute(query, params)
        result = cursor.fetchone()
        return result["count"] if result else 0


def get_categories():
    """カテゴリ一覧を取得"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM items ORDER BY category")
        rows = cursor.fetchall()
        return [row["category"] for row in rows]


def show_dashboard_page():
    """🏠 ダッシュボードページ（KPI表示）"""
    from db import (
        get_monthly_outbound_total,
        get_stock_alert_count,
        get_expired_count,
        get_disposal_count
    )
    
    st.header("🏠 ダッシュボード")
    
    # ロール判定（GUESTは部署フィルタあり）
    current_user = get_current_user()
    user_role = current_user.get("user_role")
    user_dept = current_user.get("department")
    
    # 部署フィルタの設定
    department_filter = user_dept if user_role == "GUEST" else None
    
    # GUEST向けに表示範囲を明示
    if user_role == "GUEST":
        st.caption(f"📍 表示範囲: {user_dept} + 全社共通")
    
    st.subheader("📊 今月のKPI")
    
    # KPIデータ取得
    monthly_out = get_monthly_outbound_total(department_name=department_filter)
    stock_alert_count = get_stock_alert_count(department_name=department_filter)
    expired_count = get_expired_count(department_name=department_filter)
    disposal_pending = get_disposal_count(status="PENDING")
    
    # KPIカード表示（4列）
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="📤 今月の出庫数量",
            value=f"{monthly_out:,}",
            help="今月の出庫（OUT）数量の合計"
        )
    
    with col2:
        st.metric(
            label="⚠️ 在庫不足件数",
            value=f"{stock_alert_count}件",
            delta=None,
            delta_color="off",
            help="在庫数が発注点以下の物品数"
        )
    
    with col3:
        st.metric(
            label="🔴 期限切れ件数",
            value=f"{expired_count}件",
            delta=None,
            delta_color="off",
            help="使用期限が過ぎている物品数"
        )
    
    with col4:
        # 廃棄待ちはADMIN/USERのみ表示（GUESTは廃棄申請を見ない想定）
        if user_role in ["ADMIN", "USER"]:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value=f"{disposal_pending}件",
                delta=None,
                delta_color="off",
                help="承認待ちの廃棄申請数"
            )
        else:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value="-",
                help="この情報は管理者のみ表示されます"
            )
    
    st.divider()
    
    # クイックリンク
    st.subheader("🔗 クイックアクセス")
    
    link_col1, link_col2, link_col3, link_col4 = st.columns(4)
    
    with link_col1:
        if st.button("📦 在庫一覧", use_container_width=True):
            set_menu("inventory")
    
    with link_col2:
        if st.button("🚨 アラート", use_container_width=True):
            set_menu("alert")
    
    with link_col3:
        if user_role in ["ADMIN", "USER"]:
            if st.button("➕ 入庫", use_container_width=True):
                set_menu("inbound")
        elif user_role == "GUEST":
            if st.button("➖ 出庫（申請）", use_container_width=True):
                set_menu("outbound")
    
    with link_col4:
        if user_role in ["ADMIN", "USER"]:
            if st.button("➖ 出庫", use_container_width=True):
                set_menu("outbound")
    
    st.divider()
    
    # 補足情報
    st.info("💡 左側メニューから各機能にアクセスできます")


def show_inventory_page():
    """在庫一覧ページ"""
    st.header("📦 在庫一覧")
    
    # 更新ボタン
    show_refresh_button()
    
    # ========== 承認待ち通知（USER/ADMIN向け） ==========
    if can_inbound():  # USER/ADMINのみ表示
        current_user = get_current_user()
        user_dept_id = current_user.get("department_id")
        
        # ADMINは全部署、USERは自部署のみ
        if is_admin():
            pending_count = get_pending_count()  # 全件
        else:
            pending_count = get_pending_count(department_id=user_dept_id)  # 自部署のみ
        
        if pending_count > 0:
            st.warning(f"⚠️ **承認待ち申請が {pending_count} 件** あります。「📋 承認管理」ページで確認してください。")
    
    # ========== KPI カード ==========
    from db import (
        get_monthly_outbound_total,
        get_stock_alert_count,
        get_expired_count,
        get_disposal_count,
        get_reorder_candidates_count
    )
    
    # ロール判定（GUESTは部署フィルタあり）
    current_user = get_current_user()
    user_role = current_user.get("user_role")
    user_dept = current_user.get("department")
    department_filter = user_dept if user_role == "GUEST" else None
    
    # GUEST向けに表示範囲を明示
    if user_role == "GUEST":
        st.caption(f"📍 表示範囲: {user_dept} + 全社共通")
    
    # KPI取得
    monthly_out = get_monthly_outbound_total(department_name=department_filter)
    stock_alert_count = get_stock_alert_count(department_name=department_filter)
    expired_count = get_expired_count(department_name=department_filter)
    disposal_pending = get_disposal_count(status="PENDING")
    reorder_count = get_reorder_candidates_count(department_name=department_filter)
    
    # KPIカード表示（5列）
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    
    with kpi_col1:
        st.metric(
            label="📤 今月の出庫数量",
            value=f"{monthly_out:,}",
            help="今月の出庫（OUT）数量の合計"
        )
    
    with kpi_col2:
        st.metric(
            label="⚠️ 在庫不足件数",
            value=f"{stock_alert_count}件",
            help="在庫数が発注点以下の物品数"
        )
    
    with kpi_col3:
        st.metric(
            label="🔴 期限切れ件数",
            value=f"{expired_count}件",
            help="使用期限が過ぎている物品数"
        )
    
    with kpi_col4:
        if user_role in ["ADMIN", "USER"]:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value=f"{disposal_pending}件",
                help="承認待ちの廃棄申請数"
            )
        else:
            st.metric(
                label="🗑️ 廃棄待ち件数",
                value="-",
                help="この情報は管理者のみ表示されます"
            )
    
    with kpi_col5:
        st.metric(
            label="📦 発注候補件数",
            value=f"{reorder_count}件",
            help="消耗品で在庫不足＋直近30日OUT履歴あり"
        )
    
    st.divider()
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")
    
    # 検索フォーム
    col1, col2, col3, col4 = st.columns([3, 2, 1.5, 1])
    
    with col1:
        search_query = st.text_input(
            "🔍 検索",
            placeholder="品目名、品目コード、業者名などで検索",
            key="search_query"
        )
    
    with col2:
        categories = ["すべて"] + get_categories()
        category_filter = st.selectbox(
            "カテゴリ",
            options=categories,
            key="category_filter"
        )
    
    with col3:
        asset_filter = st.selectbox(
            "種別",
            options=["すべて", "消耗品", "資産"],
            key="asset_filter"
        )
    
    with col4:
        st.write("")  # スペース調整
        st.write("")
        search_button = st.button("🔎 検索", use_container_width=True)
    
    # ページネーション設定
    items_per_page = st.selectbox(
        "表示件数",
        options=[50, 100, 200, 500],
        index=1,
        key="items_per_page"
    )
    
    # ページ番号（セッションステートで管理）
    if "current_page" not in st.session_state:
        st.session_state.current_page = 1
    
    # 部署フィルタ（GUESTユーザーのみ適用）
    department_name_filter = None
    if is_guest():
        current_user = get_current_user()
        user_dept = current_user.get("department")
        if user_dept:
            department_name_filter = user_dept
            st.info(f"📋 表示範囲：**{user_dept}** のみ")
    
    # 総件数取得
    total_count = get_total_count(search_query, category_filter, asset_filter, department_name=department_name_filter)
    total_pages = (total_count + items_per_page - 1) // items_per_page
    
    # ページ情報とCSV出力ボタン
    col_info, col_csv = st.columns([3, 1])
    with col_info:
        st.info(f"📊 全 {total_count} 件中 {min(items_per_page, total_count)} 件を表示")
    with col_csv:
        if total_count > 0:
            # 全件取得してCSV出力用データを作成
            df_all = get_inventory_list(search_query, category_filter, asset_filter, limit=total_count, offset=0, department_name=department_name_filter)
            if not df_all.empty:
                # 種別を日本語化
                df_all['asset_type'] = df_all['is_asset'].map({0: '消耗品', 1: '資産'})
                
                csv_df = pd.DataFrame({
                    "品目名": df_all["item_name"],
                    "品目コード": df_all["item_code"],
                    "カテゴリ": df_all["category"],
                    "種別": df_all["asset_type"],
                    "在庫数": df_all["quantity"],
                    "閾値": df_all["threshold"],
                    "保管場所": df_all["location"].fillna("未設定"),
                    "業者名": df_all["vendor_name"].fillna(""),
                    "単価": df_all["unit_price"],
                    "部署タグ": df_all["department_tags"].fillna("")
                })
                
                csv_data = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                filename = f"inventory_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
                
                st.download_button(
                    label="📥 CSV出力",
                    data=csv_data,
                    file_name=filename,
                    mime="text/csv",
                    use_container_width=True,
                    help="現在のフィルタ条件で絞り込まれた在庫をCSV出力します"
                )
    
    # データ取得
    offset = (st.session_state.current_page - 1) * items_per_page
    df = get_inventory_list(search_query, category_filter, asset_filter, items_per_page, offset, department_name=department_name_filter)
    
    if not df.empty:
        # 在庫アラート表示
        alert_items = df[df["quantity"] <= df["threshold"]]
        if not alert_items.empty:
            st.warning(f"⚠️ 在庫が閾値以下の品目が {len(alert_items)} 件あります")
        
        # データ表示（カラム名を日本語化）
        display_df = df[[
            "alert_status", "item_name", "item_code", "category",
            "quantity", "threshold", "location", "vendor_name", "unit_price"
        ]].copy()
        
        display_df.columns = [
            "状態", "品目名", "品目コード", "カテゴリ",
            "在庫数", "閾値", "保管場所", "業者名", "単価"
        ]
        
        # データフレーム表示（Streamlitのデータフレームは自動でページネーション）
        st.dataframe(
            display_df,
            width='stretch',
            hide_index=True
        )
        
        # ページネーションコントロール
        if total_pages > 1:
            col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
            
            with col1:
                if st.button("⏮️ 最初", disabled=(st.session_state.current_page == 1)):
                    st.session_state.current_page = 1
                    st.rerun()
            
            with col2:
                if st.button("◀️ 前へ", disabled=(st.session_state.current_page == 1)):
                    st.session_state.current_page -= 1
                    st.rerun()
            
            with col3:
                st.write(f"ページ {st.session_state.current_page} / {total_pages}")
            
            with col4:
                if st.button("次へ ▶️", disabled=(st.session_state.current_page == total_pages)):
                    st.session_state.current_page += 1
                    st.rerun()
            
            with col5:
                if st.button("最後 ⏭️", disabled=(st.session_state.current_page == total_pages)):
                    st.session_state.current_page = total_pages
                    st.rerun()
    else:
        st.info("🔍 該当する在庫データがありません")


def get_all_items_for_outbound(search_query="", category_filter="すべて", department_id=None, include_assets=False, department_name=None):
    """
    出庫可能な物品一覧を取得（在庫数 > 0、デフォルトは消耗品のみ）
    
    Args:
        search_query: 検索キーワード
        category_filter: カテゴリでのフィルタ
        department_id: 部署ID（将来的に部署ごとの表示制限に使用）
        include_assets: Trueの場合、資産も含める（デフォルト: False）
        department_name: 部署名（GUESTユーザー用フィルタ）。指定時は自部署タグ+全社共通のみ表示
    
    Returns:
        物品リスト
    
    TODO: 将来的にdepartment_idを使って以下のようなフィルタを実装可能:
        - 部署ごとに閲覧可能なカテゴリを制限
        - 部署専用品目のみ表示
        - department_items テーブルを作成してN:Nの関連付け
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 基本SQL（デフォルトは消耗品のみ、include_assets=Trueなら資産も含む）
        if include_assets:
            sql = """
                SELECT 
                    i.id, i.item_name, i.item_code, i.category,
                    inv.quantity, inv.location, i.vendor_name
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE inv.quantity > 0
            """
        else:
            sql = """
                SELECT 
                    i.id, i.item_name, i.item_code, i.category,
                    inv.quantity, inv.location, i.vendor_name
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE inv.quantity > 0 AND i.is_asset = 0
            """
        
        params = []
        
        # 検索条件追加
        if search_query and search_query.strip():
            sql += """ AND (
                i.item_name LIKE ? OR 
                i.item_code LIKE ? OR 
                i.vendor_name LIKE ? OR
                i.vendor_item_code LIKE ?
            )"""
            search_param = f"%{search_query.strip()}%"
            params.extend([search_param, search_param, search_param, search_param])
        
        # カテゴリフィルタ追加
        if category_filter and category_filter != "すべて":
            sql += " AND i.category = ?"
            params.append(category_filter)
        
        # 部署名フィルタ追加（GUESTユーザー用：自部署タグのみ）
        if department_name:
            # 自部署名を含む物品のみ表示（全社共通は除外）
            sql += " AND i.department_tags LIKE ?"
            params.append(f'%{department_name}%')
        
        # TODO: 将来的な部署フィルタ（department_id を使った制限）
        # if department_id:
        #     sql += """ AND i.id IN (
        #         SELECT item_id FROM department_items WHERE department_id = ?
        #     )"""
        #     params.append(department_id)
        
        sql += " ORDER BY i.item_name"
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_items_for_inbound(search_query="", category_filter="すべて", department_id=None, include_assets=False):
    """
    入庫可能な物品一覧を取得（デフォルトは消耗品のみ、資産は通常入庫不可）
    
    Args:
        search_query: 検索キーワード
        category_filter: カテゴリでのフィルタ
        department_id: 部署ID（将来的に部署ごとの表示制限に使用）
        include_assets: Trueの場合、資産も含める（デフォルト: False）
    
    Returns:
        物品リスト
    
    TODO: 将来的にdepartment_idを使って部署ごとの品目制限を実装可能
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 基本SQL（デフォルトは消耗品のみ、include_assets=Trueなら資産も含む）
        if include_assets:
            sql = """
                SELECT 
                    i.id, i.item_name, i.item_code, i.category,
                    inv.quantity, inv.location, i.vendor_name
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE 1=1
            """
        else:
            sql = """
                SELECT 
                    i.id, i.item_name, i.item_code, i.category,
                    inv.quantity, inv.location, i.vendor_name
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.is_asset = 0
            """
        
        params = []
        
        # 検索条件追加
        if search_query and search_query.strip():
            sql += """ AND (
                i.item_name LIKE ? OR 
                i.item_code LIKE ? OR 
                i.vendor_name LIKE ? OR
                i.vendor_item_code LIKE ?
            )"""
            search_param = f"%{search_query.strip()}%"
            params.extend([search_param, search_param, search_param, search_param])
        
        # カテゴリフィルタ追加
        if category_filter and category_filter != "すべて":
            sql += " AND i.category = ?"
            params.append(category_filter)
        
        # TODO: 将来的な部署フィルタ（department_id を使った制限）
        # if department_id:
        #     sql += """ AND i.id IN (
        #         SELECT item_id FROM department_items WHERE department_id = ?
        #     )"""
        #     params.append(department_id)
        
        sql += " ORDER BY i.item_name"
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def show_outbound_page():
    """出庫ページ"""
    st.header("➖ 出庫処理")
    
    # 更新ボタン
    show_refresh_button()
    
    # ページ上部のメッセージ領域（取消成功など）
    message_area = st.empty()
    
    # 取消成功メッセージ表示（ページ上部）
    if "last_undo_outbound_success" in st.session_state and st.session_state.last_undo_outbound_success:
        with message_area.container():
            st.success(st.session_state.last_undo_outbound_success)
        st.session_state.last_undo_outbound_success = None
    
    # 権限チェック（共通関数使用）：ログイン必須
    if not require_login("出庫処理を行うにはログインが必要です"):
        return
    
    # ========== ミニダッシュボード（現場向け消費ペース表示） ==========
    with st.expander("📊 今月の出庫状況（消費ペース）", expanded=False):
        from db import get_top_outbound_items, get_outbound_trend_data
        import pandas as pd
        
        # ロール判定（GUESTは部署フィルタあり）
        current_user = get_current_user()
        user_role = current_user.get("user_role")
        user_dept = current_user.get("department")
        department_filter = user_dept if user_role == "GUEST" else None
        
        # GUEST向けに表示範囲を明示
        if user_role == "GUEST":
            st.info(f"📍 表示範囲: **{user_dept}** のみ")
        
        # ========== 1) 絞り込みUI ==========
        st.subheader("🔍 絞り込み条件")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            categories = ["すべて"] + get_categories()
            selected_category = st.selectbox(
                "カテゴリ",
                options=categories,
                key="dashboard_category"
            )
        
        with filter_col2:
            selected_period = st.selectbox(
                "期間",
                options=[3, 6, 12],
                index=1,  # デフォルト6ヶ月
                format_func=lambda x: f"過去{x}ヶ月",
                key="dashboard_period"
            )
        
        with filter_col3:
            keyword_search = st.text_input(
                "キーワード検索",
                placeholder="物品名、品目コード",
                key="dashboard_keyword"
            )
        
        st.divider()
        
        # ========== 2) 今月の出庫量TOP10を取得 ==========
        st.subheader("📈 今月の出庫量 TOP10")
        
        top_items = get_top_outbound_items(
            category=selected_category if selected_category != "すべて" else None,
            keyword=keyword_search,
            department_name=department_filter,
            limit=10
        )
        
        if not top_items:
            st.warning("⚠️ 絞り込み条件に該当する出庫データがありません（今月）")
        else:
            st.caption(f"💡 絞り込み条件で今月の出庫量が多い順にTOP10を表示しています")
            
            # TOP10をテーブル表示（チェックボックス付き）
            top_df = pd.DataFrame(top_items)
            top_df["monthly_out"] = top_df["monthly_out"].fillna(0).astype(int)
            top_df["quantity"] = top_df["quantity"].fillna(0).astype(int)
            top_df["threshold"] = top_df["threshold"].fillna(0).astype(int)
            
            # 表示用DataFrame
            display_top = top_df[["item_name", "item_code", "category", "monthly_out", "quantity", "threshold"]].copy()
            display_top.columns = ["物品名", "品目コード", "カテゴリ", "今月OUT", "現在庫", "発注点"]
            
            st.dataframe(display_top, width="stretch", hide_index=True)
            
            st.divider()
            
            # ========== 3) 物品選択（最大5件） ==========
            st.subheader("🔢 比較する物品を選択（最大5件）")
            
            # チェックボックス形式で選択
            selected_item_ids = []
            
            # 2列レイアウトでチェックボックス表示
            checkbox_cols = st.columns(2)
            for idx, item in enumerate(top_items):
                col_idx = idx % 2
                with checkbox_cols[col_idx]:
                    is_selected = st.checkbox(
                        f"{item['item_name']} ({item['item_code']})",
                        key=f"dashboard_item_{item['item_id']}",
                        disabled=len(selected_item_ids) >= 5 and item['item_id'] not in selected_item_ids
                    )
                    if is_selected:
                        selected_item_ids.append(item['item_id'])
            
            if not selected_item_ids:
                st.info("🔍 物品を選択すると、詳細KPIとグラフが表示されます")
            else:
                st.divider()
                
                # ========== 4) 物品別KPI表示 ==========
                st.subheader("📊 選択物品の詳細")
                
                # 選択した物品のみを抽出
                selected_top = top_df[top_df["item_id"].isin(selected_item_ids)].copy()
                
                # 物品別テーブル
                detail_display = selected_top[["item_name", "monthly_out", "quantity", "threshold"]].copy()
                detail_display.columns = ["物品名", "今月OUT", "現在庫", "発注点"]
                
                st.dataframe(detail_display, width="stretch", hide_index=True)
                
                # 合計値（補助）
                total_monthly_out = selected_top["monthly_out"].sum()
                total_stock = selected_top["quantity"].sum()
                
                summary_col1, summary_col2 = st.columns(2)
                with summary_col1:
                    st.metric("📤 今月OUT（合計）", f"{total_monthly_out:,}")
                with summary_col2:
                    st.metric("📦 現在庫（合計）", f"{total_stock:,}")
                
                st.divider()
                
                # ========== 5) 折れ線グラフ（必須） ==========
                st.subheader("📉 出庫量の推移（月別）")
                
                # グラフデータ取得
                trend_data = get_outbound_trend_data(
                    selected_item_ids,
                    months=selected_period,
                    department_name=department_filter
                )
                
                if trend_data:
                    # DataFrameに変換
                    trend_df = pd.DataFrame(trend_data)
                    
                    # ピボットして折れ線グラフ用に整形（欠け月を0補完）
                    pivot_df = trend_df.pivot_table(
                        index="ym",
                        columns="item_name",
                        values="qty",
                        fill_value=0
                    )
                    
                    # Streamlitの折れ線グラフ
                    st.line_chart(pivot_df, width="stretch")
                    
                    st.caption(f"💡 選択した物品の月別出庫数量（過去{selected_period}ヶ月）。欠けている月は0として表示されます。")
                else:
                    st.info(f"📭 選択した期間（過去{selected_period}ヶ月）に出庫データがありません")
    
    st.divider()
    
    # ========== 以下、既存の出庫フォーム ==========
    
    # GUESTの場合は仮入力モードであることを表示
    if is_guest():
        st.warning("👻 **ゲストモード**: 出庫は「仮入力」となり、管理者の承認後に反映されます")

    # 前回の出庫成功メッセージをセッションから移動して rerun で表示
    if "last_outbound_success" in st.session_state and st.session_state.last_outbound_success:
        st.session_state.outbound_success_display = st.session_state.last_outbound_success.copy()
        st.session_state.last_outbound_success = None
        st.rerun()
    
    if is_guest():
        st.info("💡 在庫を減らす処理です。ゲストユーザーは「仮入力」として記録され、管理者の承認を待ちます。")
    else:
        st.info("💡 在庫を減らす処理です。出庫すると自動的に履歴に記録されます。")
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")

    # 取消エラーメッセージはその場で表示
    if "last_undo_outbound_error" in st.session_state and st.session_state.last_undo_outbound_error:
        st.error(st.session_state.last_undo_outbound_error)
        st.session_state.last_undo_outbound_error = None
    
    # ゲストユーザーは単品出庫のみ表示
    if is_guest():
        show_single_outbound()
    else:
        # タブで「単品出庫」と「クイック出庫」を分ける
        tab1, tab2 = st.tabs(["📦 単品出庫", "⚡ クイック出庫（まとめて出庫）"])
        
        with tab1:
            # === 単品出庫（従来の処理） ===
            show_single_outbound()
        
        with tab2:
            # === クイック出庫（まとめて出庫） ===
            show_quick_outbound()


def show_single_outbound():
    """単品出庫（従来の処理）"""
    # 検索フォーム
    st.subheader("🔍 物品検索")
    
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        search_query_outbound = st.text_input(
            "検索",
            placeholder="品目名、品目コード、業者名などで検索",
            key="search_query_outbound"
        )
    
    with col2:
        categories = ["すべて"] + get_categories()
        category_filter_outbound = st.selectbox(
            "カテゴリ",
            options=categories,
            key="category_filter_outbound"
        )
    
    with col3:
        st.write("")  # スペース調整
        st.write("")
        search_button_outbound = st.button("🔎 検索", key="search_btn_outbound", use_container_width=True)
    
    st.divider()
    
    # 出庫可能な物品を取得（検索条件適用）
    # GUESTユーザーの場合は自部署タグのみ表示
    department_name_filter = None
    if is_guest():
        current_user = get_current_user()
        user_dept = current_user.get("department")
        if user_dept:
            department_name_filter = user_dept
            st.info(f"📋 表示範囲：**{user_dept}** のみ")
    
    items = get_all_items_for_outbound(search_query_outbound, category_filter_outbound, department_name=department_name_filter)
    
    if not items:
        st.warning("⚠️ 検索条件に該当する在庫がありません")
        return
    
    st.info(f"📊 {len(items)} 件の物品が見つかりました")
    
    # 【重要】物品選択をフォームの外に出す（リアルタイム反映のため）
    st.subheader("📝 出庫情報入力")
    
    # 物品選択（フォーム外）
    item_options = {
        f"{item['item_name']} (在庫: {item.get('quantity', 0)}個) [{item.get('category', '-')}]": item['id']
        for item in items
    }
    
    selected_item_display = st.selectbox(
        "物品を選択",
        options=list(item_options.keys()),
        help="在庫がある物品のみ表示されています",
        key="item_select"
    )
    
    selected_item_id = item_options[selected_item_display]
    
    # 選択された物品の詳細表示
    selected_item = next(item for item in items if item['id'] == selected_item_id)
    
    # DBから最新の在庫数を再取得（キャッシュ対策）
    fresh_item = get_item_by_id(selected_item_id)
    if fresh_item:
        selected_item['quantity'] = fresh_item.get('quantity', 0)
        st.caption(f"🔄 最新DB在庫: {fresh_item.get('quantity', 0)} 個") 
    
    # 在庫数を安全に取得
    current_quantity = selected_item.get('quantity', 0)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("現在在庫", f"{current_quantity} 個")
    with col2:
        st.metric("保管場所", selected_item.get('location') or "未設定")
    with col3:
        st.metric("カテゴリ", selected_item.get('category', '-'))

    # 出庫ページから発注申請への導線ボタン（USER/ADMINのみ）
    if not is_guest():
        btn_col1, btn_col2 = st.columns([1, 5])
        with btn_col1:
            if st.button("📝 発注申請", help="この物品で発注申請フォームを開きます"):
                # プレフィル用セッションにセットして申請ページへ遷移
                st.session_state.pr_prefill_item_id = selected_item_id
                # 推奨数量は在庫差分（閾値超過分）または1をセット
                try:
                    thresh = int(fresh_item.get('threshold', 0)) if fresh_item else 0
                    stock = int(current_quantity or 0)
                    rec = max(1, thresh - stock) if thresh and stock < thresh else 1
                except Exception:
                    rec = 1
                st.session_state.pr_prefill_qty = rec
                set_menu("purchase_request")
    
    st.divider()
    
    # 連打防止フラグの確認（成功直後はTrue、次回のrerunでFalseに戻す）
    button_disabled = st.session_state.get("outbound_button_disabled", False)
    if button_disabled:
        st.session_state.outbound_button_disabled = False  # 次回はrerun後に有効化
    
    # フォーム作成（物品選択以外の入力項目）
    with st.form("outbound_form", clear_on_submit=True):
        # 出庫数量入力
        quantity = st.number_input(
            "出庫数量",
            min_value=1,
            max_value=max(1, current_quantity),
            value=1,
            step=1,
            help=f"最大 {current_quantity} 個まで出庫できます"
        )
        
        # ユーザー情報（GUESTは手入力、それ以外は自動）
        current_user = get_current_user()
        col1, col2 = st.columns(2)
        
        with col1:
            if is_guest():
                # GUEST: 実行者名は手入力必須
                actor_name_input = st.text_input(
                    "出庫者名 *（必須）",
                    value="",
                    placeholder="例: 山田太郎",
                    help="複数人で共有IDを使用するため、実際の出庫者名を入力してください"
                )
                user_name = actor_name_input
            else:
                # USER/ADMIN: 自動入力
                st.text_input(
                    "出庫者名",
                    value=current_user.get("display_name", ""),
                    disabled=True,
                    help="ログインユーザー名が自動で設定されます"
                )
                user_name = current_user.get("display_name", "")
        
        with col2:
            st.text_input(
                "部署名",
                value=current_user.get("department", ""),
                disabled=True,
                help="ログインユーザーの部署が自動で設定されます"
            )
            department = current_user.get("department", "")
        
        # 備考
        note = st.text_area(
            "備考",
            placeholder="出庫理由や用途など（任意）",
            height=100
        )
        
        st.divider()
        
        # 送信ボタン（GUESTは「仮入力」表記）
        col1, col2 = st.columns([3, 1])
        with col1:
            if is_guest():
                st.info("💡 入力内容を確認して「出庫を申請」ボタンを押してください（承認待ちになります）")
            else:
                st.info("💡 入力内容を確認して「出庫を実行」ボタンを押してください")
        with col2:
            button_label = "📝 出庫を申請" if is_guest() else "✅ 出庫を実行"
            submitted = st.form_submit_button(
                button_label,
                type="primary",
                use_container_width=True,
                disabled=button_disabled
            )
        
        if submitted:
            # === バリデーション実行 ===
            ok, validated_qty, error_msg = to_int_safe(quantity, "出庫数量", min_value=1, allow_zero=False)
            if not ok:
                st.error(error_msg)
                return
            
            # 出庫者名のバリデーション（GUESTの場合）
            if is_guest():
                ok_name, validated_name, error_msg_name = validate_required_text(user_name, "出庫者名")
                if not ok_name:
                    st.error(error_msg_name)
                    st.info("複数人で共有IDを使用するため、実際の出庫者名が必須です。")
                    return
                user_name = validated_name
            
            # GUESTの場合は仮出庫処理、それ以外は通常出庫処理
            if is_guest():
                # pending_transactionsテーブルに仮登録
                result = create_pending_transaction(
                    change_type="OUT",
                    item_id=selected_item_id,
                    quantity=validated_qty,
                    actor_name=user_name,
                    note=note.strip(),
                    guest_user_id=current_user.get("id"),
                    department_id=current_user.get("department_id")
                )
                
                if result["success"]:
                    st.session_state.last_outbound_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'user_name': user_name,
                        'department': department,
                        'note': note.strip(),
                        'before_quantity': current_quantity,
                        'after_quantity': current_quantity,  # 仮入力なので変更なし
                        'is_low_stock': False,
                        'is_pending': True  # 仮入力フラグ
                    }
                    # フォーム付近通知用フラグもセット
                    st.session_state.outbound_form_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'after_quantity': current_quantity,
                        'is_pending': True
                    }
                    # 連打防止
                    st.session_state.outbound_button_disabled = True
                    st.rerun()
                else:
                    st.error(f"### ❌ 出庫申請に失敗しました")
                    st.error(result["message"])
            else:
                # 通常の出庫処理
                result = process_outbound(
                    item_id=selected_item_id,
                    quantity=validated_qty,
                    user_name=user_name,
                    department=department,
                    note=note.strip()
                )
                
                if result["success"]:
                    st.session_state.last_outbound_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'user_name': user_name,
                        'department': department,
                        'note': note.strip(),
                        'before_quantity': current_quantity,
                        'after_quantity': result['remaining_quantity'],
                        'is_low_stock': result['remaining_quantity'] <= fresh_item.get('threshold', 10) if fresh_item else False,
                        'is_pending': False
                    }
                    # フォーム付近通知用フラグもセット
                    st.session_state.outbound_form_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'after_quantity': result['remaining_quantity'],
                        'is_pending': False
                    }
                    # 連打防止
                    st.session_state.outbound_button_disabled = True
                    st.rerun()
                else:
                    st.error(f"### ❌ 出庫処理に失敗しました")
                    st.error(result["message"])
    
    # 短い成功通知（フォーム終了後、詳細カードの直前）
    form_notification = st.empty()
    if "outbound_form_success" in st.session_state and st.session_state.outbound_form_success:
        success_msg = st.session_state.outbound_form_success
        with form_notification.container():
            if success_msg.get('is_pending'):
                st.info(f"✅ **出庫申請が完了しました！** {success_msg['item_name']} x {success_msg['quantity']}個（承認待ち）")
            else:
                st.success(f"✅ **出庫が完了しました！** {success_msg['item_name']} x {success_msg['quantity']}個 → 残り{success_msg['after_quantity']}個")
        # フラグクリア（表示後に削除）
        del st.session_state.outbound_form_success
    
    # 成功内容カード表示（フォームの下、直近履歴の上）
    if "outbound_success_display" in st.session_state:
        success_data = st.session_state.outbound_success_display
        st.divider()
        with st.container(border=True):
            if success_data.get('is_pending'):
                st.subheader("📋 出庫申請内容")
            else:
                st.subheader("📋 出庫完了内容")
                st.balloons()

            col1, col2 = st.columns(2)
            with col1:
                st.metric("出庫物品", success_data['item_name'])
                st.metric("出庫数量", f"{success_data['quantity']} 個", delta=f"-{success_data['quantity']}")
                st.metric("出庫者", success_data['user_name'])

            with col2:
                if success_data.get('is_pending'):
                    st.metric("状態", "⏳ 承認待ち")
                    st.metric("現在在庫", f"{success_data['before_quantity']} 個")
                else:
                    st.metric("出庫前在庫", f"{success_data['before_quantity']} 個")
                    st.metric("出庫後在庫", f"{success_data['after_quantity']} 個")
                if success_data.get('department'):
                    st.metric("部署", success_data['department'])

            if success_data.get('note'):
                st.info(f"📝 備考: {success_data['note']}")

            if not success_data.get('is_pending') and success_data.get('is_low_stock'):
                st.warning(f"⚠️ 在庫が閾値以下になりました！発注をご検討ください。")
        
        # フラグをクリア
        del st.session_state.outbound_success_display
        if "outbound_success_shown" in st.session_state:
            del st.session_state.outbound_success_shown
    
    # 直近の出庫履歴を表示（最下部に配置）
    st.divider()
    st.subheader("⏪ 直近の出庫・申請")
    
    # 取消処理結果メッセージを表示（このセクションの直下）
    if "cancel_success_message" in st.session_state and st.session_state.cancel_success_message:
        st.success(st.session_state.cancel_success_message)
        st.session_state.cancel_success_message = None
    
    if "cancel_error_message" in st.session_state and st.session_state.cancel_error_message:
        st.error(st.session_state.cancel_error_message)
        st.session_state.cancel_error_message = None
    
    # === 承認待ち申請（PENDING）を表示 ===
    current_user = get_current_user()
    user_role = get_user_role()
    my_pending = get_my_pending_transactions(
        user_id=current_user.get("id"),
        department_id=current_user.get("department_id"),
        change_type="OUT",
        user_role=user_role
    )
    
    if my_pending:
        st.markdown("#### 📝 承認待ち申請（PENDING）")
        for pending in my_pending:
            created_at = parse_db_ts_to_jst(pending["created_at"])
            time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            
            with st.container(border=True):
                col1, col2 = st.columns([5, 2])
                
                with col1:
                    st.markdown(f"**📦 {pending['item_name']}** ({pending['item_code']}) 🔶 **承認申請中**")
                    st.caption(f"⏱️ {minutes_ago}分前 | 数量: {pending['quantity']}個 | 申請者: {pending['actor_name']}")
                    if pending.get('note'):
                        st.caption(f"📝 {pending['note']}")
                
                with col2:
                    # 取り下げボタン（GUESTの場合のみ、guest_user_id一致の場合）
                    if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                        confirm_key = f"confirm_cancel_pending_{pending['id']}"
                        if confirm_key not in st.session_state:
                            st.session_state[confirm_key] = False
                        
                        if not st.session_state[confirm_key]:
                            if st.button("🗑️ 取り下げ", key=f"cancel_pending_{pending['id']}", use_container_width=True):
                                st.session_state[confirm_key] = True
                                st.rerun()
                        else:
                            st.caption("⬇️ 下に入力欄")
                    else:
                        st.info("承認待ち")
                
                # 取り下げ確認フォーム（カラムの外に配置して見やすく）
                if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                    confirm_key = f"confirm_cancel_pending_{pending['id']}"
                    if confirm_key in st.session_state and st.session_state[confirm_key]:
                        actor_input_key = f"actor_confirm_{pending['id']}"
                        st.warning("⚠️ 取り下げるには、申請時に入力した名前を再入力してください")
                        actor_confirm = st.text_input("申請者名（本人確認用）", key=actor_input_key, placeholder="例: 山田太郎")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ 取り下げ確定", key=f"yes_cancel_{pending['id']}", type="primary", use_container_width=True):
                                if not actor_confirm.strip():
                                    st.session_state.cancel_error_message = "❌ 名前を入力してください"
                                    st.rerun()
                                elif actor_confirm.strip() != pending['actor_name']:
                                    st.session_state.cancel_error_message = "❌ 申請者名が一致しません。申請者本人でなければ取消処理はできません。"
                                    st.session_state[confirm_key] = False
                                    st.rerun()
                                else:
                                    result = cancel_pending_transaction(pending['id'], current_user['id'], actor_confirm.strip())
                                    st.session_state[confirm_key] = False
                                    if result["success"]:
                                        st.session_state.cancel_success_message = f"✅ 申請を取り下げました: {pending['item_name']} {pending['quantity']}個"
                                    else:
                                        st.session_state.cancel_error_message = result["message"]
                                    st.rerun()
                        with col_no:
                            if st.button("❌ キャンセル", key=f"no_cancel_{pending['id']}", use_container_width=True):
                                st.session_state[confirm_key] = False
                                st.rerun()
    
    # === 確定済み履歴（直近5件）===
    st.markdown("#### ✅ 確定済み履歴（直近5件）")
    st.caption("※ 10分以内なら取消可能")
    
    recent_outbound = get_recent_history_for_undo("OUT", limit=5)
    if recent_outbound:
        for record in recent_outbound:
            created_at = parse_db_ts_to_jst(record["created_at"])
            time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            
            # 取消可能かチェック（10分以内）
            can_undo_flag, reason = can_undo_history(record['id'], minutes=10)
            
            with st.container(border=True):
                col1, col2 = st.columns([5, 2])
                
                with col1:
                    st.markdown(f"**📦 {record['item_name']}** ({record['item_code']})")
                    st.caption(f"⏱️ {minutes_ago}分前 | 数量: {record['quantity']}個 | 担当: {record['user_name']}")
                
                with col2:
                    if not can_undo_flag:
                        # 取消不可（10分超過または取消済み）
                        st.button(f"🚫 {reason}", key=f"undo_out_{record['id']}", disabled=True, use_container_width=True)
                    else:
                        # 確認ダイアログ付き取消ボタン
                        if f"confirm_undo_out_{record['id']}" not in st.session_state:
                            st.session_state[f"confirm_undo_out_{record['id']}"] = False
                        
                        # GUESTは「申請」、それ以外は「取消」
                        button_label = "📝 取消申請" if is_guest() else "↩️ 取消"
                        confirm_msg = "取消を申請しますか？" if is_guest() else "本当に取り消しますか？"
                        
                        if not st.session_state[f"confirm_undo_out_{record['id']}"]:
                            if st.button(button_label, key=f"undo_out_{record['id']}", use_container_width=True):
                                st.session_state[f"confirm_undo_out_{record['id']}"] = True
                                st.rerun()
                        else:
                            st.error(confirm_msg)
                            col_yes, col_no = st.columns(2)
                            with col_yes:
                                if st.button("✅ はい", key=f"yes_out_{record['id']}", type="primary"):
                                    # GUESTは申請、それ以外は即時取消
                                    if is_guest():
                                        result = process_undo_pending(
                                            record['id'], 
                                            current_user.get("display_name", ""),
                                            current_user.get("department", "")
                                        )
                                    else:
                                        result = process_undo(record['id'], record['user_name'])
                                    
                                    st.session_state[f"confirm_undo_out_{record['id']}"] = False
                                    if result["success"]:
                                        st.session_state.last_undo_outbound_success = result["message"]
                                    else:
                                        st.session_state.last_undo_outbound_error = result["message"]
                                    st.rerun()
                            with col_no:
                                if st.button("❌ いいえ", key=f"no_out_{record['id']}"):
                                    st.session_state[f"confirm_undo_out_{record['id']}"] = False
                                    st.rerun()
    else:
        st.info("📭 確定済みの出庫履歴がありません")


def show_quick_outbound():
    """クイック出庫（まとめて出庫）- st.data_editorで表形式"""
    st.subheader("⚡ クイック出庫")
    st.info("💡 カテゴリを選択し、複数の物品を一度に出庫できます。")
    
    # カテゴリ選択
    categories = get_categories()
    if not categories:
        st.warning("⚠️ カテゴリが登録されていません")
        return
    
    selected_category = st.selectbox(
        "カテゴリを選択",
        options=categories,
        key="quick_outbound_category"
    )
    
    # 選択カテゴリの物品を取得
    items = get_all_items_for_outbound("", selected_category)
    
    if not items:
        st.warning(f"⚠️ 「{selected_category}」カテゴリに在庫がある物品がありません")
        return
    
    st.caption(f"📊 {len(items)} 件の物品")
    
    # まとめて出庫の成功メッセージ
    if "quick_outbound_success" in st.session_state and st.session_state.quick_outbound_success:
        success_count = st.session_state.quick_outbound_success
        st.success(f"✅ **{success_count} 件の出庫が完了しました！**")
        del st.session_state.quick_outbound_success
    
    # 現在のユーザー情報
    current_user = get_current_user()
    user_name = current_user.get("display_name", "")
    department = current_user.get("department", "")
    
    # GUEST用の出庫者名入力
    if is_guest():
        st.warning("👻 **ゲストモード**: 出庫者名を入力してください（必須）")
        actor_name_input = st.text_input(
            "出庫者名 *（必須）",
            value="",
            placeholder="例: 山田太郎",
            help="複数人で共有IDを使用するため、実際の出庫者名を入力してください",
            key="quick_outbound_actor_name"
        )
    
    # DataFrameに変換
    df_data = []
    for item in items:
        df_data.append({
            "id": item['id'],
            "品目名": item['item_name'],
            "在庫": item.get('quantity', 0),
            "保管場所": item.get('location') or "-",
            "業者名": item.get('vendor_name') or "-",
            "出庫数量": 0
        })
    
    df = pd.DataFrame(df_data)
    
    st.caption("💡 表の「出庫数量」列を編集してください（在庫数上限）")
    
    # st.data_editorで編集可能な表を表示（列幅は自動調整でレスポンシブ対応）
    # 列順：品目名→業者名→在庫→出庫数量（保管場所は非表示）
    edited_df = st.data_editor(
        df,
        column_config={
            "id": None,  # 非表示
            "品目名": st.column_config.TextColumn(
                "品目名",
                disabled=True,
                help="物品名"
            ),
            "業者名": st.column_config.TextColumn(
                "業者名",
                disabled=True,
                help="業者名"
            ),
            "在庫": st.column_config.NumberColumn(
                "在庫",
                disabled=True,
                format="%d",
                help="現在の在庫数"
            ),
            "出庫数量": st.column_config.NumberColumn(
                "出庫数量",
                min_value=0,
                max_value=None,  # 各行で在庫数上限は後でチェック
                step=1,
                format="%d",
                required=True,
                help="出庫する数量を入力"
            ),
            "保管場所": None  # 非表示
        },
        column_order=["品目名", "業者名", "在庫", "出庫数量"],
        hide_index=True,
        use_container_width=True,  # 画面幅に合わせてレスポンシブ対応
        num_rows="fixed",
        key="quick_outbound_editor"
    )
    
    # 備考と送信ボタン
    note = st.text_area(
        "備考（全体共通）",
        placeholder="出庫理由や用途など（任意）",
        height=60,
        key="quick_outbound_note"
    )
    
    # 送信ボタン
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("💡 出庫数量が1以上の物品のみが処理されます")
    with col2:
        submitted = st.button(
            "✅ まとめて出庫",
            type="primary",
            use_container_width=True,
            key="quick_outbound_submit"
        )
    
    if submitted:
        # === GUEST時の名前バリデーション ===
        if is_guest():
            ok_name, validated_name, error_msg_name = validate_required_text(actor_name_input, "出庫者名")
            if not ok_name:
                st.error(error_msg_name)
                st.info("複数人で共有IDを使用するため、実際の出庫者名が必須です。")
                return
            user_name = validated_name
        
        # 編集後のDataFrameから出庫数量が1以上の行を抽出
        outbound_rows = edited_df[edited_df['出庫数量'] > 0]
        
        if outbound_rows.empty:
            st.warning("⚠️ 出庫数量が1以上の物品を選択してください")
        else:
            # === バリデーションエラーを収集 ===
            validation_errors = []
            for idx, row in outbound_rows.iterrows():
                # 数量のバリデーション
                ok, validated_qty, error_msg = to_int_safe(row['出庫数量'], f"{row['品目名']}の出庫数量", min_value=1, allow_zero=False)
                if not ok:
                    validation_errors.append(f"❌ {row['品目名']}: {error_msg}")
                elif validated_qty > row['在庫']:
                    validation_errors.append(f"❌ {row['品目名']}: 出庫数量({validated_qty})が在庫数({row['在庫']})を超えています")
            
            if validation_errors:
                st.error("### ⚠️ 入力エラー")
                for err in validation_errors:
                    st.error(err)
            else:
                success_count = 0
                error_messages = []
                
                # 各物品を出庫処理
                for idx, row in outbound_rows.iterrows():
                    item_id = int(row['id'])
                    qty = int(row['出庫数量'])
                    
                    if is_guest():
                        # GUEST: 仮入力
                        result = create_pending_transaction(
                            change_type="OUT",
                            item_id=item_id,
                            quantity=qty,
                            actor_name=user_name,
                            note=note,
                            guest_user_id=current_user.get("id"),
                            department_id=current_user.get("department_id")
                        )
                    else:
                        # 通常出庫
                        result = process_outbound(
                            item_id=item_id,
                            quantity=qty,
                            user_name=user_name,
                            department=department,
                            note=note
                        )
                    
                    if result["success"]:
                        success_count += 1
                    else:
                        error_messages.append(f"❌ {row['品目名']}: {result['message']}")
                
                # 結果を表示
                if success_count > 0:
                    st.session_state.quick_outbound_success = success_count
                
                if error_messages:
                    st.error("### ⚠️ 一部の出庫処理に失敗しました")
                    for msg in error_messages:
                        st.error(msg)
                
                if success_count > 0:
                    st.rerun()



def show_inbound_page():
    """入庫ページ"""
    st.header("➕ 入庫処理")
    
    # 更新ボタン
    show_refresh_button()
    
    # ページ上部のメッセージ領域（取消成功など）
    message_area = st.empty()
    
    # 取消成功メッセージ表示（ページ上部）
    if "last_undo_inbound_success" in st.session_state and st.session_state.last_undo_inbound_success:
        with message_area.container():
            st.success(st.session_state.last_undo_inbound_success)
        st.session_state.last_undo_inbound_success = None
    
    # 権限チェック（共通関数使用）：ADMIN/USERのみ（GUESTは入庫不可）
    if not require_min_role("USER", "入庫処理はUSER以上の権限が必要です（ゲストユーザーは入庫不可）"):
        return
    
    # タブ切り替え
    tab1, tab2 = st.tabs(["🚚 発注品入庫", "📦 通常入庫"])
    
    with tab1:
        show_purchase_order_inbound_tab()
    
    with tab2:
        show_normal_inbound_tab()


def show_normal_inbound_tab():
    """通常入庫タブの内容"""
    # 前回の入庫成功メッセージをセッションから移動して rerun で表示
    if "last_inbound_success" in st.session_state and st.session_state.last_inbound_success:
        st.session_state.inbound_success_display = st.session_state.last_inbound_success.copy()
        st.session_state.last_inbound_success = None
        st.rerun()
    
    st.info("💡 在庫を増やす処理です。入庫すると自動的に履歴に記録されます。")
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")

    # 取消エラーメッセージはその場で表示
    if "last_undo_inbound_error" in st.session_state and st.session_state.last_undo_inbound_error:
        st.error(st.session_state.last_undo_inbound_error)
        st.session_state.last_undo_inbound_error = None
    
    # 検索フォーム
    st.subheader("🔍 物品検索")
    
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        search_query_inbound = st.text_input(
            "検索",
            placeholder="品目名、品目コード、業者名などで検索",
            key="search_query_inbound"
        )
    
    with col2:
        categories = ["すべて"] + get_categories()
        category_filter_inbound = st.selectbox(
            "カテゴリ",
            options=categories,
            key="category_filter_inbound"
        )
    
    with col3:
        st.write("")  # スペース調整
        st.write("")
        search_button_inbound = st.button("🔎 検索", key="search_btn_inbound", use_container_width=True)
    
    st.divider()
    
    # 入庫可能な物品を取得（検索条件適用）
    items = get_all_items_for_inbound(search_query_inbound, category_filter_inbound)
    
    if not items:
        st.warning("⚠️ 検索条件に該当する物品がありません")
        return
    
    st.info(f"📊 {len(items)} 件の物品が見つかりました")
    
    # 【重要】物品選択をフォームの外に出す（リアルタイム反映のため）
    st.subheader("📝 入庫情報入力")
    
    # 物品選択（フォーム外）
    item_options = {
        f"{item['item_name']} (現在在庫: {item.get('quantity', 0)}個) [{item.get('category', '-')}]": item['id']
        for item in items
    }
    
    selected_item_display = st.selectbox(
        "物品を選択",
        options=list(item_options.keys()),
        help="全ての物品が表示されています",
        key="item_select_inbound"
    )
    
    selected_item_id = item_options[selected_item_display]
    
    # 選択された物品の詳細表示
    selected_item = next(item for item in items if item['id'] == selected_item_id)
    
    # DBから最新の在庫数を再取得（キャッシュ対策）
    fresh_item = get_item_by_id(selected_item_id)
    if fresh_item:
        selected_item['quantity'] = fresh_item.get('quantity', 0)
        st.caption(f"🔄 最新DB在庫: {fresh_item.get('quantity', 0)} 個") 
    
    # 在庫数を安全に取得
    current_quantity = selected_item.get('quantity', 0)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("現在在庫", f"{current_quantity} 個")
    with col2:
        st.metric("保管場所", selected_item.get('location') or "未設定")
    with col3:
        st.metric("カテゴリ", selected_item.get('category', '-'))
    
    st.divider()
    
    # 連打防止フラグの確認（成功直後はTrue、次回のrerunでFalseに戻す）
    button_disabled = st.session_state.get("inbound_button_disabled", False)
    if button_disabled:
        st.session_state.inbound_button_disabled = False  # 次回はrerun後に有効化
    
    # フォーム作成（物品選択以外の入力項目）
    with st.form("inbound_form", clear_on_submit=True):
        # 入庫数量入力（正の整数のみ）
        quantity = st.number_input(
            "入庫数量",
            min_value=1,
            max_value=10000,
            value=1,
            step=1,
            help="入庫する数量を入力してください"
        )
        
        # ユーザー情報表示（ログインユーザーから自動取得）
        current_user = get_current_user()
        col1, col2 = st.columns(2)
        
        with col1:
            st.text_input(
                "入庫者名",
                value=current_user.get("display_name", ""),
                disabled=True,
                help="ログインユーザー名が自動で設定されます"
            )
            user_name = current_user.get("display_name", "")
        
        with col2:
            st.text_input(
                "部署名",
                value=current_user.get("department", ""),
                disabled=True,
                help="ログインユーザーの部署が自動で設定されます"
            )
            department = current_user.get("department", "")
        
        # 備考
        note = st.text_area(
            "備考",
            placeholder="入庫理由や仕入先など（任意）",
            height=100
        )
        
        st.divider()
        
        # 送信ボタン
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("💡 入力内容を確認して「入庫を実行」ボタンを押してください")
        with col2:
            submitted = st.form_submit_button(
                "✅ 入庫を実行",
                type="primary",
                use_container_width=True,
                disabled=button_disabled
            )
        
        if submitted:
            # === バリデーション実行 ===
            ok, validated_qty, error_msg = to_int_safe(quantity, "入庫数量", min_value=1, allow_zero=False)
            if not ok:
                st.error(error_msg)
                return
            
            # 入庫処理実行（ユーザー名はログインユーザーから自動取得済み）
            result = process_inbound(
                item_id=selected_item_id,
                quantity=validated_qty,
                user_name=user_name,
                department=department,
                note=note.strip()
            )
            
            if result["success"]:
                # 成功データをsession_stateに保存
                st.session_state.last_inbound_success = {
                    'item_name': selected_item['item_name'],
                    'quantity': validated_qty,
                    'user_name': user_name,
                    'department': department,
                    'note': note.strip(),
                    'before_quantity': current_quantity,
                    'after_quantity': result['new_quantity']
                }
                # フォーム付近通知用フラグもセット
                st.session_state.inbound_form_success = {
                    'item_name': selected_item['item_name'],
                    'quantity': validated_qty,
                    'after_quantity': result['new_quantity']
                }
                # 連打防止
                st.session_state.inbound_button_disabled = True
                
                # ページをリロードして成功メッセージを表示
                st.rerun()
            else:
                st.error(f"### ❌ 入庫処理に失敗しました")
                st.error(result["message"])
    
    # 短い成功通知（フォーム終了後、詳細カードの直前）
    form_notification = st.empty()
    if "inbound_form_success" in st.session_state and st.session_state.inbound_form_success:
        success_msg = st.session_state.inbound_form_success
        with form_notification.container():
            st.success(f"✅ **入庫が完了しました！** {success_msg['item_name']} x {success_msg['quantity']}個 → 在庫{success_msg['after_quantity']}個")
        # フラグクリア（表示後に削除）
        del st.session_state.inbound_form_success
    
    # 成功内容カード表示（フォームの下、直近履歴の上）
    if "inbound_success_display" in st.session_state:
        success_data = st.session_state.inbound_success_display
        st.divider()
        with st.container(border=True):
            st.subheader("📋 入庫完了内容")
            st.balloons()

            col1, col2 = st.columns(2)
            with col1:
                st.metric("入庫物品", success_data['item_name'])
                st.metric("入庫数量", f"{success_data['quantity']} 個", delta=f"+{success_data['quantity']}")
                st.metric("入庫者", success_data['user_name'])

            with col2:
                st.metric("入庫前在庫", f"{success_data['before_quantity']} 個")
                st.metric("入庫後在庫", f"{success_data['after_quantity']} 個")
                if success_data.get('department'):
                    st.metric("部署", success_data['department'])

            if success_data.get('note'):
                st.info(f"📝 備考: {success_data['note']}")
        
        # フラグをクリア
        del st.session_state.inbound_success_display
        if "inbound_success_shown" in st.session_state:
            del st.session_state.inbound_success_shown
    
    # 直近の入庫履歴を表示（最下部に配置）
    st.divider()
    st.subheader("⏪ 直近の入庫を取り消す")
    st.caption("※ 直近5件を表示")
    
    recent_inbound = get_recent_history_for_undo("IN", limit=5)
    if recent_inbound:
        for record in recent_inbound:
            created_at = parse_db_ts_to_jst(record["created_at"])
            time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            
            # 取消可能かチェック（10分以内）
            can_undo, reason = can_undo_history(record['id'], minutes=10)
            
            with st.container(border=True):
                col1, col2 = st.columns([5, 2])
                
                with col1:
                    st.markdown(f"**📦 {record['item_name']}** ({record['item_code']})")
                    st.caption(f"⏱️ {minutes_ago}分前 | 数量: {record['quantity']}個 | 担当: {record['user_name']}")
                
                with col2:
                    if not can_undo:
                        # 取消不可（10分超過または取消済み）
                        st.button(f"🚫 {reason}", key=f"undo_in_{record['id']}", disabled=True, use_container_width=True)
                    else:
                        # 確認ダイアログ付き取消ボタン
                        if f"confirm_undo_in_{record['id']}" not in st.session_state:
                            st.session_state[f"confirm_undo_in_{record['id']}"] = False
                        
                        if not st.session_state[f"confirm_undo_in_{record['id']}"]:
                            if st.button("↩️ 取消", key=f"undo_in_{record['id']}", use_container_width=True):
                                st.session_state[f"confirm_undo_in_{record['id']}"] = True
                                st.rerun()
                        else:
                            st.error("本当に取り消しますか？")
                            col_yes, col_no = st.columns(2)
                            with col_yes:
                                if st.button("✅ はい", key=f"yes_in_{record['id']}", type="primary"):
                                    result = process_undo(record['id'], record['user_name'])
                                    st.session_state[f"confirm_undo_in_{record['id']}"] = False
                                    if result["success"]:
                                        st.session_state.last_undo_inbound_success = result["message"]
                                    else:
                                        st.session_state.last_undo_inbound_error = result["message"]
                                    st.rerun()
                            with col_no:
                                if st.button("❌ いいえ", key=f"no_in_{record['id']}"):
                                    st.session_state[f"confirm_undo_in_{record['id']}"] = False
                                    st.rerun()
    else:
        st.info("📭 入庫履歴がありません")


def show_history_page():
    """履歴ページ"""
    st.header("📋 履歴")
    
    # 更新ボタン
    show_refresh_button()
    
    st.info("💡 入庫・出庫の履歴を確認できます。")
    
    # 取消処理結果メッセージを表示
    if "cancel_success_message" in st.session_state and st.session_state.cancel_success_message:
        st.success(st.session_state.cancel_success_message)
        st.session_state.cancel_success_message = None
    
    if "cancel_error_message" in st.session_state and st.session_state.cancel_error_message:
        st.error(st.session_state.cancel_error_message)
        st.session_state.cancel_error_message = None
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")
    
    # タブで「確定履歴」と「申請（承認待ち）」を分ける
    tab1, tab2 = st.tabs(["✅ 確定履歴", "📝 申請（承認待ち）"])
    
    # ========== タブ1: 確定履歴 ==========
    with tab1:
        # フィルタフォーム
        st.subheader("🔍 履歴検索")
    
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        
        with col1:
            period_option = st.selectbox(
                "期間",
                options=["全期間", "今日", "7日間", "30日間", "90日間"],
                key="history_period"
            )
            
            # 期間を日数に変換
            period_map = {
                "全期間": None,
                "今日": 1,
                "7日間": 7,
                "30日間": 30,
                "90日間": 90
            }
            period_days = period_map[period_option]
        
        with col2:
            change_type_filter = st.selectbox(
                "種別",
                options=["すべて", "IN", "OUT", "DISPOSE"],
                format_func=lambda x: {"すべて": "すべて", "IN": "入庫", "OUT": "出庫", "DISPOSE": "廃棄"}[x],
                key="history_change_type"
            )
        
        with col3:
            search_query_history = st.text_input(
                "検索",
                placeholder="品目名、品目コードで検索",
                key="search_query_history"
            )
        
        with col4:
            st.write("")  # スペース調整
            st.write("")
            search_button_history = st.button("🔎 検索", key="search_btn_history", use_container_width=True)
        
        st.divider()
        
        # 履歴データ取得
        history_data = get_history_list(
            period_days=period_days,
            change_type=change_type_filter,
            search_query=search_query_history
        )
        
        if not history_data:
            st.warning("⚠️ 該当する履歴がありません")
        else:
            st.info(f"📊 {len(history_data)} 件の履歴が見つかりました")
            
            try:
                # データフレーム作成
                df = pd.DataFrame(history_data)
                
                # 必要なカラムが存在しない場合は追加（NaNで埋める）
                if 'total_price' not in df.columns:
                    df['total_price'] = None
                if 'unit_price' not in df.columns:
                    df['unit_price'] = None
                if 'vendor_name' not in df.columns:
                    df['vendor_name'] = None
                
                # 数値カラムを安全に変換（NULL/NaN対策）
                df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce').fillna(0)
                df['total_price'] = pd.to_numeric(df['total_price'], errors='coerce')
                df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)
                
                # 金額計算（total_price優先、なければ数量×単価）
                df['amount'] = df.apply(lambda r: 
                    r['total_price'] if pd.notna(r['total_price']) 
                    else abs(r['quantity']) * r['unit_price'], 
                    axis=1
                )
                
                # 円表示用のヘルパー関数
                def yen(x):
                    return f"¥{int(x):,}"
                
                # 表示用に整形
                # created_atをUTCとして解釈し、JSTに変換して表示
                ts_jst = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Asia/Tokyo")

                display_df = pd.DataFrame({
                    "日時": ts_jst.dt.strftime("%Y-%m-%d %H:%M"),
                    "種別": df["change_type"].map({
                        "IN": "➕ 入庫", 
                        "OUT": "➖ 出庫", 
                        "DISPOSE": "🗑️ 廃棄"
                    }).fillna(df["change_type"]),  # マップにない値はそのまま表示
                    "品目名": df["item_name"],
                    "品目コード": df["item_code"],
                    "数量": df["quantity"].abs().astype(int).astype(str) + " 個",
                    "単価": df["unit_price"].apply(yen),
                    "金額": df["amount"].apply(yen),
                    "業者名": df["vendor_name"].fillna("-"),
                    "保管場所": df["location"].fillna("未設定"),
                    "担当者": df["user_name"],
                    "部署": df["department"].fillna("-"),
                    "備考": df["note"].fillna("-")
                })
                
                # データフレーム表示
                st.dataframe(
                    display_df,
                    width='stretch',
                    hide_index=True,
                    height=600
                )
            except Exception as e:
                st.error(f"❌ データフレーム作成エラー: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
                st.write("デバッグ: データの最初のレコード")
                if history_data:
                    st.json(history_data[0])
            
            # 統計情報表示
            st.divider()
            st.subheader("📈 統計情報")
            
            col1, col2, col3 = st.columns([3, 3, 3])
            
            with col1:
                total_in = df[df["change_type"] == "IN"]["quantity"].sum()
                st.metric("総入庫数", f"{int(total_in)} 個")
            
            with col2:
                total_out = df[df["change_type"] == "OUT"]["quantity"].sum()
                st.metric("総出庫数", f"{int(total_out)} 個")
            
            with col3:
                net_change = total_in - total_out
                st.metric("純増減", f"{int(net_change):+d} 個", delta=int(net_change))
            
            # CSV出力用データ作成
            # created_atをUTCとして解釈し、JSTに変換して出力
            ts_jst = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Asia/Tokyo")

            csv_df = pd.DataFrame({
                "日時": ts_jst.dt.strftime("%Y-%m-%d %H:%M:%S"),
                "種別": df["change_type"].map({"IN": "入庫", "OUT": "出庫", "DISPOSE": "廃棄"}),
                "品目名": df["item_name"],
                "品目コード": df["item_code"],
                "数量": df["quantity"].abs().astype(int),
                "単価": df["unit_price"].astype(int),
                "金額": df["amount"].astype(int),
                "業者名": df["vendor_name"].fillna(""),
                "保管場所": df["location"].fillna("未設定"),
                "担当者": df["user_name"],
                "部署": df["department"].fillna(""),
                "備考": df["note"].fillna("")
            })
            
            # CSVデータをバイトに変換
            csv_data = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            
            # ファイル名生成
            filename = f"history_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 CSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )
    
    # ========== タブ2: 申請（承認待ち） ==========
    with tab2:
        st.subheader("📝 承認待ち申請一覧")
        
        # 表示対象を権限に応じて決定
        current_user = get_current_user()
        user_role = get_user_role()
        
        if is_admin():
            st.info("💡 管理者として全部署の申請を表示しています。")
            pending_list = get_pending_for_history(user_role="ADMIN")
        elif is_guest():
            st.info("💡 自分の申請のみ表示しています。")
            pending_list = get_pending_for_history(
                user_id=current_user.get("id"),
                user_role="GUEST"
            )
        else:
            # USER
            dept_name = current_user.get("department", "")
            st.info(f"💡 「{dept_name}」部署の申請を表示しています。")
            pending_list = get_pending_for_history(
                department_id=current_user.get("department_id"),
                user_role="USER"
            )
        
        if not pending_list:
            st.success("🎉 承認待ちの申請はありません")
        else:
            st.warning(f"⚠️ {len(pending_list)} 件の承認待ち申請があります")
            
            for pending in pending_list:
                created_at = parse_db_ts_to_jst(pending["created_at"])
                time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
                minutes_ago = int(time_diff.total_seconds() / 60)
                hours_ago = minutes_ago // 60
                
                # 経過時間表示
                if hours_ago > 0:
                    time_display = f"{hours_ago}時間{minutes_ago % 60}分前"
                else:
                    time_display = f"{minutes_ago}分前"
                
                with st.container(border=True):
                    col1, col2, col3 = st.columns([4, 2, 2])
                    
                    with col1:
                        change_type_label = "➖ 出庫" if pending['change_type'] == 'OUT' else "➕ 入庫"
                        st.markdown(f"**{change_type_label}** {pending['item_name']} ({pending['item_code']})")
                        st.caption(f"⏱️ {time_display} | 数量: {pending['quantity']}個 | 申請者: {pending['actor_name']}")
                        st.caption(f"🏢 部署: {pending.get('department_name', 'N/A')}")
                        if pending.get('note'):
                            st.caption(f"📝 {pending['note']}")
                    
                    with col2:
                        st.markdown("🔶 **承認待ち**")
                    
                    with col3:
                        # GUESTの場合のみ取り下げボタン表示（guest_user_id一致）
                        if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                            confirm_key = f"confirm_cancel_hist_{pending['id']}"
                            if confirm_key not in st.session_state:
                                st.session_state[confirm_key] = False
                            
                            if not st.session_state[confirm_key]:
                                if st.button("🗑️ 取り下げ", key=f"cancel_hist_{pending['id']}", use_container_width=True):
                                    st.session_state[confirm_key] = True
                                    st.rerun()
                            else:
                                st.caption("⬇️ 下に入力欄")
                        else:
                            st.caption("承認待ち中")
                
                # 取り下げ確認フォーム（コンテナの外に配置して見やすく）
                if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                    confirm_key = f"confirm_cancel_hist_{pending['id']}"
                    if confirm_key in st.session_state and st.session_state[confirm_key]:
                        actor_input_key = f"actor_hist_{pending['id']}"
                        st.warning("⚠️ 取り下げるには、申請時に入力した名前を再入力してください")
                        actor_confirm = st.text_input("申請者名（本人確認用）", key=actor_input_key, placeholder="例: 山田太郎")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ 取り下げ確定", key=f"yes_hist_{pending['id']}", type="primary", use_container_width=True):
                                if not actor_confirm.strip():
                                    st.session_state.cancel_error_message = "❌ 名前を入力してください"
                                    st.rerun()
                                elif actor_confirm.strip() != pending['actor_name']:
                                    st.session_state.cancel_error_message = "❌ 申請者名が一致しません。申請者本人でなければ取消処理はできません。"
                                    st.session_state[confirm_key] = False
                                    st.rerun()
                                else:
                                    result = cancel_pending_transaction(pending['id'], current_user['id'], actor_confirm.strip())
                                    st.session_state[confirm_key] = False
                                    if result["success"]:
                                        st.session_state.cancel_success_message = f"✅ 申請を取り下げました: {pending['item_name']} {pending['quantity']}個"
                                    else:
                                        st.session_state.cancel_error_message = result["message"]
                                    st.rerun()
                        with col_no:
                            if st.button("❌ キャンセル", key=f"no_hist_{pending['id']}", use_container_width=True):
                                st.session_state[confirm_key] = False
                                st.rerun()


def show_purchase_order_inbound_tab():
    """発注品入庫タブの内容"""
    st.info("💡 発注済みで到着待ちの物品を入庫処理します。")
    
    # 成功メッセージの表示（前回の処理結果）
    if "receive_success_message" in st.session_state and st.session_state.receive_success_message:
        msg = st.session_state.receive_success_message
        st.success(f"✅ {msg['title']}")
        st.info(f"📦 {msg['item_name']} - {msg['qty']}個を入庫しました")
        st.info(f"📊 新しい在庫数: {msg['new_quantity']}個")
        if msg.get('history_id'):
            st.caption(f"📝 履歴ID: {msg['history_id']} として記録されました")
            
            # デバッグ: 実際にDBに保存されたか確認
            from db import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inventory_history WHERE id = ?", (msg['history_id'],))
                saved_record = cursor.fetchone()
                if saved_record:
                    st.success(f"✅ データベース確認: 履歴ID {msg['history_id']} は正常に保存されています")
                    with st.expander("🔍 保存データの詳細"):
                        st.json(dict(saved_record))
                else:
                    st.error(f"❌ データベースエラー: 履歴ID {msg['history_id']} が見つかりません")
        
        st.balloons()
        # メッセージをクリア
        st.session_state.receive_success_message = None
    
    # 現在のユーザー情報を取得
    current_user = get_current_user()
    user_role = current_user.get("user_role", "GUEST")
    department_name = current_user.get("department")
    
    # デバッグ情報
    st.caption(f"🔍 デバッグ: ユーザー権限={user_role}, 部署={department_name}")
    
    # 発注済み申請を取得（ADMINは全体、それ以外は自部署のみ）
    if user_role == "ADMIN":
        ordered_requests = get_ordered_purchase_requests()
        st.caption(f"🔍 デバッグ: ADMIN として全体検索 → {len(ordered_requests) if ordered_requests else 0}件取得")
    else:
        ordered_requests = get_ordered_purchase_requests(department_name=department_name)
        st.caption(f"🔍 デバッグ: {department_name} で検索 → {len(ordered_requests) if ordered_requests else 0}件取得")
    
    # デバッグ: 比較用に get_purchase_requests でも取得
    from db import get_purchase_requests
    comparison_requests = get_purchase_requests(status="ORDERED", department=None if user_role == "ADMIN" else department_name)
    st.caption(f"🔍 比較: get_purchase_requests(ORDERED) → {len(comparison_requests) if comparison_requests else 0}件取得")
    
    if not ordered_requests:
        st.warning("📭 現在、入庫待ちの発注品はありません。")
        # デバッグ: 実際のステータスを確認
        if comparison_requests:
            st.error(f"⚠️ データ不整合: get_purchase_requests では {len(comparison_requests)}件 見つかっています")
            with st.expander("🔍 詳細確認"):
                for req in comparison_requests[:3]:  # 最初の3件のみ表示
                    st.json(req)
        return
    
    # ADMINの場合は全部署の入庫待ちを部署ごとに表示
    if user_role == "ADMIN":
        st.success(f"📦 **全部署で {len(ordered_requests)}件** の発注品が到着待ちです")
        
        # 部署ごとにグループ化
        from collections import defaultdict
        requests_by_department = defaultdict(list)
        for req in ordered_requests:
            dept = req.get('requested_by_department', '部署未設定')
            requests_by_department[dept].append(req)
        
        # 部署ごとに表示
        for dept_name in sorted(requests_by_department.keys()):
            dept_requests = requests_by_department[dept_name]
            with st.expander(f"🏢 **{dept_name}** - {len(dept_requests)}件の入庫待ち", expanded=True):
                for req in dept_requests:
                    display_purchase_order_card(req, current_user, user_role)
    else:
        st.success(f"📦 **{len(ordered_requests)}件** の発注品が到着待ちです")
        for req in ordered_requests:
            display_purchase_order_card(req, current_user, user_role)


def display_purchase_order_card(req, current_user, user_role):
    """発注品の入庫カード表示（共通化）"""
    with st.container(border=True):
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 2])
            
            with col1:
                st.markdown(f"### 📦 {req['item_name']}")
                st.caption(f"品目コード: {req['item_code']}")
                if req.get('vendor_name'):
                    st.caption(f"業者: {req['vendor_name']}")
            
            with col2:
                st.metric("発注数量", f"{req['requested_qty']} 個")
                if req.get('unit_price'):
                    total = req['requested_qty'] * req['unit_price']
                    st.caption(f"金額: ¥{total:,}")
            
            with col3:
                if req.get('ordered_at'):
                    ordered_date = parse_db_ts_to_jst(req['ordered_at'])
                    days_ago = (datetime.now(ZoneInfo('Asia/Tokyo')) - ordered_date).days
                    st.metric("発注日", f"{days_ago}日前")
            
            # 詳細情報を展開表示
            with st.expander("📋 詳細情報"):
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.write(f"**申請者:** {req.get('requester_name', '不明')}")
                    st.write(f"**部署:** {req.get('requested_by_department', '不明')}")
                    if req.get('priority'):
                        st.write(f"**優先度:** {req['priority']}")
                with info_col2:
                    if req.get('approver_name'):
                        st.write(f"**承認者:** {req['approver_name']}")
                    if req.get('order_channel'):
                        st.write(f"**発注方法:** {req['order_channel']}")
                    if req.get('generated_document_name'):
                        st.write(f"**発注書:** {req['generated_document_name']}")
                
                if req.get('note'):
                    st.info(f"📝 申請メモ: {req['note']}")
            
            # 入庫処理フォーム
            with st.form(f"receive_form_{req['id']}"):
                st.subheader("📥 入庫処理")
                
                form_col1, form_col2 = st.columns(2)
                
                with form_col1:
                    received_qty = st.number_input(
                        "入庫数量",
                        min_value=1,
                        max_value=10000,
                        value=req['requested_qty'],
                        step=1,
                        help="実際に入庫した数量を入力してください（発注数量と異なる場合は修正可）",
                        key=f"qty_{req['id']}"
                    )
                
                with form_col2:
                    st.text_input(
                        "入庫担当者",
                        value=current_user.get("display_name", ""),
                        disabled=True,
                        help="ログインユーザーが自動設定されます",
                        key=f"user_{req['id']}"
                    )
                
                received_note = st.text_area(
                    "入庫メモ（任意）",
                    placeholder="例: 一部破損あり、検品完了、など",
                    height=80,
                    key=f"note_{req['id']}"
                )
                
                col_submit, col_info = st.columns([1, 3])
                with col_submit:
                    submitted = st.form_submit_button(
                        "📦 納品を完了する",
                        type="primary",
                        use_container_width=True
                    )
                with col_info:
                    if req['requested_qty'] != received_qty:
                        st.warning(f"⚠️ 発注数と入庫数が異なります（発注: {req['requested_qty']}個）")
                
                if submitted:
                    # 入庫処理実行
                    result = receive_purchase_order(
                        request_id=req['id'],
                        received_qty=received_qty,
                        received_note=received_note.strip(),
                        user_id=current_user['id']
                    )
                    
                    if result['success']:
                        # セッション状態に成功メッセージを保存
                        st.session_state.receive_success_message = {
                            'title': '納品完了しました！',
                            'item_name': req['item_name'],
                            'qty': received_qty,
                            'new_quantity': result['new_quantity'],
                            'history_id': result.get('history_id')
                        }
                        # ページをリロード
                        st.rerun()
                    else:
                        st.error(f"❌ 納品処理に失敗しました: {result['message']}")
        
        st.divider()


def get_all_items_for_adjust():
    """在庫調整用の全物品リストを取得"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                i.id, i.item_name, i.item_code, i.category,
                inv.quantity, inv.location
            FROM items i
            LEFT JOIN inventory inv ON i.id = inv.item_id
            ORDER BY i.item_name
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def show_adjust_page():
    """在庫調整ページ（管理者専用）"""
    st.header("🔧 在庫調整")
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "在庫調整は管理者のみ使用できます"):
        return
    
    st.info("💡 管理者専用機能：在庫数量を直接調整できます。棚卸しや誤差修正などにご使用ください。")
    
    # 前回の調整成功メッセージを表示
    if "last_adjust_success" in st.session_state and st.session_state.last_adjust_success:
        success_data = st.session_state.last_adjust_success
        
        st.success("### ✅ 在庫調整が完了しました！")
        st.balloons()
        
        st.markdown("---")
        st.subheader("📋 調整完了内容")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**物品名:** {success_data['item_name']}")
            st.write(f"**調整前:** {success_data['old_quantity']} 個")
            st.write(f"**調整後:** {success_data['new_quantity']} 個")
        with col2:
            diff = success_data['new_quantity'] - success_data['old_quantity']
            direction = "増加 ⬆️" if diff > 0 else "減少 ⬇️"
            st.write(f"**変動:** {direction} {abs(diff)} 個")
            st.write(f"**理由:** {success_data['reason']}")
            st.write(f"**調整者:** {success_data['user_name']}")
        
        st.markdown("---")
        
        if st.button("🔄 続けて調整する", use_container_width=True):
            st.session_state.last_adjust_success = None
            st.rerun()
        
        return
    
    # 全物品を取得
    items = get_all_items_for_adjust()
    
    if not items:
        st.warning("⚠️ 調整対象の物品がありません")
        return
    
    st.subheader("📝 調整対象を選択")
    
    # 物品選択
    item_options = {
        f"{item['item_name']} (現在: {item.get('quantity', 0)}個) [{item.get('category', '-')}]": item['id']
        for item in items
    }
    
    selected_item_display = st.selectbox(
        "物品を選択",
        options=list(item_options.keys()),
        help="調整する物品を選択してください",
        key="adjust_item_select"
    )
    
    selected_item_id = item_options[selected_item_display]
    selected_item = next(item for item in items if item['id'] == selected_item_id)
    
    # 現在の在庫情報を表示
    current_quantity = selected_item.get('quantity', 0) or 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("現在在庫", f"{current_quantity} 個")
    with col2:
        st.metric("保管場所", selected_item.get('location') or "未設定")
    with col3:
        st.metric("カテゴリ", selected_item.get('category', '-'))
    
    st.divider()
    
    # 調整フォーム
    with st.form("adjust_form", clear_on_submit=True):
        st.subheader("🔢 調整内容を入力")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_quantity = st.number_input(
                "調整後の数量",
                min_value=0,
                max_value=100000,
                value=current_quantity,
                step=1,
                help="調整後の在庫数量を入力してください（0以上）"
            )
        
        with col2:
            # 差分をリアルタイム表示するため計算
            diff = new_quantity - current_quantity
            if diff > 0:
                st.info(f"⬆️ {diff} 個 増加")
            elif diff < 0:
                st.info(f"⬇️ {abs(diff)} 個 減少")
            else:
                st.info("変更なし")
        
        # 理由（必須）
        reason = st.text_area(
            "調整理由 *（必須）",
            placeholder="例: 棚卸し差異修正、破損廃棄、システム誤差修正など",
            height=100,
            help="調整理由は必須です。監査のため詳細に記録してください。"
        )
        
        # ユーザー情報（自動）
        current_user = get_current_user()
        st.caption(f"📝 調整者: {current_user.get('display_name', '')} ({current_user.get('department', '')})")
        
        st.divider()
        
        # 送信ボタン
        col1, col2 = st.columns([3, 1])
        with col1:
            st.warning("⚠️ 調整操作は取り消せません。内容をよく確認してください。")
        with col2:
            submitted = st.form_submit_button(
                "🔧 調整を実行",
                type="primary",
                use_container_width=True
            )
        
        if submitted:
            # バリデーション
            if not reason or reason.strip() == "":
                st.error("❌ 調整理由を入力してください（必須）")
            elif new_quantity == current_quantity:
                st.warning("⚠️ 数量に変更がありません")
            else:
                # 調整処理実行
                result = process_adjust(
                    item_id=selected_item_id,
                    new_quantity=new_quantity,
                    user_name=current_user.get("display_name", ""),
                    department=current_user.get("department", ""),
                    reason=reason.strip()
                )
                
                if result["success"]:
                    # 成功データをsession_stateに保存
                    st.session_state.last_adjust_success = {
                        'item_name': selected_item['item_name'],
                        'old_quantity': current_quantity,
                        'new_quantity': new_quantity,
                        'reason': reason.strip(),
                        'user_name': current_user.get("display_name", "")
                    }
                    st.rerun()
                else:
                    st.error(result["message"])


def show_approval_page():
    """承認管理ページ（USER/ADMIN専用）"""
    st.header("✅ 承認管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：USER以上
    if not require_min_role("USER", "承認管理は一般ユーザー以上のみ使用できます"):
        return
    
    # 前回の処理結果メッセージを表示
    if "approval_success_message" in st.session_state and st.session_state.approval_success_message:
        st.success(st.session_state.approval_success_message)
        st.session_state.approval_success_message = None
    
    if "approval_error_message" in st.session_state and st.session_state.approval_error_message:
        st.error(st.session_state.approval_error_message)
        st.session_state.approval_error_message = None
    
    current_user = get_current_user()
    user_dept_id = current_user.get("department_id")
    
    # ADMINは全部署、USERは自部署のみ
    if is_admin():
        st.info("💡 管理者として全部署の承認待ち申請を表示しています。")
        pending_list = get_pending_transactions()  # 全件
    else:
        dept_name = current_user.get("department", "")
        st.info(f"💡 「{dept_name}」部署の承認待ち申請を表示しています。")
        pending_list = get_pending_transactions(department_id=user_dept_id)  # 自部署のみ
    
    if not pending_list:
        st.success("🎉 承認待ちの申請はありません")
        return
    
    st.subheader(f"📋 承認待ち申請: {len(pending_list)} 件")
    
    for pending in pending_list:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 2])
            
            with col1:
                # 申請種別
                change_type_label = "➖ 出庫" if pending['change_type'] == 'OUT' else "➕ 入庫"
                st.markdown(f"### {change_type_label}")
                
                # 物品情報
                st.markdown(f"**物品:** {pending.get('item_name', 'N/A')} ({pending.get('item_code', 'N/A')})")
                st.markdown(f"**数量:** {pending['quantity']} 個")
                
                # 申請者情報
                st.caption(f"👤 申請者: {pending['actor_name']}")
                st.caption(f"🏢 部署: {pending.get('department_name', 'N/A')}")
                
                if pending.get('note'):
                    st.caption(f"📝 備考: {pending['note']}")
                
                st.caption(f"🕒 申請日時: {pending['created_at']}")
            
            with col2:
                # 現在在庫確認
                item = get_item_by_id(pending['item_id'])
                if item:
                    current_qty = item.get('quantity', 0)
                    st.metric("現在在庫", f"{current_qty} 個")
                    
                    # 出庫の場合、在庫が足りるかチェック
                    if pending['change_type'] == 'OUT':
                        if current_qty < pending['quantity']:
                            st.error(f"⚠️ 在庫不足！")
                else:
                    st.warning("物品が見つかりません")
            
            with col3:
                # 承認・却下ボタン
                st.write("**操作:**")
                
                # 二重実行防止フラグ
                processing_key = f"processing_approval_{pending['id']}"
                is_processing = st.session_state.get(processing_key, False)
                
                # 却下理由入力
                reject_key = f"reject_reason_{pending['id']}"
                
                # 承認ボタン（二重実行防止対応）
                if st.button("✅ 承認", key=f"approve_{pending['id']}", use_container_width=True, type="primary", disabled=is_processing):
                    st.session_state[processing_key] = True
                    # 在庫チェック（出庫の場合）
                    if pending['change_type'] == 'OUT':
                        item = get_item_by_id(pending['item_id'])
                        if item and item.get('quantity', 0) < pending['quantity']:
                            st.session_state.approval_error_message = "❌ 在庫が不足しているため承認できません"
                            if processing_key in st.session_state:
                                del st.session_state[processing_key]
                            st.rerun()
                        else:
                            result = approve_pending_transaction(pending['id'], current_user['id'])
                            if result["success"]:
                                item_name = pending.get('item_name', '物品')
                                qty = pending['quantity']
                                actor = pending['actor_name']
                                log_approve(get_user_display_name(), pending['id'], "pending_transaction")
                                st.session_state.approval_success_message = f"✅ 1件の申請を承認しました: {item_name} {qty}個（申請者: {actor}）"
                            else:
                                st.session_state.approval_error_message = result["message"]
                            if processing_key in st.session_state:
                                del st.session_state[processing_key]
                            st.rerun()
                    else:
                        result = approve_pending_transaction(pending['id'], current_user['id'])
                        if result["success"]:
                            item_name = pending.get('item_name', '物品')
                            qty = pending['quantity']
                            actor = pending['actor_name']
                            log_approve(get_user_display_name(), pending['id'], "pending_transaction")
                            st.session_state.approval_success_message = f"✅ 1件の申請を承認しました: {item_name} {qty}個（申請者: {actor}）"
                        else:
                            st.session_state.approval_error_message = result["message"]
                        if processing_key in st.session_state:
                            del st.session_state[processing_key]
                        st.rerun()
                
                # 却下ボタン
                with st.expander("却下する場合"):
                    reject_reason = st.text_input("却下理由", key=reject_key, placeholder="理由を入力")
                    reject_processing_key = f"processing_reject_{pending['id']}"
                    is_reject_processing = st.session_state.get(reject_processing_key, False)
                    if st.button("❌ 却下", key=f"reject_{pending['id']}", use_container_width=True, disabled=is_reject_processing):
                        # 却下理由バリデーション
                        ok, reason_clean, err = validate_required_string(reject_reason, field_name="却下理由", min_length=1)
                        if not ok:
                            st.warning("却下理由を入力してください")
                        else:
                            st.session_state[reject_processing_key] = True
                            result = reject_pending_transaction(pending['id'], current_user['id'], reason_clean)
                            if result["success"]:
                                item_name = pending.get('item_name', '物品')
                                log_reject(get_user_display_name(), pending['id'], "pending_transaction", reason_clean)
                                st.session_state.approval_success_message = f"❌ 1件の申請を却下しました: {item_name}（理由: {reason_clean}）"
                            else:
                                st.session_state.approval_error_message = result["message"]
                            if reject_processing_key in st.session_state:
                                del st.session_state[reject_processing_key]
                            st.rerun()


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
    
    # タブで機能を分割
    tab1, tab2 = st.tabs(["📋 ユーザー一覧", "➕ 新規作成"])
    
    # ========== タブ1: ユーザー一覧・編集 ==========
    with tab1:
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
    with tab2:
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


def show_item_master_management_page():
    """物品マスター管理ページ（管理者専用）- 表形式表示"""
    st.header("📦 物品マスター管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "物品管理は管理者のみ使用できます"):
        return
    
    # タブで「一覧」「新規登録」「カテゴリ管理」「CSV取り込み」を分ける
    tab1, tab2, tab3, tab4 = st.tabs(["📋 物品一覧", "➕ 新規登録", "🏷️ カテゴリ管理", "📥 CSV取り込み"])
    
    with tab1:
        # === 物品一覧（表形式） ===
        st.subheader("📋 物品一覧")
        
        # フィルタ・検索エリア
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        
        with col1:
            search_query = st.text_input("🔍 検索（品目名/品目コード/業者名/業者品番）", placeholder="キーワード入力", key="item_search")
        
        with col2:
            category_names = ["すべて"] + get_category_names()
            category_filter = st.selectbox("カテゴリ", options=category_names, key="item_category_filter")
            if category_filter == "すべて":
                category_filter = ""
        
        with col3:
            # デフォルトは「消耗品」
            asset_filter = st.selectbox("種別", options=["消耗品", "資産", "すべて"], index=0, key="item_asset_filter")
        
        with col4:
            show_inactive = st.checkbox("無効も表示", value=False, key="item_show_inactive")
        
        # 部署タグフィルタ（オプション）
        departments = get_all_departments(active_only=True)
        dept_names = ["すべて"] + [dept['name'] for dept in departments]
        department_tag_filter = st.selectbox("📌 利用部署タグ", options=dept_names, key="item_dept_filter")
        if department_tag_filter == "すべて":
            department_tag_filter = ""
        
        st.divider()
        
        # ページング設定
        if "item_page" not in st.session_state:
            st.session_state.item_page = 0
        
        items_per_page = 50
        offset = st.session_state.item_page * items_per_page
        
        # 物品一覧を取得（SQL絞り込み）
        items = list_items(
            include_inactive=show_inactive,
            search_query=search_query,
            category_filter=category_filter,
            asset_filter=asset_filter,
            department_tag_filter=department_tag_filter,
            limit=items_per_page,
            offset=offset
        )
        
        # 総件数を取得
        total_count = count_items(
            include_inactive=show_inactive,
            search_query=search_query,
            category_filter=category_filter,
            asset_filter=asset_filter,
            department_tag_filter=department_tag_filter
        )
        
        total_pages = (total_count + items_per_page - 1) // items_per_page if total_count > 0 else 1
        
        # 件数表示
        st.caption(f"📊 {total_count} 件中 {offset+1}〜{min(offset+len(items), total_count)} 件を表示")
        
        if not items:
            st.info("📭 条件に合致する物品がありません")
        else:
            # テーブル表示用のデータフレームを作成
            import pandas as pd
            table_data = []
            for item in items:
                table_data.append({
                    "ID": item.get('id'),
                    "状態": "🟢" if item.get('is_active') else "🔴",
                    "品目名": item.get('item_name', '-'),
                    "カテゴリ": item.get('category', '-'),
                    "品目コード": item.get('item_code') or "-",
                    "業者名": item.get('vendor_name') or "-",
                    "業者品番": item.get('vendor_item_code') or "-",
                    "単価": f"¥{item.get('unit_price', 0):,.0f}",
                    "種別": "資産" if item.get('is_asset') else "消耗品",
                    "部署タグ": item.get('department_tags') or "-"
                })
            
            df = pd.DataFrame(table_data)
            
            # データフレーム表示（インタラクティブ）
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "状態": st.column_config.TextColumn("状態", width="small"),
                    "品目名": st.column_config.TextColumn("品目名", width="medium"),
                    "カテゴリ": st.column_config.TextColumn("カテゴリ", width="small"),
                    "品目コード": st.column_config.TextColumn("品目コード", width="small"),
                    "業者名": st.column_config.TextColumn("業者名", width="small"),
                    "業者品番": st.column_config.TextColumn("業者品番", width="small"),
                    "単価": st.column_config.TextColumn("単価", width="small"),
                    "種別": st.column_config.TextColumn("種別", width="small"),
                    "部署タグ": st.column_config.TextColumn("部署タグ", width="medium")
                }
            )
            
            # ページング操作
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("◀ 前へ", disabled=(st.session_state.item_page == 0), use_container_width=True):
                    st.session_state.item_page -= 1
                    st.rerun()
            with col_page:
                st.write(f"📄 ページ {st.session_state.item_page + 1} / {total_pages}")
            with col_next:
                if st.button("次へ ▶", disabled=(st.session_state.item_page >= total_pages - 1), use_container_width=True):
                    st.session_state.item_page += 1
                    st.rerun()
            
            st.divider()
            
            # 詳細表示・操作エリア
            st.subheader("🔍 物品詳細・操作")
            selected_id = st.number_input("物品IDを入力", min_value=1, value=items[0]['id'] if items else 1, step=1, key="selected_item_id")
            
            if st.button("📄 詳細表示", use_container_width=True):
                st.session_state.viewing_item_id = selected_id
            
            # 詳細表示パネル
            if 'viewing_item_id' in st.session_state and st.session_state.viewing_item_id:
                item = get_item_master_by_id(st.session_state.viewing_item_id)
                if item:
                    st.success(f"✅ 物品ID {item.get('id')}: {item.get('item_name', '-')}")
                    
                    col_detail1, col_detail2 = st.columns(2)
                    with col_detail1:
                        st.write(f"**品目名:** {item.get('item_name', '-')}")
                        st.write(f"**カテゴリ:** {item.get('category', '-')}")
                        st.write(f"**品目コード:** {item.get('item_code') or '-'}")
                        st.write(f"**業者名:** {item.get('vendor_name') or '-'}")
                        st.write(f"**業者品番:** {item.get('vendor_item_code') or '-'}")
                    
                    with col_detail2:
                        st.write(f"**単価:** ¥{item.get('unit_price', 0):,.0f}")
                        st.write(f"**種別:** {'資産' if item.get('is_asset') else '消耗品'}")
                        st.write(f"**使用頻度:** {item.get('frequency_tag') or '-'}")
                        st.write(f"**期限:** {item.get('expiry_date') or '-'}")
                        st.write(f"**部署タグ:** {item.get('department_tags') or '-'}")
                    
                    st.write(f"**状態:** {'🟢 有効' if item.get('is_active') else '🔴 無効'}")
                    
                    # 操作ボタン
                    col_btn1, col_btn2, col_btn3 = st.columns(3)
                    with col_btn1:
                        if st.button("✏️ 編集", key=f"detail_edit_{item.get('id')}", use_container_width=True, type="primary"):
                            st.session_state.editing_item_id = item.get('id')
                            st.rerun()
                    
                    with col_btn2:
                        if item.get('is_active'):
                            if st.button("🚫 無効化", key=f"detail_deactivate_{item.get('id')}", use_container_width=True):
                                result = deactivate_item(item.get('id'))
                                if result['success']:
                                    st.success(result['message'])
                                    st.rerun()
                                else:
                                    st.error(result['message'])
                        else:
                            if st.button("✅ 有効化", key=f"detail_activate_{item.get('id')}", use_container_width=True):
                                result = activate_item(item.get('id'))
                                if result['success']:
                                    st.success(result['message'])
                                    st.rerun()
                                else:
                                    st.error(result['message'])
                    
                    with col_btn3:
                        if st.button("❌ 閉じる", key="close_detail", use_container_width=True):
                            del st.session_state.viewing_item_id
                            st.rerun()
                else:
                    st.error(f"❌ 物品ID {st.session_state.viewing_item_id} が見つかりません")
    
    with tab2:
        # === 新規登録フォーム ===
        st.subheader("➕ 新規物品登録")
        
        # カテゴリ一覧を取得
        category_names = get_category_names()
        if not category_names:
            st.warning("⚠️ カテゴリが登録されていません。先に「カテゴリ管理」タブでカテゴリを登録してください。")
            return
        
        # 部署一覧を取得
        departments = get_all_departments(active_only=True)
        dept_names = [dept['name'] for dept in departments]
        
        # 業者一覧を取得
        vendor_names = get_vendor_names()
        if not vendor_names:
            st.warning("⚠️ 業者が登録されていません。先に「業者管理」で業者を登録してください。")
            return
        
        # フォームリセット用のキーを生成
        if "form_reset_counter" not in st.session_state:
            st.session_state.form_reset_counter = 0
        
        with st.form(key=f"new_item_form_{st.session_state.form_reset_counter}"):
            col1, col2 = st.columns(2)
            
            with col1:
                item_name = st.text_input("品目名 *", placeholder="例: コピー用紙 A4")
                category = st.selectbox("カテゴリ *", options=category_names)
                item_code = st.text_input("品目コード", placeholder="任意")
                vendor_name = st.selectbox("業者名", options=vendor_names)
            
            with col2:
                vendor_item_code = st.text_input("業者品番", placeholder="例: ABC-123")
                unit_price = st.number_input("単価（円）", min_value=0.0, value=0.0, step=100.0)
                frequency_tag = st.selectbox("使用頻度", ["", "高頻度", "中頻度", "低頻度"])
                # 期限（年月のみ）
                expiry_year = st.number_input("期限（年）", min_value=2020, max_value=2100, value=2026, step=1)
                expiry_month = st.selectbox("期限（月）", options=["なし"] + [f"{i}月" for i in range(1, 13)])
            
            # 業者情報を表示
            if vendor_name:
                vendor_info = get_vendor_by_name(vendor_name)
                if vendor_info:
                    st.info(f"📍 **所在地:** {vendor_info['address'] or '未登録'}  |  📞 **電話:** {vendor_info['phone'] or '未登録'}  |  📧 **メール:** {vendor_info['email'] or '未登録'}")
            
            # 管理部署の選択
            st.write("**管理部署（責任部署）**")
            owner_dept_names = ["未設定"] + dept_names
            owner_department = st.selectbox("発注・棚卸の担当部署", options=owner_dept_names)
            owner_department_id = None
            if owner_department != "未設定":
                for dept in departments:
                    if dept['name'] == owner_department:
                        owner_department_id = dept['id']
                        break
            
            # 利用部署タグ（複数選択）
            st.write("**利用部署タグ（複数選択可）**")
            is_common = st.checkbox("全社共通", key=f"is_common_{st.session_state.form_reset_counter}")
            selected_depts = []
            if not is_common:
                cols = st.columns(3)
                for i, dept_name in enumerate(dept_names):
                    with cols[i % 3]:
                        if st.checkbox(dept_name, key=f"dept_{dept_name}_{st.session_state.form_reset_counter}"):
                            selected_depts.append(dept_name)
            
            # 警告表示
            if not is_common and not selected_depts:
                st.warning("⚠️ 利用部署タグが未設定です。「全社共通」または部署を選択してください。")
            
            st.caption("* は必須項目です")
            st.caption("💡 品目コードがない場合は、業者名と業者品番が必須になります")
            st.caption("💡 単価が50,000円以上の場合、自動的に「資産」として登録されます")
            
            submitted = st.form_submit_button("✅ 登録", use_container_width=True, type="primary")
            
            if submitted:
                # === バリデーション実行 ===
                validation_errors = []
                
                # 品目名（必須）
                ok_name, validated_name, error_msg_name = validate_required_text(item_name, "品目名", max_len=100)
                if not ok_name:
                    validation_errors.append(error_msg_name)
                
                # カテゴリ（必須）
                if not category:
                    validation_errors.append("カテゴリを選択してください")
                
                # 単価（必須・0以上）
                ok_price, validated_price, error_msg_price = to_float_safe(unit_price, "単価", min_value=0.0, allow_zero=True)
                if not ok_price:
                    validation_errors.append(error_msg_price)
                else:
                    # 補正が行われた場合は警告表示
                    needs_warn, warn_msg = needs_correction_warning(unit_price, "currency")
                    if needs_warn:
                        st.warning(f"💡 単価: {warn_msg}")
                
                # 品目コードと業者情報のチェック
                if not item_code and (not vendor_name or not vendor_item_code):
                    validation_errors.append("品目コードがない場合は、業者名と業者品番が必須です")
                
                # エラーがあれば表示して終了
                if validation_errors:
                    for err in validation_errors:
                        st.error(err)
                else:
                    # 部署タグをカンマ区切りに変換
                    department_tags = ",".join(selected_depts) if selected_depts else None
                    
                    # 期限をYYYY-MM形式に変換
                    expiry_date = None
                    if expiry_month != "なし":
                        month_num = int(expiry_month.replace("月", ""))
                        expiry_date = f"{expiry_year}-{month_num:02d}"
                    
                    # 資産区分を自動設定（50,000円以上なら資産）
                    is_asset = 1 if validated_price >= 50000 else 0
                    
                    result = insert_item(
                        item_name=validated_name,
                        category=category,
                        item_code=item_code if item_code else None,
                        vendor_name=vendor_name if vendor_name else None,
                        vendor_item_code=vendor_item_code if vendor_item_code else None,
                        department_tags=department_tags,
                        unit_price=validated_price,
                        is_asset=is_asset,
                        frequency_tag=frequency_tag if frequency_tag else None,
                        expiry_date=expiry_date,
                        owner_department_id=owner_department_id,
                        is_common=1 if is_common else 0
                    )
                    
                    if result['success']:
                        # 成功メッセージをsession_stateに保存してリロード
                        st.session_state.item_register_success = result['message']
                        # フォームリセット用のカウンターをインクリメント
                        st.session_state.form_reset_counter += 1
                        st.rerun()
                    else:
                        st.error(result['message'])
        
        # 成功メッセージの表示（フォームの外、登録ボタンの下）
        if "item_register_success" in st.session_state:
            st.success(st.session_state.item_register_success)
            del st.session_state.item_register_success
    
    with tab3:
        # === カテゴリ管理 ===
        st.subheader("🏷️ カテゴリ管理")
        
        # 既存カテゴリ一覧
        categories = list_categories(include_inactive=False)
        if categories:
            st.write("**登録済みカテゴリ**")
            for cat in categories:
                st.write(f"• {cat['name']}")
        else:
            st.info("カテゴリが登録されていません")
        
        st.divider()
        
        # 新規カテゴリ追加フォーム
        st.write("**新規カテゴリ追加**")
        with st.form("new_category_form"):
            new_category_name = st.text_input("カテゴリ名", placeholder="例: 医療機器")
            category_submitted = st.form_submit_button("➕ カテゴリ追加", use_container_width=True, type="primary")
            
            if category_submitted:
                result = insert_category(new_category_name)
                if result['success']:
                    st.success(result['message'])
                    st.rerun()
                else:
                    st.error(result['message'])
    
    # 編集モーダル（session_stateで管理）
    if 'editing_item_id' in st.session_state and st.session_state.editing_item_id:
        item_id = st.session_state.editing_item_id
        item = get_item_master_by_id(item_id)
        
        if item:
            st.divider()
            st.subheader(f"✏️ 物品編集: {item.get('item_name', '-')}")
            
            # カテゴリ一覧と部署一覧と業者一覧を取得
            category_names = get_category_names()
            departments = get_all_departments(active_only=True)
            dept_names = [dept['name'] for dept in departments]
            vendor_names = get_vendor_names()
            
            with st.form(f"edit_item_form_{item_id}"):
                col1, col2 = st.columns(2)
                
                # カテゴリのインデックスを取得
                try:
                    cat_index = category_names.index(item.get('category', ''))
                except ValueError:
                    cat_index = 0
                
                # 業者のインデックスを取得
                vendor_index = 0
                if item.get('vendor_name') and item.get('vendor_name') in vendor_names:
                    vendor_index = vendor_names.index(item.get('vendor_name'))
                
                with col1:
                    item_name = st.text_input("品目名 *", value=item.get('item_name', ''))
                    category = st.selectbox("カテゴリ *", options=category_names, index=cat_index)
                    item_code = st.text_input("品目コード", value=item.get('item_code') or "")
                    vendor_name = st.selectbox("業者名", options=vendor_names, index=vendor_index)
                
                with col2:
                    vendor_item_code = st.text_input("業者品番", value=item.get('vendor_item_code') or "")
                    unit_price = st.number_input("単価（円）", min_value=0.0, value=float(item.get('unit_price', 0)), step=100.0)
                    frequency_tag = st.selectbox("使用頻度", ["", "高頻度", "中頻度", "低頻度"], 
                                                index=["", "高頻度", "中頻度", "低頻度"].index(item.get('frequency_tag') or ""))
                    # 期限（年月のみ）
                    expiry_year = 2026
                    expiry_month_val = "なし"
                    if item.get('expiry_date'):
                        try:
                            parts = item.get('expiry_date').split('-')
                            if len(parts) >= 2:
                                expiry_year = int(parts[0])
                                expiry_month_val = f"{int(parts[1])}月"
                        except:
                            pass
                    expiry_year = st.number_input("期限（年）", min_value=2020, max_value=2100, value=expiry_year, step=1)
                    expiry_month = st.selectbox("期限（月）", options=["なし"] + [f"{i}月" for i in range(1, 13)], 
                                               index=["なし"] + [f"{i}月" for i in range(1, 13)].index(expiry_month_val) if expiry_month_val in ["なし"] + [f"{i}月" for i in range(1, 13)] else 0)
                
                # 業者情報を表示
                if vendor_name:
                    vendor_info = get_vendor_by_name(vendor_name)
                    if vendor_info:
                        st.info(f"📍 **所在地:** {vendor_info['address'] or '未登録'}  |  📞 **電話:** {vendor_info['phone'] or '未登録'}  |  📧 **メール:** {vendor_info['email'] or '未登録'}")
                
                # 管理部署の選択
                st.write("**管理部署（責任部署）**")
                owner_dept_names = ["未設定"] + dept_names
                current_owner_dept = "未設定"
                if item.get('owner_department_id'):
                    for dept in departments:
                        if dept['id'] == item.get('owner_department_id'):
                            current_owner_dept = dept['name']
                            break
                owner_dept_index = owner_dept_names.index(current_owner_dept) if current_owner_dept in owner_dept_names else 0
                owner_department = st.selectbox("発注・棚卸の担当部署", options=owner_dept_names, index=owner_dept_index)
                owner_department_id = None
                if owner_department != "未設定":
                    for dept in departments:
                        if dept['name'] == owner_department:
                            owner_department_id = dept['id']
                            break
                
                # 利用部署タグ（複数選択）
                st.write("**利用部署タグ（複数選択可）**")
                is_common = st.checkbox("全社共通", value=bool(item.get('is_common')), key=f"is_common_edit_{item_id}")
                current_tags = item.get('department_tags', '').split(',') if item.get('department_tags') else []
                selected_depts = []
                if not is_common:
                    cols = st.columns(3)
                    for i, dept_name in enumerate(dept_names):
                        with cols[i % 3]:
                            if st.checkbox(dept_name, value=dept_name in current_tags, key=f"edit_dept_{item_id}_{dept_name}"):
                                selected_depts.append(dept_name)
                
                # 警告表示
                if not is_common and not selected_depts:
                    st.warning("⚠️ 利用部署タグが未設定です。「全社共通」または部署を選択してください。")
                
                st.caption("💡 単価が50,000円以上の場合、自動的に「資産」として登録されます")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    update_btn = st.form_submit_button("💾 更新", use_container_width=True, type="primary")
                with col_btn2:
                    cancel_btn = st.form_submit_button("❌ キャンセル", use_container_width=True)
                
                if update_btn:
                    # === バリデーション実行 ===
                    validation_errors = []
                    
                    # 品目名（必須）
                    ok_name, validated_name, error_msg_name = validate_required_text(item_name, "品目名", max_len=100)
                    if not ok_name:
                        validation_errors.append(error_msg_name)
                    
                    # カテゴリ（必須）
                    if not category:
                        validation_errors.append("カテゴリを選択してください")
                    
                    # 単価（必須・0以上）
                    ok_price, validated_price, error_msg_price = to_float_safe(unit_price, "単価", min_value=0.0, allow_zero=True)
                    if not ok_price:
                        validation_errors.append(error_msg_price)
                    else:
                        # 補正が行われた場合は警告表示
                        needs_warn, warn_msg = needs_correction_warning(unit_price, "currency")
                        if needs_warn:
                            st.warning(f"💡 単価: {warn_msg}")
                    
                    # 品目コードと業者情報のチェック
                    if not item_code and (not vendor_name or not vendor_item_code):
                        validation_errors.append("品目コードがない場合は、業者名と業者品番が必須です")
                    
                    # エラーがあれば表示して終了
                    if validation_errors:
                        for err in validation_errors:
                            st.error(err)
                    else:
                        # 部署タグをカンマ区切りに変換
                        department_tags = ",".join(selected_depts) if selected_depts else None
                        
                        # 期限をYYYY-MM形式に変換
                        expiry_date = None
                        if expiry_month != "なし":
                            month_num = int(expiry_month.replace("月", ""))
                            expiry_date = f"{expiry_year}-{month_num:02d}"
                        
                        # 資産区分を自動設定（50,000円以上なら資産）
                        is_asset = 1 if validated_price >= 50000 else 0
                        
                        result = update_item(
                            item_id=item_id,
                            item_name=validated_name,
                            category=category,
                            item_code=item_code if item_code else None,
                            vendor_name=vendor_name if vendor_name else None,
                            vendor_item_code=vendor_item_code if vendor_item_code else None,
                            department_tags=department_tags,
                            unit_price=validated_price,
                            is_asset=is_asset,
                            frequency_tag=frequency_tag if frequency_tag else None,
                            expiry_date=expiry_date,
                            owner_department_id=owner_department_id,
                            is_common=1 if is_common else 0
                        )
                        
                        if result['success']:
                            st.session_state.item_register_success = result['message']
                            del st.session_state.editing_item_id
                            st.rerun()
                        else:
                            st.error(result['message'])
                
                if cancel_btn:
                    del st.session_state.editing_item_id
                    st.rerun()
    
    with tab4:
        # === CSV取り込み ===
        show_csv_import_tab()


def show_csv_import_tab():
    """CSV取り込みタブの内容"""
    import pandas as pd
    import io
    from csv_import_helper import (
        generate_sample_csv, validate_csv_row, check_duplicate, prepare_import_data
    )
    
    st.subheader("📥 物品CSV一括取り込み")
    st.caption("大量の物品を一括登録できます。「できるだけ失敗させず、後から編集できる」設計です。")
    
    # 1️⃣ サンプルCSVダウンロード
    st.markdown("### 📄 ステップ1: サンプルCSVをダウンロード")
    sample_csv = generate_sample_csv()
    st.download_button(
        label="📥 サンプルCSVダウンロード",
        data=sample_csv.encode('utf-8-sig'),  # BOM付きUTF-8（Excelで文字化け防止）
        file_name="物品マスターサンプル.csv",
        mime="text/csv",
        help="このサンプルを編集して使用してください"
    )
    
    with st.expander("📋 CSVフォーマット詳細"):
        st.markdown("""
        #### 🔴 必須列
        - `item_name`: 物品名
        - `category_name`: カテゴリ名（存在しない場合は自動作成）
        - `vendor_name`: 業者名（存在しない場合は自動作成）
        - `unit_price`: 単価（数値）
        
        #### 🟡 任意列
        - `item_code`: 品目コード
        - `vendor_part_no`: 業者品番
        - `department_tags`: 部署タグ（カンマ区切り）
        - `reorder_point`: 発注点
        - `expiry_date`: 期限日（YYYY-MM-DD形式）
        - `is_active`: 有効フラグ（0 or 1、デフォルト: 1）
        - `notes`: 備考
        
        #### 📌 注意事項
        - **Excelで作成している場合は「CSV UTF-8（コンマ区切り）」で保存してください**
          - Excel: ファイル → 名前を付けて保存 → ファイルの種類で「CSV UTF-8（コンマ区切り）(*.csv)」を選択
          - テキストエディタの場合: UTF-8エンコードで保存
        - 日付形式: **YYYY-MM-DD**
        - 単価 >= 50,000円 の場合、自動的に「資産」扱いになります
        - 空のカテゴリ/業者は自動的に「未分類」「不明業者」として作成されます
        """)
    
    st.divider()
    
    # 2️⃣ CSVアップロード
    st.markdown("### 📤 ステップ2: CSVファイルをアップロード")
    uploaded_file = st.file_uploader(
        "CSVファイルを選択",
        type=['csv'],
        help="UTF-8エンコードのCSVファイルをアップロードしてください"
    )
    
    if not uploaded_file:
        st.info("💡 CSVファイルをアップロードしてください")
        return
    
    try:
        # CSVを読み込み（UTF-8 or UTF-8-BOM）
        csv_data = uploaded_file.read()
        try:
            # まずUTF-8-BOMで試す
            df = pd.read_csv(io.BytesIO(csv_data), encoding='utf-8-sig')
        except:
            # UTF-8で試す
            df = pd.read_csv(io.BytesIO(csv_data), encoding='utf-8')
        
        st.success(f"✅ CSVを読み込みました: {len(df)}行")
        
    except Exception as e:
        st.error(f"❌ CSVの読み込みに失敗しました: {str(e)}")
        st.info("💡 文字コードがUTF-8であることを確認してください")
        return
    
    # 3️⃣ プレビュー表示
    st.markdown("### 👀 ステップ3: データプレビュー")
    st.dataframe(df.head(10), use_container_width=True)
    if len(df) > 10:
        st.caption(f"（最初の10行のみ表示、全{len(df)}行）")
    
    st.divider()
    
    # 4️⃣ 取り込み設定
    st.markdown("### ⚙️ ステップ4: 取り込み設定")
    
    col1, col2 = st.columns(2)
    
    with col1:
        auto_create_masters = st.checkbox(
            "📝 カテゴリ・業者の自動作成",
            value=True,
            help="存在しないカテゴリや業者を自動的に作成します"
        )
    
    with col2:
        duplicate_action = st.radio(
            "🔄 重複時の動作",
            options=["スキップ", "更新"],
            index=0,
            horizontal=True,
            help="item_code または vendor_name+vendor_part_no が一致した場合の動作"
        )
    
    st.divider()
    
    # 5️⃣ バリデーション
    st.markdown("### ✅ ステップ5: データ検証")
    
    if st.button("🔍 検証実行", type="secondary"):
        # 既存データを取得
        existing_categories = set(get_category_names())
        existing_vendors = set(get_vendor_names())
        from db import list_items
        existing_items = list_items(include_inactive=True, limit=100000)  # 全件取得
        
        validation_results = []
        error_count = 0
        warning_count = 0
        ok_count = 0
        
        for idx, row in df.iterrows():
            row_number = idx + 2  # ヘッダー行があるので+2
            status, errors, warnings = validate_csv_row(
                row.to_dict(), row_number, existing_categories, existing_vendors
            )
            
            # 重複チェック
            is_duplicate, dup_item = check_duplicate(row.to_dict(), existing_items)
            
            validation_results.append({
                '行': row_number,
                'ステータス': status,
                '物品名': row.get('item_name', ''),
                '重複': '⚠️ 重複' if is_duplicate else '-',
                'エラー': '; '.join(errors) if errors else '-',
                '警告': '; '.join(warnings) if warnings else '-'
            })
            
            if status == 'error':
                error_count += 1
            elif status == 'warning':
                warning_count += 1
            else:
                ok_count += 1
        
        # 検証結果サマリー
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("✅ OK", f"{ok_count}行")
        with col2:
            st.metric("⚠️ 警告", f"{warning_count}行")
        with col3:
            st.metric("❌ エラー", f"{error_count}行")
        
        # 検証結果詳細
        result_df = pd.DataFrame(validation_results)
        st.dataframe(result_df, use_container_width=True, height=400)
        
        # セッションステートに保存
        st.session_state.csv_validation_done = True
        st.session_state.csv_validation_results = validation_results
        st.session_state.csv_data = df
        st.session_state.csv_error_count = error_count
    
    st.divider()
    
    # 6️⃣ 取り込み実行
    st.markdown("### 🚀 ステップ6: 取り込み実行")
    
    if not st.session_state.get('csv_validation_done', False):
        st.info("💡 まず「検証実行」ボタンをクリックしてデータを確認してください")
        return
    
    if st.session_state.get('csv_error_count', 0) > 0:
        st.warning(f"⚠️ {st.session_state.csv_error_count}行のエラーがあります。エラー行は取り込まれません。")
    
    if st.button("📥 取り込み実行", type="primary"):
        df = st.session_state.csv_data
        validation_results = st.session_state.csv_validation_results
        
        # 既存データを再取得
        existing_categories = set(get_category_names())
        existing_vendors = set(get_vendor_names())
        from db import list_items, insert_item, update_item, insert_category, insert_vendor
        existing_items = list_items(include_inactive=True, limit=100000)
        
        success_count = 0
        skip_count = 0
        update_count = 0
        error_count = 0
        results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, row in df.iterrows():
            progress = (idx + 1) / len(df)
            progress_bar.progress(progress)
            status_text.text(f"処理中... {idx + 1}/{len(df)}")
            
            # バリデーション結果を確認
            validation = validation_results[idx]
            if validation['ステータス'] == 'error':
                error_count += 1
                results.append({
                    '行': validation['行'],
                    '結果': '❌ エラー',
                    '物品名': row.get('item_name', ''),
                    '理由': validation['エラー']
                })
                continue
            
            # カテゴリ・業者の自動作成
            if auto_create_masters:
                category = str(row.get('category_name', '未分類')).strip() or '未分類'
                if category not in existing_categories:
                    insert_category(category)
                    existing_categories.add(category)
                
                vendor = str(row.get('vendor_name', '不明業者')).strip() or '不明業者'
                if vendor not in existing_vendors:
                    insert_vendor(vendor, vendor_code=None, notes=f"CSV取り込み時に自動作成")
                    existing_vendors.add(vendor)
            
            # 重複チェック
            is_duplicate, dup_item = check_duplicate(row.to_dict(), existing_items)
            
            if is_duplicate:
                if duplicate_action == "スキップ":
                    skip_count += 1
                    results.append({
                        '行': validation['行'],
                        '結果': '⏭️ スキップ',
                        '物品名': row.get('item_name', ''),
                        '理由': '重複のためスキップ'
                    })
                    continue
                else:  # 更新
                    import_data = prepare_import_data(row.to_dict())
                    result = update_item(
                        item_id=dup_item['id'],
                        **import_data
                    )
                    if result['success']:
                        update_count += 1
                        results.append({
                            '行': validation['行'],
                            '結果': '🔄 更新',
                            '物品名': row.get('item_name', ''),
                            '理由': '更新成功'
                        })
                    else:
                        error_count += 1
                        results.append({
                            '行': validation['行'],
                            '結果': '❌ エラー',
                            '物品名': row.get('item_name', ''),
                            '理由': result['message']
                        })
                    continue
            
            # 新規登録
            import_data = prepare_import_data(row.to_dict())
            result = insert_item(**import_data)
            
            if result['success']:
                success_count += 1
                results.append({
                    '行': validation['行'],
                    '結果': '✅ 成功',
                    '物品名': row.get('item_name', ''),
                    '理由': '新規登録成功'
                })
            else:
                error_count += 1
                results.append({
                    '行': validation['行'],
                    '結果': '❌ エラー',
                    '物品名': row.get('item_name', ''),
                    '理由': result['message']
                })
        
        progress_bar.progress(1.0)
        status_text.text("完了！")
        
        # 7️⃣ 実行結果表示
        st.markdown("### 📊 取り込み結果")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("✅ 新規登録", f"{success_count}件")
        with col2:
            st.metric("🔄 更新", f"{update_count}件")
        with col3:
            st.metric("⏭️ スキップ", f"{skip_count}件")
        with col4:
            st.metric("❌ エラー", f"{error_count}件")
        
        # 詳細結果
        result_df = pd.DataFrame(results)
        st.dataframe(result_df, use_container_width=True, height=400)
        
        # セッションステートをクリア
        if 'csv_validation_done' in st.session_state:
            del st.session_state.csv_validation_done
        if 'csv_validation_results' in st.session_state:
            del st.session_state.csv_validation_results
        if 'csv_data' in st.session_state:
            del st.session_state.csv_data
        if 'csv_error_count' in st.session_state:
            del st.session_state.csv_error_count
        
        st.success("🎉 CSV取り込みが完了しました！")
        st.info("💡 「物品一覧」タブで登録内容を確認してください")


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


def show_department_management_page():
    """部署マスタ管理ページ（管理者専用）- テーブル形式 + 検索 + ページング"""
    st.header("🏢 部署管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "部署管理は管理者のみ使用できます"):
        return
    
    # タブで機能を分割
    tab1, tab2 = st.tabs(["📋 部署一覧", "➕ 新規追加"])
    
    # ========== タブ1: 部署一覧・編集 ==========
    with tab1:
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
    with tab2:
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


def show_alert_page():
    """アラート画面（在庫不足・期限切れ/間近）"""
    from db import get_stock_alerts, get_expiry_alerts
    from datetime import datetime
    
    st.header("🚨 アラート")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック
    if not is_logged_in():
        st.warning("⚠️ アラートを確認するにはログインが必要です")
        return
    
    # 部署フィルタリング（ADMINは全体、USER/GUESTは自部署のみ）
    current_user = get_current_user()
    user_dept = current_user.get("department") if current_user else None
    
    if is_admin():
        department_filter = None  # ADMINは全部署+全社共通
    else:
        department_filter = user_dept  # USER/GUESTは自部署のみ
        if user_dept:
            st.info(f"📍 表示範囲: **{user_dept}** の物品のみ")
    
    # タブで在庫アラートと期限アラートを分ける
    tab1, tab2 = st.tabs(["📦 在庫不足", "⏰ 期限"])
    
    with tab1:
        st.subheader("📦 在庫不足アラート")
        st.caption("在庫数が発注点以下の物品を表示します")
        
        stock_alerts = get_stock_alerts(department_name=department_filter)
        
        # 申請済み状態を取得
        if stock_alerts:
            from db import check_items_ordered_status
            item_ids = [item['id'] for item in stock_alerts]
            order_status_map = check_items_ordered_status(item_ids)
        else:
            order_status_map = {}
        
        if not stock_alerts:
            st.success("✅ 在庫不足の物品はありません")
        else:
            st.warning(f"⚠️ 在庫不足の物品が **{len(stock_alerts)}件** あります")
            
            # 発注申請ボタンの表示（USER/ADMINのみ）
            show_purchase_button = not is_guest()
            
            # 列ヘッダー
            if show_purchase_button:
                header_cols = st.columns([3, 1, 1, 1, 1, 1, 1, 1.5])
            else:
                header_cols = st.columns([3, 1, 1, 1, 1, 1, 1])
            
            with header_cols[0]:
                st.markdown("**物品名**")
            with header_cols[1]:
                st.markdown("**品目コード**")
            with header_cols[2]:
                st.markdown("**カテゴリ**")
            with header_cols[3]:
                st.markdown("**在庫数**")
            with header_cols[4]:
                st.markdown("**発注点**")
            with header_cols[5]:
                st.markdown("**保管場所**")
            with header_cols[6]:
                st.markdown("**業者名**")
            if show_purchase_button:
                with header_cols[7]:
                    st.markdown("**操作**")
            
            # 在庫数が少ない順にソート
            stock_alerts_sorted = sorted(stock_alerts, key=lambda x: x['quantity'])
            
            # 各行に発注申請ボタンを追加
            for idx, item in enumerate(stock_alerts_sorted):
                with st.container():
                    if show_purchase_button:
                        cols = st.columns([3, 1, 1, 1, 1, 1, 1, 1.5])
                    else:
                        cols = st.columns([3, 1, 1, 1, 1, 1, 1])
                    
                    # 申請済み状態を確認
                    item_info = order_status_map.get(item['id'])
                    status_badge = ""
                    if item_info:
                        status = item_info.get('status')
                        qty = item_info.get('qty', 0)
                        # 入庫完了は表示しない（まだ不足しているなら追加申請が必要）
                        if status == 'ordered':
                            status_badge = f"✅ 発注済（{qty}個）"
                        elif status == 'pending':
                            status_badge = f"📝 申請済（{qty}個）"
                    
                    with cols[0]:
                        if status_badge:
                            st.write(f"**{item['item_name']}** {status_badge}")
                        else:
                            st.write(f"**{item['item_name']}**")
                    with cols[1]:
                        st.write(item['item_code'])
                    with cols[2]:
                        st.write(item['category'])
                    with cols[3]:
                        st.write(f"{item['quantity']}")
                    with cols[4]:
                        st.write(f"{item['reorder_point']}")
                    with cols[5]:
                        st.write(item['location'])
                    with cols[6]:
                        st.write(item.get('vendor_name', ''))
                    if show_purchase_button:
                        with cols[7]:
                            if st.button("📝 発注申請", key=f"purchase_stock_{idx}_{item['id']}"):
                                # セッションステートに選択した物品情報を保存
                                st.session_state.prefill_purchase_item_id = item['id']
                                st.session_state.prefill_purchase_quantity = max(item['reorder_point'] - item['quantity'], 1)
                                st.session_state.prefill_purchase_reason = "在庫不足アラート"
                                set_menu("purchase_request")
            
            st.info("💡 発注点を見直す場合は「物品マスター管理」から編集してください")
    
    with tab2:
        st.subheader("⏰ 期限アラート")
        st.caption("期限切れまたは期限間近（30日以内）の物品を表示します")
        
        # GUESTは廃棄申請権限がないため、期限アラートを表示しない
        if is_guest():
            st.info("📍 ゲストユーザーは期限アラートを表示できません。廃棄申請権限はUSER/ADMINのみです。")
            return
        
        # 部署フィルタリングを適用（ADMINは全体、USERは自部署のみ）
        expiry_alerts = get_expiry_alerts(department_name=department_filter)
        expired = expiry_alerts.get("expired", [])
        expiring_soon = expiry_alerts.get("expiring_soon", [])
        
        total_count = len(expired) + len(expiring_soon)
        
        if total_count == 0:
            st.success("✅ 期限アラートはありません")
        else:
            # サマリー表示
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("合計", f"{total_count}件")
            with col2:
                st.metric("期限切れ", f"{len(expired)}件", delta=None, delta_color="off")
            with col3:
                st.metric("期限間近", f"{len(expiring_soon)}件", delta=None, delta_color="off")
            
            st.divider()
            
            # 期限切れ
            if expired:
                st.error(f"🔴 **期限切れ: {len(expired)}件**")
                
                import pandas as pd
                df_expired = pd.DataFrame(expired)
                
                # 廃棄申請ボタンの追加（USER/ADMINのみ）
                show_disposal_button = not is_guest()
                
                # 列ヘッダー
                header_cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                with header_cols[0]:
                    st.markdown("**物品名**")
                with header_cols[1]:
                    st.markdown("**品目コード**")
                with header_cols[2]:
                    st.markdown("**カテゴリ**")
                with header_cols[3]:
                    st.markdown("**使用期限**")
                with header_cols[4]:
                    st.markdown("**在庫数**")
                with header_cols[5]:
                    st.markdown("**保管場所**")
                with header_cols[6]:
                    st.markdown("**操作**")
                
                # 各行に廃棄申請ボタンを追加
                for idx, item in enumerate(expired):
                    with st.container():
                        cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                        
                        with cols[0]:
                            st.write(f"**{item['item_name']}**")
                        with cols[1]:
                            st.write(item['item_code'])
                        with cols[2]:
                            st.write(item['category'])
                        with cols[3]:
                            st.write(item['expiry_date'])
                        with cols[4]:
                            st.write(f"{item['quantity']}")
                        with cols[5]:
                            st.write(item['location'])
                        with cols[6]:
                            if show_disposal_button:
                                if st.button("🗑️ 廃棄申請する", key=f"disposal_expired_{idx}_{item['id']}"):
                                    # セッションステートに選択した物品情報を保存
                                    st.session_state.prefill_disposal_item_id = item['id']
                                    st.session_state.prefill_disposal_quantity = 1
                                    st.session_state.prefill_disposal_reason = "期限アラート"
                                    set_menu("disposal_request")
                
                st.divider()
            
            # 期限間近
            if expiring_soon:
                st.warning(f"⚠️ **期限間近（30日以内）: {len(expiring_soon)}件**")
                
                import pandas as pd
                df_expiring = pd.DataFrame(expiring_soon)
                
                # 廃棄申請ボタンの追加（USER/ADMINのみ）
                show_disposal_button = not is_guest()
                
                # 列ヘッダー
                header_cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                with header_cols[0]:
                    st.markdown("**物品名**")
                with header_cols[1]:
                    st.markdown("**品目コード**")
                with header_cols[2]:
                    st.markdown("**カテゴリ**")
                with header_cols[3]:
                    st.markdown("**使用期限**")
                with header_cols[4]:
                    st.markdown("**在庫数**")
                with header_cols[5]:
                    st.markdown("**保管場所**")
                with header_cols[6]:
                    st.markdown("**操作**")
                
                # 各行に廃棄申請ボタンを追加
                for idx, item in enumerate(expiring_soon):
                    with st.container():
                        cols = st.columns([4, 1, 1, 1, 1, 1, 1.5])
                        
                        with cols[0]:
                            st.write(f"**{item['item_name']}**")
                        with cols[1]:
                            st.write(item['item_code'])
                        with cols[2]:
                            st.write(item['category'])
                        with cols[3]:
                            st.write(item['expiry_date'])
                        with cols[4]:
                            st.write(f"{item['quantity']}")
                        with cols[5]:
                            st.write(item['location'])
                        with cols[6]:
                            if show_disposal_button:
                                if st.button("🗑️ 廃棄申請する", key=f"disposal_expiring_{idx}_{item['id']}"):
                                    # セッションステートに選択した物品情報を保存
                                    st.session_state.prefill_disposal_item_id = item['id']
                                    st.session_state.prefill_disposal_quantity = 1
                                    st.session_state.prefill_disposal_reason = "期限アラート"
                                    set_menu("disposal_request")
                
                st.divider()
            
            st.info("💡 期限切れ物品は廃棄処理を検討してください")


def show_disposal_request_page():
    """廃棄申請画面（USER/ADMIN）"""
    from db import create_disposal_request, get_disposal_requests
    
    st.header("🗑️ 廃棄申請")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（GUESTはアクセス不可）
    if not is_logged_in():
        st.warning("⚠️ 廃棄申請にはログインが必要です")
        return
    
    if is_guest():
        st.warning("⚠️ ゲストユーザーは廃棄申請を行うことができません。")
        st.info("📍 ゲストユーザーは出庫申請のみ可能です。廃棄申請がUSERまたはADMINに依頼してください。")
        return
    
    current_user = get_current_user()
    user_id = current_user.get("id")
    
    # タブ: 新規申請 / 申請履歴
    tab1, tab2 = st.tabs(["📝 新規申請", "📋 申請履歴"])
    
    with tab1:
        st.subheader("📝 新規廃棄申請")
        st.caption("期限切れや破損した薬品・造影剤などを廃棄申請します")
        
        # 薬品カテゴリの物品を取得（部署フィルタリング適用）
        user_dept = current_user.get("department")
        
        from db import get_db_connection
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # ADMINは全物品、USER/GUESTは自部署のみ
                # カテゴリ条件を緩和：「薬品」「医薬品」「造影剤」を含むものを対象
                if is_admin():
                    cursor.execute("""
                        SELECT i.id, i.item_name, i.item_code, i.expiry_date, inv.quantity, i.department_tags, i.category
                        FROM items i
                        JOIN inventory inv ON i.id = inv.item_id
                        WHERE (i.category LIKE '%薬品%' OR i.category LIKE '%造影剤%')
                          AND i.is_active = 1
                          AND i.is_asset = 0
                          AND inv.quantity > 0
                        ORDER BY i.item_name
                    """)
                else:
                    cursor.execute("""
                        SELECT i.id, i.item_name, i.item_code, i.expiry_date, inv.quantity, i.department_tags, i.category
                        FROM items i
                        JOIN inventory inv ON i.id = inv.item_id
                        WHERE (i.category LIKE '%薬品%' OR i.category LIKE '%造影剤%')
                          AND i.is_active = 1
                          AND i.is_asset = 0
                          AND inv.quantity > 0
                          AND i.department_tags LIKE ?
                        ORDER BY i.item_name
                    """, (f'%{user_dept}%',))
                
                medicine_items = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            st.error(f"❌ 物品取得エラー: {e}")
            return
        
        if not is_admin() and user_dept:
            st.info(f"📍 表示対象: {user_dept} の薬品・造影剤のみ")
        
        st.caption(f"🔍 検索結果: {len(medicine_items)}件の物品が見つかりました")
        
        if not medicine_items:
            st.warning("⚠️ 廃棄可能な物品がありません")
            st.info("💡 以下を確認してください：")
            st.markdown("""
            - カテゴリが「薬品」「医薬品」「造影剤」のいずれかの物品が登録されているか
            - 在庫数が0より大きいか
            - 物品が有効化されているか
            - 自部署タグが設定されているか（USER権限の場合）
            """)
            
            # デモデータの再投入を提案
            with st.expander("🔧 デモデータを再投入する", expanded=False):
                st.caption("デモデータを再投入すると、薬品・造影剤のサンプルデータが登録されます")
                if st.button("📥 デモデータ再投入", key="reload_demo"):
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["python", "init_production_demo.py"],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if result.returncode == 0:
                            st.success("✅ デモデータの投入が完了しました")
                            st.rerun()
                        else:
                            st.error(f"❌ エラー: {result.stderr}")
                    except Exception as e:
                        st.error(f"❌ エラー: {e}")
            return
        
        # アラート画面から事前選択された物品情報を取得
        preselect_item_id = st.session_state.get("prefill_disposal_item_id")
        preselect_quantity = st.session_state.get("prefill_disposal_quantity", 1)
        preselect_reason = st.session_state.get("prefill_disposal_reason", "")
        
        # デバッグ情報を表示
        with st.expander("🔧 デバッグ情報", expanded=False):
            st.write(f"- 事前選択ID: {preselect_item_id}")
            st.write(f"- ユーザー部署: {user_dept}")
            st.write(f"- 権限: {'ADMIN' if is_admin() else 'USER'}")
            st.write(f"- 物品件数: {len(medicine_items)}")
            if medicine_items:
                st.write(f"- 物品例: {medicine_items[0]['item_name']} (ID: {medicine_items[0]['id']})")
        
        # アラートから来た場合は目立つ通知を表示
        if preselect_item_id:
            # 物品名を取得
            preselect_item = next((item for item in medicine_items if item['id'] == preselect_item_id), None)
            if preselect_item:
                st.info(f"📌 **アラートから選択:** {preselect_item['item_name']} （{preselect_item['item_code']}）")
            else:
                st.warning(f"⚠️ 選択された物品が見つかりません。在庫がない、または無効化されている可能性があります。")
                # 事前選択情報をクリア
                if "prefill_disposal_item_id" in st.session_state:
                    del st.session_state.prefill_disposal_item_id
                if "prefill_disposal_quantity" in st.session_state:
                    del st.session_state.prefill_disposal_quantity
                if "prefill_disposal_reason" in st.session_state:
                    del st.session_state.prefill_disposal_reason
                preselect_item_id = None
        
        default_index = 0
        if preselect_item_id:
            for i, item in enumerate(medicine_items):
                if item['id'] == preselect_item_id:
                    default_index = i
                    break
        
        # 申請成功メッセージの表示
        if "last_disposal_success" in st.session_state:
            st.success("✅ 申請しました！管理者の承認をお待ちください")
            st.info("💡 別の物品を申請する場合は、下記のフォームから選択してください")
            # 一度表示したらクリア
            del st.session_state.last_disposal_success
            # 事前選択情報もクリア（二重申請防止）
            if "prefill_disposal_item_id" in st.session_state:
                del st.session_state.prefill_disposal_item_id
            if "prefill_disposal_quantity" in st.session_state:
                del st.session_state.prefill_disposal_quantity
            if "prefill_disposal_reason" in st.session_state:
                del st.session_state.prefill_disposal_reason
        
        # フォームで入力を包む
        with st.form(key="disposal_request_form", clear_on_submit=False):
            # 物品選択
            item_options = [
                f"{item['item_name']} ({item['item_code']}) - 在庫: {item['quantity']} - 期限: {item.get('expiry_date') or 'なし'}"
                for item in medicine_items
            ]
            
            selected_idx = st.selectbox(
                "廃棄する薬品を選択",
                range(len(item_options)),
                format_func=lambda i: item_options[i],
                index=default_index
            )
            
            selected_item = medicine_items[selected_idx]
            
            # 事前選択された数量を初期値として使用（最大在庫数を超えないように）
            initial_quantity = min(preselect_quantity, selected_item['quantity']) if preselect_quantity else 1
            
            col1, col2 = st.columns(2)
            with col1:
                quantity = st.number_input(
                    "廃棄数量",
                    min_value=1,
                    max_value=selected_item['quantity'],
                    value=initial_quantity
                )
            
            with col2:
                st.metric("現在庫", selected_item['quantity'])
            
            # 廃棄理由（事前選択されている場合は初期値を設定）
            reason_default = preselect_reason if preselect_reason else ""
            reason = st.text_area(
                "廃棄理由",
                value=reason_default,
                placeholder="例: 期限切れのため、破損のため、汚染のため"
            )
            
            submitted = st.form_submit_button("📤 廃棄申請を提出", type="primary")
        
        # フォーム外で処理（エラーメッセージが表示されるように）
        if submitted:
            # === バリデーション実行 ===
            if len(reason.strip()) < 5:
                st.error("❌ 廃棄理由を5文字以上で入力してください")
            else:
                # 重複申請チェック
                import hashlib
                request_hash = hashlib.md5(
                    f"{selected_item['id']}_{quantity}_{reason.strip()}".encode()
                ).hexdigest()
                
                last_request_hash = st.session_state.get("last_disposal_request_hash")
                
                if last_request_hash == request_hash:
                    st.warning("⚠️ 同じ内容の申請が既に提出されています。内容を変更してください。")
                else:
                    try:
                        result = create_disposal_request(
                            item_id=selected_item['id'],
                            quantity=int(quantity),
                            reason=reason.strip(),
                            requester_id=user_id
                        )
                        
                        if result['success']:
                            # 申請成功を記録
                            st.session_state.last_disposal_request_hash = request_hash
                            st.session_state.last_disposal_success = True
                            st.rerun()
                        else:
                            st.error(f"❌ 申請失敗: {result['message']}")
                    except Exception as e:
                        st.error(f"❌ エラーが発生しました: {e}")
    
    with tab2:
        st.subheader("📋 申請履歴")
        
        # 自分の申請を取得
        requests = get_disposal_requests(requester_id=user_id)
        
        if not requests:
            st.info("申請履歴がありません")
        else:
            import pandas as pd
            df = pd.DataFrame(requests)
            
            # ステータス表示を整形
            status_map = {
                'PENDING': '⏳ 承認待ち',
                'APPROVED': '✅ 承認済み',
                'REJECTED': '❌ 却下'
            }
            df['status_display'] = df['status'].map(status_map)
            
            display_df = df[[
                'item_name', 'quantity', 'reason', 'status_display', 
                'created_at', 'approver_name', 'reject_reason'
            ]].copy()
            
            display_df.columns = [
                '物品名', '数量', '廃棄理由', 'ステータス',
                '申請日時', '承認者', '却下理由'
            ]
            
            st.dataframe(
                display_df,
                use_container_width=True,
                height=400
            )


def show_disposal_approval_page():
    """廃棄承認画面（ADMIN専用）"""
    from db import get_disposal_requests, approve_disposal_request, reject_disposal_request
    
    st.header("✅ 廃棄承認管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "廃棄承認は管理者のみ使用できます"):
        return
    
    current_user = get_current_user()
    approver_id = current_user.get("id")
    
    # タブ: 承認待ち / 処理済み
    tab1, tab2 = st.tabs(["⏳ 承認待ち", "📋 処理済み"])
    
    with tab1:
        st.subheader("⏳ 承認待ち廃棄申請")
        
        pending_requests = get_disposal_requests(status='PENDING')
        
        if not pending_requests:
            st.success("✅ 承認待ちの廃棄申請はありません")
        else:
            st.warning(f"⚠️ {len(pending_requests)}件の廃棄申請が承認待ちです")
            
            for req in pending_requests:
                with st.expander(
                    f"【{req['item_name']}】 {req['quantity']}個 - 申請者: {req['requester_name']} ({req['created_at']})",
                    expanded=True
                ):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**物品コード:** {req['item_code']}")
                        st.write(f"**カテゴリ:** {req['category']}")
                        st.write(f"**廃棄数量:** {req['quantity']}個")
                        st.write(f"**廃棄理由:**")
                        st.info(req['reason'])
                        st.write(f"**申請者:** {req['requester_name']}")
                        st.write(f"**申請日時:** {req['created_at']}")
                    
                    with col2:
                        st.write("### 承認/却下")
                        
                        # 処理中フラグで二重送信防止
                        processing_key = f"processing_{req['id']}"
                        is_processing = st.session_state.get(processing_key, False)
                        
                        if st.button(
                            "✅ 承認", 
                            key=f"approve_{req['id']}", 
                            type="primary",
                            disabled=is_processing
                        ):
                            st.session_state[processing_key] = True
                            result = approve_disposal_request(req['id'], approver_id)
                            if result['success']:
                                st.success(result['message'])
                                if processing_key in st.session_state:
                                    del st.session_state[processing_key]
                                st.rerun()
                            else:
                                st.error(result['message'])
                                if processing_key in st.session_state:
                                    del st.session_state[processing_key]
                        
                        if st.button(
                            "❌ 却下", 
                            key=f"reject_btn_{req['id']}",
                            disabled=is_processing
                        ):
                            st.session_state[f"show_reject_{req['id']}"] = True
                            st.rerun()
                        
                        # 却下理由入力フォーム
                        if st.session_state.get(f"show_reject_{req['id']}", False):
                            reject_reason = st.text_area(
                                "却下理由",
                                placeholder="却下する理由を入力してください",
                                key=f"reject_reason_{req['id']}"
                            )
                            
                            col_a, col_b = st.columns(2)
                            with col_a:
                                # 処理中フラグで二重送信防止
                                reject_processing_key = f"reject_processing_{req['id']}"
                                is_reject_processing = st.session_state.get(reject_processing_key, False)
                                
                                if st.button(
                                    "確定", 
                                    key=f"reject_confirm_{req['id']}",
                                    disabled=is_reject_processing
                                ):
                                    if not reject_reason or len(reject_reason.strip()) < 5:
                                        st.error("却下理由を5文字以上で入力してください")
                                    else:
                                        st.session_state[reject_processing_key] = True
                                        result = reject_disposal_request(
                                            req['id'], 
                                            approver_id, 
                                            reject_reason.strip()
                                        )
                                        if result['success']:
                                            st.success(result['message'])
                                            if f"show_reject_{req['id']}" in st.session_state:
                                                del st.session_state[f"show_reject_{req['id']}"]
                                            if reject_processing_key in st.session_state:
                                                del st.session_state[reject_processing_key]
                                            st.rerun()
                                        else:
                                            st.error(result['message'])
                                            if reject_processing_key in st.session_state:
                                                del st.session_state[reject_processing_key]
                            
                            with col_b:
                                if st.button("キャンセル", key=f"reject_cancel_{req['id']}"):
                                    del st.session_state[f"show_reject_{req['id']}"]
                                    st.rerun()
    
    with tab2:
        st.subheader("📋 処理済み廃棄申請")
        
        # 承認済みと却下済みを取得
        approved_requests = get_disposal_requests(status='APPROVED')
        rejected_requests = get_disposal_requests(status='REJECTED')
        
        all_processed = approved_requests + rejected_requests
        
        if not all_processed:
            st.info("処理済みの廃棄申請はありません")
        else:
            import pandas as pd
            df = pd.DataFrame(all_processed)
            
            # ステータス表示を整形
            status_map = {
                'APPROVED': '✅ 承認済み',
                'REJECTED': '❌ 却下'
            }
            df['status_display'] = df['status'].map(status_map)
            
            # 廃棄金額を計算
            df['disposal_amount'] = df['quantity'] * df['unit_price'].fillna(0)
            
            display_df = df[[
                'item_name', 'category', 'quantity', 'unit_price', 'disposal_amount',
                'reason', 'requester_name', 'status_display', 'approved_at', 'approver_name', 'reject_reason'
            ]].copy()
            
            display_df.columns = [
                '物品名', 'カテゴリ', '数量', '単価', '廃棄金額',
                '廃棄理由', '申請者', 'ステータス', '処理日時', '承認者', '却下理由'
            ]
            
            st.dataframe(
                display_df,
                use_container_width=True,
                height=400
            )
            
            # CSV出力ボタン
            # 廃棄金額を計算（単価 × 数量）
            df['disposal_amount'] = df['quantity'] * df['unit_price'].fillna(0)
            
            csv_df = pd.DataFrame({
                "物品名": df['item_name'],
                "カテゴリ": df['category'],
                "数量": df['quantity'],
                "単価": df['unit_price'].fillna(0),
                "廃棄金額": df['disposal_amount'],
                "廃棄理由": df['reason'],
                "申請者": df['requester_name'],
                "ステータス": df['status_display'],
                "処理日時": df['approved_at'],
                "承認者": df['approver_name'].fillna(""),
                "却下理由": df['reject_reason'].fillna("")
            })
            
            csv_data = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            
            filename = f"disposal_processed_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 CSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                use_container_width=False,
                help="処理済み廃棄申請をCSV出力します"
            )


def show_statistics_page():
    """集計ページ（USER/ADMIN専用）"""
    st.header("📊 集計")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック：USER/ADMINのみ
    if not is_logged_in():
        st.warning("⚠️ 集計を表示するにはログインが必要です")
        return
    
    if is_guest():
        st.error("🚫 この機能はゲストユーザーは使用できません")
        return
    
    st.info("💡 部署別・月別の出庫（消費）状況を確認できます")
    
    # フィルタ設定
    st.subheader("🔍 集計条件")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # 開始月
        current_date = datetime.now(ZoneInfo('Asia/Tokyo')).date()
        default_start = current_date.replace(month=1, day=1)  # 今年の1月
        
        start_date = st.date_input(
            "開始月",
            value=default_start,
            key="stats_start_date"
        )
        start_month = start_date.strftime('%Y-%m')
    
    with col2:
        # 終了月
        end_date = st.date_input(
            "終了月",
            value=current_date,
            key="stats_end_date"
        )
        end_month = end_date.strftime('%Y-%m')
    
    with col3:
        # 部署フィルタ
        departments = get_all_departments(active_only=True)
        dept_options = ["すべて"] + [dept['name'] for dept in departments]
        selected_dept = st.selectbox(
            "部署",
            options=dept_options,
            key="stats_dept"
        )
    
    with col4:
        # カテゴリフィルタ
        category_names = get_category_names()
        category_options = ["すべて"] + category_names
        selected_category = st.selectbox(
            "カテゴリ",
            options=category_options,
            key="stats_category"
        )
    
    # アクション種別
    action_types = st.multiselect(
        "集計対象",
        options=["OUT", "DISPOSE"],
        default=["OUT"],
        help="OUT: 出庫、DISPOSE: 廃棄",
        key="stats_action_types"
    )
    
    if not action_types:
        st.warning("⚠️ 集計対象を選択してください")
        return
    
    st.divider()
    
    # データ取得
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # SQLクエリ構築
        action_filter = "', '".join(action_types)
        
        # 月別サマリ（全体）
        st.subheader("📅 月別サマリ（全体）")
        
        sql_monthly = f"""
            SELECT 
                strftime('%Y-%m', ih.created_at) as month,
                ih.change_type as action,
                SUM(ABS(ih.quantity)) as total_quantity,
                SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
            FROM inventory_history ih
            LEFT JOIN items i ON ih.item_id = i.id
            WHERE ih.change_type IN ('{action_filter}')
              AND strftime('%Y-%m', ih.created_at) >= ?
              AND strftime('%Y-%m', ih.created_at) <= ?
        """
        
        params = [start_month, end_month]
        
        if selected_dept != "すべて":
            sql_monthly += " AND ih.department = ?"
            params.append(selected_dept)
        
        if selected_category != "すべて":
            sql_monthly += " AND i.category = ?"
            params.append(selected_category)
        
        sql_monthly += """
            GROUP BY month, ih.change_type
            ORDER BY month, ih.change_type
        """
        
        cursor.execute(sql_monthly, params)
        monthly_data = [dict(row) for row in cursor.fetchall()]
        
        if monthly_data:
            import pandas as pd
            df_monthly = pd.DataFrame(monthly_data)
            
            # ピボット形式に変換
            pivot_data = {}
            for month in df_monthly['month'].unique():
                month_data = df_monthly[df_monthly['month'] == month]
                pivot_data[month] = {
                    '月': month
                }
                for action in action_types:
                    action_data = month_data[month_data['action'] == action]
                    if not action_data.empty:
                        pivot_data[month][f'{action}_数量'] = int(action_data.iloc[0]['total_quantity'])
                        pivot_data[month][f'{action}_金額'] = int(action_data.iloc[0]['total_amount'])
                    else:
                        pivot_data[month][f'{action}_数量'] = 0
                        pivot_data[month][f'{action}_金額'] = 0
            
            df_display = pd.DataFrame(list(pivot_data.values()))
            
            # 列順を固定
            columns_order = ['月']
            for action in ['OUT', 'DISPOSE']:
                if action in action_types:
                    columns_order.extend([f'{action}_数量', f'{action}_金額'])
            df_display = df_display[columns_order]
            
            st.dataframe(df_display, use_container_width=True, height=300)
            
            # CSV出力
            csv_data = df_display.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            filename = f"monthly_summary_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 月別サマリCSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv"
            )
        else:
            st.info("該当するデータがありません")
        
        st.divider()
        
        # 部署別×月別集計
        st.subheader("🏢 部署別×月別集計")
        
        sql_dept_monthly = f"""
            SELECT 
                strftime('%Y-%m', ih.created_at) as month,
                ih.department,
                ih.change_type as action,
                SUM(ABS(ih.quantity)) as total_quantity,
                SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
            FROM inventory_history ih
            LEFT JOIN items i ON ih.item_id = i.id
            WHERE ih.change_type IN ('{action_filter}')
              AND strftime('%Y-%m', ih.created_at) >= ?
              AND strftime('%Y-%m', ih.created_at) <= ?
        """
        
        params = [start_month, end_month]
        
        if selected_dept != "すべて":
            sql_dept_monthly += " AND ih.department = ?"
            params.append(selected_dept)
        
        if selected_category != "すべて":
            sql_dept_monthly += " AND i.category = ?"
            params.append(selected_category)
        
        sql_dept_monthly += """
            GROUP BY month, ih.department, ih.change_type
            ORDER BY month, ih.department, ih.change_type
        """
        
        cursor.execute(sql_dept_monthly, params)
        dept_monthly_data = [dict(row) for row in cursor.fetchall()]
        
        if dept_monthly_data:
            import pandas as pd
            df_dept = pd.DataFrame(dept_monthly_data)
            
            # ピボット形式に変換
            pivot_data = {}
            for _, row in df_dept.iterrows():
                key = (row['month'], row['department'])
                if key not in pivot_data:
                    pivot_data[key] = {
                        '月': row['month'],
                        '部署': row['department'] or '未設定'
                    }
                    for action in action_types:
                        pivot_data[key][f'{action}_数量'] = 0
                        pivot_data[key][f'{action}_金額'] = 0
                
                action = row['action']
                pivot_data[key][f'{action}_数量'] = int(row['total_quantity'])
                pivot_data[key][f'{action}_金額'] = int(row['total_amount'])
            
            df_display_dept = pd.DataFrame(list(pivot_data.values()))
            
            # 列順を固定
            columns_order = ['月', '部署']
            for action in ['OUT', 'DISPOSE']:
                if action in action_types:
                    columns_order.extend([f'{action}_数量', f'{action}_金額'])
            df_display_dept = df_display_dept[columns_order]
            
            st.dataframe(df_display_dept, use_container_width=True, height=400)
            
            # 集計サマリ
            col1, col2, col3 = st.columns(3)
            with col1:
                total_qty = sum(df_display_dept[f'{action}_数量'].sum() for action in action_types)
                st.metric("合計数量", f"{int(total_qty):,}")
            with col2:
                total_amt = sum(df_display_dept[f'{action}_金額'].sum() for action in action_types)
                st.metric("合計金額", f"¥{int(total_amt):,}")
            with col3:
                dept_count = df_display_dept['部署'].nunique()
                st.metric("対象部署数", f"{dept_count}")
            
            # CSV出力
            csv_data = df_display_dept.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            filename = f"dept_monthly_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 部署別×月別CSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv"
            )
        else:
            st.info("該当するデータがありません")
        
        st.divider()
        
        # カテゴリ別廃棄集計（DISPOSE選択時のみ）
        if 'DISPOSE' in action_types:
            st.subheader("🗑️ カテゴリ別廃棄集計")
            
            sql_category = f"""
                SELECT 
                    i.category,
                    SUM(ABS(ih.quantity)) as total_quantity,
                    SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount,
                    COUNT(DISTINCT ih.id) as disposal_count
                FROM inventory_history ih
                LEFT JOIN items i ON ih.item_id = i.id
                WHERE ih.change_type = 'DISPOSE'
                  AND strftime('%Y-%m', ih.created_at) >= ?
                  AND strftime('%Y-%m', ih.created_at) <= ?
            """
            
            params = [start_month, end_month]
            
            if selected_dept != "すべて":
                sql_category += " AND ih.department = ?"
                params.append(selected_dept)
            
            if selected_category != "すべて":
                sql_category += " AND i.category = ?"
                params.append(selected_category)
            
            sql_category += """
                GROUP BY i.category
                ORDER BY total_amount DESC
            """
            
            cursor.execute(sql_category, params)
            category_data = [dict(row) for row in cursor.fetchall()]
            
            if category_data:
                import pandas as pd
                df_category = pd.DataFrame(category_data)
                
                df_category['category'] = df_category['category'].fillna('未分類')
                
                display_df = pd.DataFrame({
                    'カテゴリ': df_category['category'],
                    '廃棄数量': df_category['total_quantity'].astype(int),
                    '廃棄金額': df_category['total_amount'].astype(int),
                    '廃棄回数': df_category['disposal_count'].astype(int)
                })
                
                st.dataframe(display_df, use_container_width=True, height=300)
                
                # カテゴリ別サマリ
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("総廃棄数量", f"{int(df_category['total_quantity'].sum()):,}")
                with col2:
                    st.metric("総廃棄金額", f"¥{int(df_category['total_amount'].sum()):,}")
                with col3:
                    st.metric("カテゴリ数", f"{len(df_category)}")
                
                # CSV出力
                csv_data = display_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                filename = f"category_disposal_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
                
                st.download_button(
                    label="📥 カテゴリ別廃棄CSV出力",
                    data=csv_data,
                    file_name=filename,
                    mime="text/csv"
                )
            else:
                st.info("廃棄データがありません")


# =============================================================================
# AIアシスタント機能
# =============================================================================

def get_ai_context_data(max_items: int = 50) -> dict:
    """
    AIアシスタントに渡すコンテキストデータを取得
    
    Args:
        max_items: 在庫データの最大件数（トークン節約のため制限）
    
    Returns:
        dict: AIに渡すコンテキストデータ
    """
    from db import get_stock_alerts, get_expiry_alerts
    from datetime import datetime
    
    context = {
        "inventory": [],
        "stock_alerts": [],
        "expiry_alerts": {"expired": [], "expiring_soon": []},
        "monthly_summary": [],
        "department_summary": []
    }
    
    try:
        # 1. 在庫一覧（上位N件）
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    i.item_name,
                    i.item_code,
                    i.category,
                    i.vendor_name,
                    i.unit_price,
                    i.department_tags,
                    i.expiry_date,
                    i.reorder_point,
                    inv.quantity,
                    inv.location
                FROM items i
                LEFT JOIN inventory inv ON i.id = inv.item_id
                WHERE i.is_active = 1
                ORDER BY i.item_name
                LIMIT ?
            """, (max_items,))
            
            rows = cursor.fetchall()
            context["inventory"] = [dict(row) for row in rows]
            
            # 2. 月別集計（今年のデータ）
            current_year = datetime.now(ZoneInfo('Asia/Tokyo')).year
            cursor.execute("""
                SELECT 
                    strftime('%Y-%m', ih.created_at) as month,
                    ih.department,
                    ih.change_type as action,
                    SUM(ABS(ih.quantity)) as total_quantity,
                    SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
                FROM inventory_history ih
                LEFT JOIN items i ON ih.item_id = i.id
                WHERE strftime('%Y', ih.created_at) = ?
                  AND ih.change_type IN ('OUT', 'DISPOSE')
                GROUP BY month, ih.department, ih.change_type
                ORDER BY month DESC
                LIMIT 100
            """, (str(current_year),))
            
            rows = cursor.fetchall()
            context["monthly_summary"] = [dict(row) for row in rows]
            
            # 3. 部署別集計（今年）
            cursor.execute("""
                SELECT 
                    ih.department,
                    ih.change_type as action,
                    SUM(ABS(ih.quantity)) as total_quantity,
                    SUM(ABS(ih.quantity) * COALESCE(i.unit_price, 0)) as total_amount
                FROM inventory_history ih
                LEFT JOIN items i ON ih.item_id = i.id
                WHERE strftime('%Y', ih.created_at) = ?
                  AND ih.change_type IN ('OUT', 'DISPOSE')
                GROUP BY ih.department, ih.change_type
                ORDER BY total_amount DESC
            """, (str(current_year),))
            
            rows = cursor.fetchall()
            context["department_summary"] = [dict(row) for row in rows]
        
        # 4. 在庫アラート
        context["stock_alerts"] = get_stock_alerts()
        
        # 5. 期限アラート
        context["expiry_alerts"] = get_expiry_alerts()
        
    except Exception as e:
        print(f"❌ AIコンテキスト取得エラー: {e}")
    
    return context


def format_context_for_ai(context: dict) -> str:
    """
    AIに渡すコンテキストデータをテキスト形式にフォーマット
    """
    from datetime import datetime
    
    lines = []
    lines.append(f"=== 在庫管理システムデータ（{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y年%m月%d日 %H:%M')}時点）===\n")
    
    # 在庫一覧
    lines.append("【在庫一覧】")
    if context["inventory"]:
        for item in context["inventory"]:
            expiry_info = f", 期限:{item['expiry_date']}" if item.get('expiry_date') else ""
            reorder_info = f", 発注点:{item['reorder_point']}" if item.get('reorder_point') else ""
            lines.append(
                f"- {item['item_name']} | カテゴリ:{item['category']} | "
                f"在庫数:{item['quantity']} | 単価:{item['unit_price']}円 | "
                f"部署:{item.get('department_tags', '全社')}{reorder_info}{expiry_info}"
            )
    else:
        lines.append("- データなし")
    lines.append("")
    
    # 在庫アラート
    lines.append("【在庫不足アラート】")
    if context["stock_alerts"]:
        for alert in context["stock_alerts"]:
            lines.append(
                f"- ⚠️ {alert['item_name']} | 在庫数:{alert['quantity']} | "
                f"発注点:{alert['reorder_point']} | 業者:{alert.get('vendor_name', '不明')}"
            )
    else:
        lines.append("- 在庫不足なし")
    lines.append("")
    
    # 期限アラート
    lines.append("【期限アラート】")
    expired = context["expiry_alerts"].get("expired", [])
    expiring_soon = context["expiry_alerts"].get("expiring_soon", [])
    
    if expired:
        lines.append("期限切れ:")
        for item in expired:
            lines.append(f"  - 🔴 {item['item_name']} | 期限:{item['expiry_date']} | 在庫数:{item['quantity']}")
    
    if expiring_soon:
        lines.append("期限間近（30日以内）:")
        for item in expiring_soon:
            lines.append(f"  - ⚠️ {item['item_name']} | 期限:{item['expiry_date']} | 在庫数:{item['quantity']}")
    
    if not expired and not expiring_soon:
        lines.append("- 期限アラートなし")
    lines.append("")
    
    # 月別集計
    lines.append("【月別消費・廃棄サマリ（今年）】")
    if context["monthly_summary"]:
        for row in context["monthly_summary"][:20]:  # 上位20件
            lines.append(
                f"- {row['month']} | {row['department']} | {row['action']}: "
                f"{row['total_quantity']}個, {int(row['total_amount']):,}円"
            )
    else:
        lines.append("- データなし")
    lines.append("")
    
    # 部署別集計
    lines.append("【部署別消費・廃棄サマリ（今年）】")
    if context["department_summary"]:
        for row in context["department_summary"]:
            lines.append(
                f"- {row['department']} | {row['action']}: "
                f"{row['total_quantity']}個, {int(row['total_amount']):,}円"
            )
    else:
        lines.append("- データなし")
    
    return "\n".join(lines)


def check_safety_request(user_message: str) -> tuple:
    """
    ユーザーの入力が操作系（入庫・出庫・削除など）かチェック
    
    Returns:
        tuple: (is_safe: bool, warning_message: str)
    """
    # 操作系キーワード
    operation_keywords = [
        "入庫して", "入庫する", "入庫を", "入庫処理",
        "出庫して", "出庫する", "出庫を", "出庫処理",
        "削除して", "削除する", "削除を", "削除処理",
        "廃棄して", "廃棄する", "廃棄を", "廃棄処理",
        "追加して", "追加する", "追加を",
        "登録して", "登録する", "登録を",
        "更新して", "更新する", "更新を",
        "変更して", "変更する", "変更を",
        "編集して", "編集する", "編集を",
        "発注して", "発注する", "発注を確定",
        "承認して", "承認する",
        "取り消して", "キャンセルして",
        "処理して", "実行して",
    ]
    
    for keyword in operation_keywords:
        if keyword in user_message:
            return (False, "⚠️ 在庫の操作（入庫・出庫・削除など）はAIアシスタントからは行えません。\n通常の操作画面から行ってください。")
    
    return (True, "")


def call_openai_chat(messages: list, system_prompt: str) -> str:
    """
    OpenAI APIを呼び出してチャット応答を取得
    
    Args:
        messages: チャット履歴
        system_prompt: システムプロンプト
    
    Returns:
        str: AIの応答
    """
    import openai
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "❌ OpenAI APIキーが設定されていません。環境変数 `OPENAI_API_KEY` を設定してください。"
    
    try:
        client = openai.OpenAI(api_key=api_key)
        
        # メッセージ構築
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)
        
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=full_messages,
            max_tokens=2000,
            temperature=0.7
        )
        
        return response.choices[0].message.content
    
    except openai.AuthenticationError:
        return "❌ OpenAI APIキーが無効です。正しいAPIキーを設定してください。"
    except openai.RateLimitError:
        return "❌ OpenAI APIのレート制限に達しました。しばらく待ってから再試行してください。"
    except Exception as e:
        return f"❌ AI応答エラー: {str(e)}"


def show_ai_assistant_page():
    """AIアシスタントページ（閲覧専用・DB更新なし）"""
    st.header("🤖 AIアシスタント")
    
    # 権限チェック
    if not is_logged_in():
        st.warning("⚠️ AIアシスタントを利用するにはログインが必要です")
        return
    
    # AI機能が無効の場合
    if not AI_ENABLED:
        st.error("🚫 AI機能は無効になっています。管理者に連絡してください。")
        st.info("💡 AI機能を有効にするには、環境変数 `AI_ENABLED=true` を設定してください。")
        return
    
    # OpenAI APIキーチェック
    if not os.getenv("OPENAI_API_KEY"):
        st.error("🚫 OpenAI APIキーが設定されていません。")
        st.info("💡 環境変数 `OPENAI_API_KEY` を設定してください。")
        return
    
    # 説明文
    st.info("""
    💡 **在庫状況や発注候補について質問できます**
    
    このアシスタントは在庫データを参照して、検索・要約・提案を行います。
    ※ 在庫の操作（入庫・出庫・削除など）は行いません。
    """)
    
    # 質問例の表示
    with st.expander("📝 質問の例", expanded=False):
        st.markdown("""
        - 「在庫が少ない物品を教えて」
        - 「今月、どの部署が一番使ってる？」
        - 「発注した方がよい物品をリスト化して」
        - 「期限切れの物品は？」
        - 「廃棄が多いカテゴリは？」
        - 「発注書の文案を作って」
        - 「〇〇の在庫状況を教えて」
        """)
    
    st.divider()
    
    # チャット履歴の初期化
    if "ai_chat_history" not in st.session_state:
        st.session_state.ai_chat_history = []
    
    # チャット履歴の表示
    chat_container = st.container()
    with chat_container:
        if not st.session_state.ai_chat_history:
            st.caption("💬 質問を入力してください")
        else:
            for message in st.session_state.ai_chat_history:
                if message["role"] == "user":
                    st.chat_message("user").markdown(message["content"])
                else:
                    st.chat_message("assistant").markdown(message["content"])
    
    st.divider()
    
    # 入力フォーム
    col1, col2 = st.columns([5, 1])
    
    with col1:
        user_input = st.text_input(
            "質問を入力",
            placeholder="例: 在庫が少ない物品を教えて",
            key="ai_user_input",
            label_visibility="collapsed"
        )
    
    with col2:
        send_button = st.button("📤 送信", use_container_width=True, type="primary")
    
    # 履歴クリアボタン
    col_clear, col_space = st.columns([1, 5])
    with col_clear:
        if st.button("🗑️ 履歴クリア", use_container_width=True):
            st.session_state.ai_chat_history = []
            st.rerun()
    
    # 送信処理
    if send_button and user_input:
        # セーフティチェック
        is_safe, warning_msg = check_safety_request(user_input)
        
        if not is_safe:
            # 操作系リクエストは拒否
            st.session_state.ai_chat_history.append({"role": "user", "content": user_input})
            st.session_state.ai_chat_history.append({"role": "assistant", "content": warning_msg})
            st.rerun()
        else:
            # コンテキストデータを取得
            with st.spinner("📊 在庫データを取得中..."):
                context_data = get_ai_context_data(max_items=50)
                context_text = format_context_for_ai(context_data)
            
            # システムプロンプト構築
            system_prompt = f"""あなたは在庫管理システムのAIアシスタントです。

【役割】
- 在庫データの検索・要約・分析
- 発注候補の提案
- 発注書・廃棄書などの文案作成
- ユーザーの質問への回答

【重要なルール】
1. データベースを変更する操作は絶対に行いません（入庫・出庫・削除・更新など）
2. 数値は必ず渡されたデータから計算してください。推測しないでください。
3. 分からない場合は「分かりません」と正直に答えてください
4. 操作系の依頼（入庫して、削除してなど）には「通常の操作画面から行ってください」と案内してください
5. 回答はMarkdown形式で見やすく整形してください

【現在の在庫データ】
{context_text}
"""
            
            # ユーザーメッセージを追加
            st.session_state.ai_chat_history.append({"role": "user", "content": user_input})
            
            # AI応答を取得
            with st.spinner("🤖 回答を生成中..."):
                # OpenAI形式のメッセージ履歴を構築（最新5往復まで）
                messages_for_api = []
                recent_history = st.session_state.ai_chat_history[-10:]  # 最新10メッセージ
                for msg in recent_history:
                    messages_for_api.append({"role": msg["role"], "content": msg["content"]})
                
                ai_response = call_openai_chat(messages_for_api, system_prompt)
            
            # AI応答を追加
            st.session_state.ai_chat_history.append({"role": "assistant", "content": ai_response})
            
            st.rerun()


def show_maintenance_page():
    """🛠️ メンテナンスページ（ADMIN専用）"""
    st.header("🛠️ データメンテナンス")
    
    # 権限チェック：ADMINのみ
    if not is_logged_in():
        st.warning("⚠️ メンテナンス機能を利用するにはログインが必要です")
        return
    
    if not is_admin():
        st.error("🚫 この機能は管理者のみ使用できます")
        return
    
    st.info("💡 データベースの整合性チェックとクリーンアップを実行できます")
    
    # 入庫履歴のchange_type統一
    st.subheader("📦 入庫履歴のchange_type統一")
    st.markdown("""
    **目的**: inventory_historyテーブルのchange_typeを標準化します
    - **残すべき値**: `IN` (入庫), `OUT` (出庫), `DISPOSE` (廃棄), `UNDO` (取消)
    - **削除対象**: `ORDER` (発注記録), `INBOUND` (重複納品記録)
    - **変換**: `INBOUND` → `IN` に統一
    """)
    
    # 現在の状態を表示
    with st.expander("📊 現在のchange_type分布", expanded=True):
        try:
            type_counts = check_history_change_types()
            if type_counts:
                df_counts = pd.DataFrame([
                    {"change_type": k, "件数": v}
                    for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
                ])
                st.dataframe(df_counts, use_container_width=True)
                
                # 問題がある場合は警告
                problematic = {k: v for k, v in type_counts.items() 
                             if k not in ['IN', 'OUT', 'DISPOSE', 'UNDO']}
                if problematic:
                    st.warning(f"⚠️ 標準外のchange_type: {', '.join(problematic.keys())}")
                else:
                    st.success("✅ すべてのchange_typeが標準値です")
            else:
                st.info("履歴データがありません")
        except Exception as e:
            st.error(f"エラー: {e}")
    
    # バックアップ
    st.subheader("💾 バックアップ")
    if st.button("📥 履歴データをCSVにバックアップ"):
        try:
            csv_path = backup_inventory_history_to_csv()
            st.success(f"✅ バックアップ完了: {csv_path}")
        except Exception as e:
            st.error(f"❌ バックアップ失敗: {e}")
    
    # ドライラン
    st.subheader("🔍 クリーンアップ予行（変更なし）")
    if st.button("🧹 ドライラン実行"):
        try:
            with st.spinner("チェック中..."):
                result = cleanup_history_change_types(dry_run=True)
            
            st.info("**変更内容（実際には変更されていません）**")
            st.write(f"- INBOUND → IN 変換: {result['converted']}件")
            st.write(f"- ORDER 削除: {result['deleted']}件")
            st.write(f"- 合計処理: {result['total_affected']}件")
            
            if result['total_affected'] > 0:
                st.warning("⚠️ 上記の変更を実行するには、下の「実行」ボタンを押してください")
            else:
                st.success("✅ クリーンアップ不要です")
                
        except Exception as e:
            st.error(f"❌ ドライラン失敗: {e}")
    
    # 実行
    st.subheader("✅ クリーンアップ実行")
    st.warning("⚠️ この操作は **元に戻せません**。必ずバックアップを取ってから実行してください。")
    
    confirm_text = st.text_input("実行するには「実行する」と入力してください:")
    
    if st.button("🚨 クリーンアップ実行", type="primary", disabled=(confirm_text != "実行する")):
        if confirm_text == "実行する":
            try:
                with st.spinner("処理中..."):
                    result = cleanup_history_change_types(dry_run=False)
                
                st.success("✅ クリーンアップ完了")
                st.write(f"- INBOUND → IN 変換: {result['converted']}件")
                st.write(f"- ORDER 削除: {result['deleted']}件")
                st.write(f"- 合計処理: {result['total_affected']}件")
                
                # 実行後の状態確認
                with st.expander("📊 実行後のchange_type分布", expanded=True):
                    after_counts = check_history_change_types()
                    if after_counts:
                        df_after = pd.DataFrame([
                            {"change_type": k, "件数": v}
                            for k, v in sorted(after_counts.items(), key=lambda x: -x[1])
                        ])
                        st.dataframe(df_after, use_container_width=True)
                        
                        # ORDER/INBOUND が残っていないか確認
                        if 'ORDER' in after_counts or 'INBOUND' in after_counts:
                            st.error("⚠️ ORDER または INBOUND が残っています！")
                        else:
                            st.success("✅ ORDER と INBOUND は完全に削除されました")
                            st.info("履歴ページで「🔄 更新」ボタンを押すと最新データが表示されます")
                
                # 結果を再表示（2秒後）
                import time
                time.sleep(2)
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ クリーンアップ失敗: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.info("確認テキストを入力してください")


def show_demo_mode_page():
    """デモモード管理ページ（管理者専用）"""
    st.header("🎭 デモモード")
    
    # 権限チェック：ADMINのみ
    if not is_logged_in():
        st.warning("⚠️ デモモードを利用するにはログインが必要です")
        return
    
    if not is_admin():
        st.error("🚫 この機能は管理者のみ使用できます")
        return
    
    st.info("💡 テスト用のサンプルデータを一括投入・リセットできます")
    
    # 現在のデータ件数を表示
    st.subheader("📊 現在のデータ件数")
    
    counts = get_demo_data_counts()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("部署", counts.get("departments", 0))
        st.metric("ユーザー", counts.get("users", 0))
    with col2:
        st.metric("業者", counts.get("vendors", 0))
        st.metric("カテゴリ", counts.get("categories", 0))
    with col3:
        st.metric("物品", counts.get("items", 0))
        st.metric("在庫", counts.get("inventory", 0))
    with col4:
        st.metric("履歴", counts.get("inventory_history", 0))
        st.metric("承認待ち", counts.get("approval_queue", 0))
    
    st.divider()
    
    # タブで機能を分割
    tab1, tab2 = st.tabs(["➕ デモデータ投入", "🗑️ デモリセット"])
    
    # ========== タブ1: デモデータ投入 ==========
    with tab1:
        st.subheader("➕ デモデータ一括投入")
        
        st.markdown("""
        **投入されるデータ:**
        - 📂 部署: 5件（総務部、営業部、開発部、経理部、人事部）
        - 👥 ユーザー: 7名（管理者1、一般4、ゲスト2）
        - 🏢 業者: 5社（文具センター、電子部品商事、家具プロ等）
        - 🏷️ カテゴリ: 5種類（文房具、電子機器、家具、消耗品、工具）
        - 📦 物品: 20件（各カテゴリに4件ずつ）
        - 📊 在庫: 全物品に在庫設定
        - 📝 履歴: 10件の物品に入出庫履歴
        - ✋ 承認待ち: 3件の出庫申請
        """)
        
        st.warning("⚠️ 既存データと重複する場合はスキップされます")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ デモデータを投入", type="primary", use_container_width=True):
                with st.spinner("投入中..."):
                    result = insert_demo_data()
                    
                    if result["success"]:
                        st.success(result["message"])
                        
                        # 投入された件数を表示
                        inserted_counts = result.get("counts", {})
                        st.markdown("**投入された件数:**")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"- 部署: {inserted_counts.get('departments', 0)}件")
                            st.write(f"- ユーザー: {inserted_counts.get('users', 0)}件")
                            st.write(f"- 業者: {inserted_counts.get('vendors', 0)}件")
                            st.write(f"- カテゴリ: {inserted_counts.get('categories', 0)}件")
                        with col_b:
                            st.write(f"- 物品: {inserted_counts.get('items', 0)}件")
                            st.write(f"- 在庫: {inserted_counts.get('inventory', 0)}件")
                            st.write(f"- 履歴: {inserted_counts.get('history', 0)}件")
                            st.write(f"- 承認待ち: {inserted_counts.get('approvals', 0)}件")
                        
                        st.balloons()
                        
                        # 各ページへのリンク
                        st.info("💡 各管理画面で確認できます")
                        
                        # 自動リロード用のセッションステート
                        if st.button("🔄 データ件数を更新", use_container_width=True):
                            st.rerun()
                    else:
                        st.error(result["message"])
        
        with col2:
            # ページ遷移ボタン
            st.write("**確認ページへ移動:**")
            
            if st.button("📦 物品マスター", use_container_width=True):
                st.session_state.page = "item_master"
                st.rerun()
            
            if st.button("🏢 業者管理", use_container_width=True):
                st.session_state.page = "vendor"
                st.rerun()
            
            if st.button("👥 ユーザー管理", use_container_width=True):
                st.session_state.page = "user"
                st.rerun()
            
            if st.button("📊 在庫一覧", use_container_width=True):
                st.session_state.page = "inventory"
                st.rerun()
    
    # ========== タブ2: デモリセット ==========
    with tab2:
        st.subheader("🗑️ デモデータリセット")
        
        st.warning("⚠️ この操作は取り消せません。注意して実行してください。")
        
        # リセットオプション
        keep_users = st.checkbox(
            "ユーザーと部署は残す",
            value=True,
            help="チェックを入れると、在庫系・履歴系のみ削除します"
        )
        
        if keep_users:
            st.markdown("""
            **削除されるデータ:**
            - 📦 物品マスター
            - 🏢 業者
            - 🏷️ カテゴリ
            - 📊 在庫
            - 📝 在庫履歴
            - ✋ 承認待ち
            
            **保持されるデータ:**
            - 👥 ユーザー
            - 📂 部署
            """)
        else:
            st.markdown("""
            **削除されるデータ:**
            - 📦 物品マスター
            - 🏢 業者
            - 🏷️ カテゴリ
            - 📊 在庫
            - 📝 在庫履歴
            - ✋ 承認待ち
            - 👥 ユーザー
            - 📂 部署
            """)
        
        # 確認用のセッションステート
        if "demo_reset_confirm" not in st.session_state:
            st.session_state.demo_reset_confirm = False
        
        col1, col2 = st.columns(2)
        
        with col1:
            if not st.session_state.demo_reset_confirm:
                if st.button("🗑️ リセット実行", type="secondary", use_container_width=True):
                    st.session_state.demo_reset_confirm = True
                    st.rerun()
            else:
                st.error("⚠️ 本当にリセットしますか？")
                
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ はい", type="primary", use_container_width=True):
                        with st.spinner("リセット中..."):
                            result = reset_demo_data(keep_users_and_depts=keep_users)
                            
                            if result["success"]:
                                st.success(result["message"])
                                
                                # 削除された件数を表示
                                deleted_counts = result.get("counts", {})
                                st.markdown("**削除された件数:**")
                                
                                col_a, col_b = st.columns(2)
                                with col_a:
                                    if not keep_users:
                                        st.write(f"- 部署: {deleted_counts.get('departments', 0)}件")
                                        st.write(f"- ユーザー: {deleted_counts.get('users', 0)}件")
                                    st.write(f"- 業者: {deleted_counts.get('vendors', 0)}件")
                                    st.write(f"- カテゴリ: {deleted_counts.get('categories', 0)}件")
                                with col_b:
                                    st.write(f"- 物品: {deleted_counts.get('items', 0)}件")
                                    st.write(f"- 在庫: {deleted_counts.get('inventory', 0)}件")
                                    st.write(f"- 履歴: {deleted_counts.get('history', 0)}件")
                                    st.write(f"- 承認待ち: {deleted_counts.get('approvals', 0)}件")
                                
                                st.session_state.demo_reset_confirm = False
                                
                                # 自動リロード
                                if st.button("🔄 データ件数を更新", use_container_width=True):
                                    st.rerun()
                            else:
                                st.error(result["message"])
                                st.session_state.demo_reset_confirm = False
                
                with col_no:
                    if st.button("❌ いいえ", use_container_width=True):
                        st.session_state.demo_reset_confirm = False
                        st.rerun()
        
        with col2:
            if st.button("🔄 キャンセル", use_container_width=True):
                st.session_state.demo_reset_confirm = False
                st.rerun()


def main():
    """メイン処理"""
    init_app()
    
    # ログインチェック
    if not is_logged_in():
        # 未ログイン時はログイン画面を表示
        show_login_page()
        return
    
    # サイドバー
    with st.sidebar:
        st.title("🏢 在庫管理システム")
        st.divider()
        
        # ユーザー情報表示
        show_user_info_sidebar()
        st.divider()
        
        # 表示サイズ選択
        st.subheader("⚙️ 表示設定")
        size_options = ["小", "中", "大"]
        selected_size = st.selectbox(
            "表示サイズ",
            options=size_options,
            index=size_options.index(st.session_state.display_size),
            key="size_selector",
            help="小：縮小表示 / 中：標準 / 大：拡大表示"
        )
        
        # 表示サイズが変更されたら更新してrerun
        if selected_size != st.session_state.display_size:
            st.session_state.display_size = selected_size
            st.rerun()
        
        st.divider()
        
        # AI機能状態表示
        if AI_ENABLED:
            st.success("🤖 AI機能: 有効")
        else:
            st.info("🤖 AI機能: 無効")
        
        st.divider()
        
        # === 互換性維持ヘルパー: 古い日本語ラベルをIDに変換 ===
        def _migrate_legacy_menu_to_id():
            """古い日本語ラベルのmenuステートをIDベースに移行"""
            legacy_map = {
                "📦 在庫一覧": "inventory",
                "🚨 アラート": "alert",
                "📝 発注申請": "purchase_request",
                "🗑️ 廃棄申請": "disposal_request",
                "➕ 入庫": "inbound",
                "➖ 出庫": "outbound",
                "➖ 出庫（申請）": "outbound",  # GUEST用
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
            
            # session_state.menu に日本語が入っていたら menu_id に変換
            current_menu = st.session_state.get("menu")
            if current_menu and current_menu in legacy_map:
                st.session_state.menu_id = legacy_map[current_menu]
                del st.session_state["menu"]  # 古いキーは消す
            
            # 承認系（動的ラベルだったもの）の救済
            if current_menu:
                if str(current_menu).startswith("✅ 承認管理"):
                    st.session_state.menu_id = "approval"
                    if "menu" in st.session_state: del st.session_state["menu"]
                elif str(current_menu).startswith("✅ 廃棄承認"):
                    st.session_state.menu_id = "disposal_approval"
                    if "menu" in st.session_state: del st.session_state["menu"]
                elif str(current_menu).startswith("✅ 発注申請管理"):
                    st.session_state.menu_id = "purchase_admin"
                    if "menu" in st.session_state: del st.session_state["menu"]

        # 移行処理を実行 (初回のみ)
        if "menu" in st.session_state and "menu_id" not in st.session_state:
            _migrate_legacy_menu_to_id()

        # === 以下、新メニューロジック (IDベース) ===
        
        # 1. メニュー構成の定義: (ID, ラベル, 条件) のリスト
        menu_items = []
        
        if is_guest():
            # GUESTは出庫（申請）のみ
            menu_items.append(("outbound", "➖ 出庫（申請）"))
        else:
            # USER/ADMIN: 基本メニュー
            menu_items.append(("inventory", "📦 在庫一覧"))
            menu_items.append(("alert", "🚨 アラート"))
            menu_items.append(("purchase_request", "📝 発注申請"))
            menu_items.append(("disposal_request", "🗑️ 廃棄申請"))
            
            # 入庫：ADMIN/USERのみ
            if can_inbound():
                menu_items.append(("inbound", "➕ 入庫"))
            
            # 出庫：USER/ADMIN
            menu_items.append(("outbound", "➖ 出庫"))
            menu_items.append(("history", "📋 履歴"))
            menu_items.append(("stats", "📊 集計"))
            
            # AIアシスタント
            if AI_ENABLED:
                menu_items.append(("ai", "🤖 AIアシスタント"))
            
            # 承認管理 (動的ラベル)
            if can_inbound():
                menu_items.append(("approval", "✅ 承認管理"))
            
            # 廃棄承認 (動的ラベル)
            if is_admin():
                menu_items.append(("disposal_approval", "✅ 廃棄承認"))
            
            # 発注申請管理 (動的ラベル)
            if is_admin():
                menu_items.append(("purchase_admin", "✅ 発注申請管理"))
            
            # 管理者メニュー
            if can_adjust():
                menu_items.append(("adjust", "🔧 在庫調整"))
            
            if is_admin():
                menu_items.append(("item_master", "📦 物品マスター管理"))
                menu_items.append(("vendor", "🏢 業者管理"))
                menu_items.append(("users", "👥 ユーザー管理"))
                menu_items.append(("departments", "🏢 部署管理"))
                menu_items.append(("maintenance", "🛠️ メンテナンス"))
                menu_items.append(("demo", "🎭 デモモード"))

        # 2. メニューIDと表示ラベルのマッピング作成
        menu_options = [item[0] for item in menu_items]     # ラジオボタンの選択肢 (IDのリスト)
        menu_labels = {item[0]: item[1] for item in menu_items} # ID -> 基本ラベル

        # 3. 動的ラベルの生成関数 (format_func用)
        def format_menu_label(menu_id):
            base_label = menu_labels.get(menu_id, menu_id)
            
            # 動的バッジの付与ロジック
            if menu_id == "approval":
                # 承認待ち件数
                current_user = get_current_user()
                user_dept_id = current_user.get("department_id")
                if is_admin():
                    pending_count = get_pending_count()
                else:
                    pending_count = get_pending_count(department_id=user_dept_id)
                
                if pending_count > 0:
                    return f"{base_label} 🔴{pending_count}件"
            
            elif menu_id == "disposal_approval":
                # 廃棄承認待ち
                disposal_pending_count = get_disposal_count(status="PENDING")
                if disposal_pending_count > 0:
                    return f"{base_label} 🔴{disposal_pending_count}件"
            
            elif menu_id == "purchase_admin":
                # 発注申請承認待ち
                pr_counts = get_purchase_request_counts()
                pr_pending = pr_counts.get("pending", 0)
                if pr_pending > 0:
                    return f"{base_label} 🔴{pr_pending}件"

            return base_label

        # 4. サイドバーメニューの表示
        # 初期値の設定 (未設定ならリストの先頭)
        if "menu_id" not in st.session_state:
            st.session_state.menu_id = menu_options[0]
        elif st.session_state.menu_id not in menu_options:
             # 権限変更などでアクセスできないIDが残っていた場合のリセット
            if "outbound" in menu_options:
                # GUESTでinventoryが無い場合などを考慮
                 st.session_state.menu_id = menu_options[0]
            else:
                 st.session_state.menu_id = menu_options[0]

        # 保険：menu_idとsb_menuがずれていたら、sb_menuをmenu_idに同期させる
        # if "sb_menu" in st.session_state and st.session_state.sb_menu != st.session_state.menu_id:
        #     if st.session_state.menu_id in menu_options:
        #         st.session_state.sb_menu = st.session_state.menu_id

        # 他ページからの遷移リクエストがあればサイドバーの状態を更新
        if "pending_menu_id" in st.session_state:
            pending = st.session_state.pop("pending_menu_id")
            if pending in menu_options:
                st.session_state.sb_menu = pending

        # サイドバーでのメニュー選択（key="sb_menu"）
        selected_menu_id = st.radio(
            "メニュー",
            options=menu_options,
            format_func=format_menu_label,
            index=menu_options.index(st.session_state.menu_id) if st.session_state.menu_id in menu_options else 0,
            key="sb_menu"
        )
        
        # sb_menu の変更を menu_id に同期 & ページリセット
        if selected_menu_id != st.session_state.menu_id:
            st.session_state.menu_id = selected_menu_id
            st.session_state.current_page = 1 # ページ切り替え時にページネーションリセット
            st.rerun() 

    # メインコンテンツルーティング (IDベースで分岐)
    current_menu_id = st.session_state.menu_id

    if current_menu_id == "inventory":
        show_inventory_page()
    elif current_menu_id == "alert":
        show_alert_page()
    elif current_menu_id == "purchase_request":
        show_purchase_request_page()
    elif current_menu_id == "disposal_request":
        show_disposal_request_page()
    elif current_menu_id == "inbound":
        show_inbound_page()
    elif current_menu_id == "outbound":
        show_outbound_page()
    elif current_menu_id == "history":
        show_history_page()
    elif current_menu_id == "stats":
        show_statistics_page()
    elif current_menu_id == "ai":
        show_ai_assistant_page()
    elif current_menu_id == "approval":
        show_approval_page()
    elif current_menu_id == "disposal_approval":
        show_disposal_approval_page()
    elif current_menu_id == "purchase_admin":
        show_purchase_request_admin_page()
    elif current_menu_id == "adjust":
        show_adjust_page()
    elif current_menu_id == "item_master":
        show_item_master_management_page()
    elif current_menu_id == "vendor":
        show_vendor_management_page()
    elif current_menu_id == "users":
        show_user_management_page()
    elif current_menu_id == "departments":
        show_department_management_page()
    elif current_menu_id == "maintenance":
        show_maintenance_page()
    elif current_menu_id == "demo":
        show_demo_mode_page()
    else:
        st.info(f"機能 {current_menu_id} は実装準備中です")


# =============================================================================
# 発注申請ページ（USER/ADMIN向け）
# =============================================================================

def show_purchase_request_page():
    """📝 発注申請ページ（USER/ADMIN）"""
    st.header("📝 発注申請")
    show_refresh_button()

    # 権限チェック（共通関数使用）：USER以上
    if not require_min_role("USER", "発注申請はUSER/ADMINのみ利用できます"):
        return

    current_user = get_current_user()
    user_dept = current_user.get("department")

    # ADMINは対象部署を選べる
    if is_admin():
        depts = get_all_departments()
        dept_names = [d['name'] for d in depts]
        default_idx = dept_names.index(user_dept) if user_dept in dept_names else 0
        selected_dept = st.selectbox("申請先部署", options=dept_names, index=default_idx)
        department_filter = selected_dept
    else:
        department_filter = user_dept
        st.info(f"📍 申請部署: {user_dept}")

    # 参考情報：自動発注候補
    with st.expander("参考: 発注点割れ物品（参考情報）", expanded=False):
        st.info("発注点を下回っている物品の一覧です。申請は下のフォームから行ってください。")
        try:
            from db import get_reorder_candidates, check_items_ordered_status
            candidates = get_reorder_candidates(department_name=department_filter)
            if candidates:
                st.metric("発注候補件数", f"{len(candidates)}件")
                st.write("**発注候補物品:**")
                
                # 申請・発注済み状態をチェック
                item_ids = [item['item_id'] for item in candidates[:10]]
                order_status = check_items_ordered_status(item_ids)
                
                for idx, item in enumerate(candidates[:10], 1):  # 最大10件表示
                    item_id = item['item_id']
                    item_info = order_status.get(item_id)
                    
                    status_text = ""
                    if item_info:
                        status = item_info.get('status')
                        qty = item_info.get('qty', 0)
                        if status == 'ordered':
                            status_text = f" 申請済 ✅ 発注済（{qty}個）。到着までしばらくお待ちください。"
                        elif status == 'pending':
                            status_text = f" 申請済（{qty}個）"
                    
                    st.write(f"{idx}. {item['item_name']} (在庫: {item['current_stock']}, 発注点: {item['threshold']}){status_text}")
                if len(candidates) > 10:
                    st.caption(f"...他 {len(candidates) - 10}件")
            else:
                st.success("✅ 発注候補はありません")
        except Exception:
            pass

    st.divider()

    # 申請フォーム
    st.subheader("📋 申請フォーム")
    
    # アラート画面から事前選択された物品情報を取得
    prefill_item_id = st.session_state.get("prefill_purchase_item_id")
    prefill_qty = st.session_state.get("prefill_purchase_quantity")
    prefill_reason = st.session_state.get("prefill_purchase_reason", "")
    
    # アラートから来た場合は目立つ通知を表示
    if prefill_item_id:
        st.info(f"📌 **在庫不足アラートから選択されました**")
    
    # 申請成功メッセージの表示（rerun前に設定されたデータ）
    if "last_purchase_request_success" in st.session_state and st.session_state.last_purchase_request_success:
        # 事前選択情報をクリア（アラートページへの戻りを防ぐ）
        if "prefill_purchase_item_id" in st.session_state:
            del st.session_state.prefill_purchase_item_id
        if "prefill_purchase_quantity" in st.session_state:
            del st.session_state.prefill_purchase_quantity
        if "prefill_purchase_reason" in st.session_state:
            del st.session_state.prefill_purchase_reason
        
        # データを保存用キーに移動してrerun
        st.session_state.purchase_request_success_display = st.session_state.last_purchase_request_success.copy()
        st.session_state.last_purchase_request_success = None
        
        # ★重要★ st.session_state.menuは変更しない（= 申請ページのまま留まる）
        st.rerun()
    
    # 二重送信防止: 最後の申請情報を保存
    if "last_pr_submission" not in st.session_state:
        st.session_state.last_pr_submission = None
    
    # 物品選択（自部署タグの範囲）- フォームの外で取得
    items_df = get_inventory_list(department_name=department_filter)
    if items_df.empty:
        st.warning("対象の物品が見つかりません")
        return
    
    with st.form("purchase_request_form"):
        options = [f"{int(r['id'])} - {r['item_name']} ({r.get('item_code','')})" for _, r in items_df.iterrows()]

        # デフォルト選択インデックス
        default_index = 0
        if prefill_item_id is not None:
            for idx, opt in enumerate(options):
                try:
                    if int(opt.split(" - ")[0]) == int(prefill_item_id):
                        default_index = idx
                        break
                except Exception:
                    continue

        selected = st.selectbox("物品", options=options, index=default_index)
        selected_item_id = int(selected.split(" - ")[0])

        # 希望数量
        qty_default = str(prefill_qty) if prefill_qty is not None else ""
        qty_text = st.text_input("希望数量（必須）", value=qty_default, help="全角数字も半角に変換します")
        
        # 希望納期
        due_date_text = st.text_input("希望納期（任意）", placeholder="YYYY-MM-DD")
        
        # 優先度
        priority_display = st.selectbox("優先度", options=["通常", "至急"])
        priority = "normal" if priority_display == "通常" else "urgent"
        
        # 備考
        note = st.text_area("備考（任意）", placeholder="例: 今月造影増えてる")

        submitted = st.form_submit_button("📝 申請する", type="primary")

        if submitted:
            import time
            import hashlib
            
            # デバッグ用ログ
            print(f"[DEBUG] Purchase request form submitted: item_id={selected_item_id}, qty={qty_text}")
            
            # === バリデーション実行（現場向けシンプルAPI使用）===
            validation_errors = []
            
            # 数量（必須・正の整数）
            ok_qty, validated_qty, error_msg_qty = to_int_safe(qty_text, "希望数量", min_value=1, allow_zero=False)
            if not ok_qty:
                validation_errors.append(error_msg_qty)
            
            # 日付（任意・形式チェック）
            ok_date, validated_date, error_msg_date = validate_date_string(due_date_text, field_name="希望納期", required=False)
            if not ok_date:
                validation_errors.append(error_msg_date)
            
            # エラーがあれば表示して終了
            if validation_errors:
                for err in validation_errors:
                    st.error(err)
                st.stop()
            
            # 二重送信チェック: 同じ内容の申請を3秒以内に重複送信しないようにする
            current_time = time.time()
            submission_hash = hashlib.md5(
                f"{selected_item_id}_{validated_qty}_{priority}_{clean_string(note) if note else ''}".encode()
            ).hexdigest()
            
            if st.session_state.last_pr_submission:
                last_time, last_hash = st.session_state.last_pr_submission
                if current_time - last_time < 3 and last_hash == submission_hash:
                    st.warning("⚠️ 同じ内容の申請が処理中です。しばらくお待ちください。")
                    return

            # 申請処理
            print(f"[DEBUG] Creating purchase request: item_id={selected_item_id}, qty={validated_qty}, user_id={current_user.get('id')}")
            res = create_purchase_request(
                item_id=selected_item_id,
                requested_qty=validated_qty,
                user_id=current_user.get('id'),
                department=department_filter,
                priority=priority,
                due_date=validated_date,
                note=clean_string(note) if note else None
            )

            print(f"[DEBUG] Purchase request result: {res}")
            
            if res.get('success'):
                # 成功データを保存（rerun後に表示）
                st.session_state.last_purchase_request_success = {
                    'item_id': selected_item_id,
                    'quantity': validated_qty,
                    'priority': priority,
                    'note': clean_string(note) if note else None
                }
                
                # 最後の申請情報を記録
                st.session_state.last_pr_submission = (current_time, submission_hash)
                
                # 事前選択情報をクリア（アラートページへの戻りを防ぐ）
                if "prefill_purchase_item_id" in st.session_state:
                    del st.session_state.prefill_purchase_item_id
                if "prefill_purchase_quantity" in st.session_state:
                    del st.session_state.prefill_purchase_quantity
                if "prefill_purchase_reason" in st.session_state:
                    del st.session_state.prefill_purchase_reason
                
                # ★重要★ st.session_state.menuは変更しない（= 申請ページのまま留まる）
                print(f"[DEBUG] Purchase request submitted - staying on request page (menu={st.session_state.get('menu')})")
                st.rerun()
            else:
                st.error(f"❌ 申請に失敗しました: {res.get('message')}")
    
    # ========== 成功メッセージ表示（フォームの下） ==========
    if "purchase_request_success_display" in st.session_state:
        success_data = st.session_state.purchase_request_success_display
        st.divider()
        with st.container(border=True):
            st.success("✅ 発注申請を送信しました！")
            st.balloons()
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("**申請内容:**")
                st.write(f"- 数量: {success_data.get('quantity')}個")
                priority_label = "🔴 至急" if success_data.get('priority') == 'urgent' else "通常"
                st.write(f"- 優先度: {priority_label}")
            
            with col2:
                st.info("💡 承認をお待ちください")
                st.caption("承認状況は下の申請一覧で確認できます")
            
            if success_data.get('note'):
                st.write(f"**備考:** {success_data.get('note')}")
        
        # フラグをクリア
        del st.session_state.purchase_request_success_display

    # ========== 自分の申請一覧 ==========
    st.divider()
    st.subheader("📋 自分の申請一覧")
    
    # 自分の申請を取得（全ステータス）
    my_requests = get_purchase_requests(requester_id=current_user.get('id'))
    
    if not my_requests:
        st.info("申請履歴はありません")
    else:
        status_labels = {
            'PENDING': '⏳ 承認待ち',
            'APPROVED': '✅ 承認済み',
            'ON_HOLD': '🔴 保留中',
            'REJECTED': '❌ 却下',
            'ORDERED': '✅ 発注完了',
            'RECEIVED': '🎉 入庫完了'
        }
        
        for req in my_requests:
            status = req.get('status')
            status_label = status_labels.get(status, status)
            priority_badge = "🔴至急 " if req.get('priority') == 'urgent' else ""
            
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{priority_badge}{req.get('item_name', '')}** — {req.get('requested_qty')}個")
                    st.caption(f"申請日: {req.get('created_at', '')[:10] if req.get('created_at') else ''}")
                    if req.get('note'):
                        st.caption(f"📝 {req.get('note')}")
                with col2:
                    st.markdown(f"**{status_label}**")
                    if status == 'RECEIVED':
                        # 入庫完了の場合：入庫日時と数量を表示
                        if req.get('received_at'):
                            st.success(f"入庫完了: {req.get('received_at')[:10]}")
                        if req.get('received_qty'):
                            st.info(f"入庫数: {req.get('received_qty')}個")
                        if req.get('received_note'):
                            st.caption(f"📝 {req.get('received_note')}")
                    elif status == 'ORDERED':
                        st.success("発注完了しました。到着までしばらくお待ちください。")
                    elif req.get('admin_comment'):
                        st.caption(f"💬 {req.get('admin_comment')}")


# =============================================================================
# 発注申請管理ページ（ADMIN向け）
# =============================================================================

def handle_purchase_request_error(result: dict, request_id: int, user_id: int):
    """
    発注申請の処理エラーを適切にハンドリングし、対処オプションを表示
    
    Args:
        result: 処理結果の辞書
        request_id: 申請ID
        user_id: 管理者ID
    """
    error_code = result.get("error_code")
    current_status = result.get("current_status")
    
    if error_code == "NOT_FOUND":
        st.error("⚠️ 申請が見つかりません")
        st.info("💡 この申請は既に削除された可能性があります。ページを更新してください。")
        
    elif error_code == "ALREADY_ORDERED":
        st.warning("⚠️ この申請は既に発注済みです")
        st.info("💡 発注済みの申請は変更できません。")
        
    elif error_code == "ALREADY_APPROVED":
        st.warning("⚠️ この申請は既に承認済みです")
        with st.expander("🔧 対処オプション"):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 承認待ちに戻す", key=f"reset_pending_{request_id}", use_container_width=True):
                    res = reset_purchase_request_to_pending(request_id, user_id, "承認済みから承認待ちに戻しました")
                    if res.get("success"):
                        st.success("✅ 承認待ちに戻しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
            with col2:
                if st.button("🗑️ この申請を削除", key=f"delete_{request_id}", use_container_width=True):
                    res = delete_purchase_request(request_id)
                    if res.get("success"):
                        st.success("✅ 削除しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
    
    elif error_code == "UPDATE_FAILED":
        st.error(f"⚠️ {result.get('message')}")
        st.info(f"💡 現在のステータス: {current_status}")
        with st.expander("🔧 対処オプション"):
            st.caption("この申請に対して以下の対処ができます：")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 承認待ちに戻す", key=f"reset_pending_fail_{request_id}", use_container_width=True):
                    res = reset_purchase_request_to_pending(request_id, user_id, "処理失敗のため承認待ちに戻しました")
                    if res.get("success"):
                        st.success("✅ 承認待ちに戻しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
            with col2:
                if st.button("🗑️ この申請を削除", key=f"delete_fail_{request_id}", use_container_width=True):
                    res = delete_purchase_request(request_id)
                    if res.get("success"):
                        st.success("✅ 削除しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
    else:
        st.error(f"❌ {result.get('message')}")


def show_purchase_request_admin_page():
    """✅ 発注申請管理ページ（ADMIN向け）- 承認から発注書作成まで完結"""
    st.header("✅ 発注申請管理")
    show_refresh_button()

    # 権限チェック（共通関数使用）
    if not require_role("ADMIN", "このページは管理者のみアクセスできます"):
        return

    import pandas as pd
    from collections import defaultdict
    
    current_user = get_current_user()
    user_id = current_user.get("id")
    
    # 発注書作成画面の表示フラグ
    if "show_order_creation" not in st.session_state:
        st.session_state.show_order_creation = False
    
    # 発注書作成画面を表示中の場合
    if st.session_state.show_order_creation:
        show_order_creation_screen(user_id)
        return
    
    # ========== メイン画面 ==========
    
    # ステータス別件数
    counts = get_purchase_request_counts()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("承認待ち", f"{counts.get('pending', 0)}件")
    with col2:
        st.metric("承認済み", f"{counts.get('approved', 0)}件")
    with col3:
        st.metric("保留", f"{counts.get('on_hold', 0)}件")
    with col4:
        st.metric("却下", f"{counts.get('rejected', 0)}件")

    st.divider()
    
    # 部署フィルタ（状態保持）
    if "pr_dept_filter" not in st.session_state:
        st.session_state.pr_dept_filter = "全て"
    
    all_dept_options = ["全て"] + [d['name'] for d in get_all_departments()]
    try:
        current_index = all_dept_options.index(st.session_state.pr_dept_filter)
    except ValueError:
        current_index = 0
    
    dept_filter = st.selectbox(
        "部署で絞る", 
        options=all_dept_options,
        index=current_index,
        key="pr_dept_filter"
    )
    query_dept = None if dept_filter == "全て" else dept_filter
    
    query_dept = None if dept_filter == "全て" else dept_filter
    
    # 入庫待ち件数を取得（部署フィルタ適用後）
    waiting_for_receipt = get_purchase_requests(status="ORDERED", department=query_dept)
    waiting_count = len(waiting_for_receipt) if waiting_for_receipt else 0

    # ========== ステータスタブ ==========
    tab_pending, tab_approved, tab_hold, tab_rejected, tab_waiting = st.tabs([
        f"📋 承認待ち ({counts.get('pending', 0)}件)",
        f"✅ 承認済み ({counts.get('approved', 0)}件)",
        f"⏸ 保留 ({counts.get('on_hold', 0)}件)",
        f"❌ 却下 ({counts.get('rejected', 0)}件)",
        f"🚚 入庫待ち ({waiting_count}件)"
    ])

    # ========== タブ1: 承認待ち（PENDING） ==========
    with tab_pending:
        pending_requests = get_purchase_requests(status="PENDING", department=query_dept)
        
        if not pending_requests:
            st.info("承認待ちの申請はありません")
        else:
            # CSV出力
            df_pending = pd.DataFrame(pending_requests)
            csv_pending = df_pending.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_pending, file_name="pending_requests.csv", mime="text/csv")
            
            st.caption("💡 各申請を承認・保留・却下できます。連続して処理可能です。")
            st.divider()
            
            # 一覧表示
            for req in pending_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    # 申請情報の表示
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個 / 発注点: {req.get('threshold', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.info(f"📝 備考: {req['note']}")
                    
                    with col_action:
                        # 承認・保留・却下アクションフォーム
                        with st.form(f"action_form_{rid}"):
                            admin_comment = st.text_area(
                                "管理コメント",
                                value=req.get('admin_comment') or "",
                                key=f"comment_{rid}",
                                height=60,
                                placeholder="保留/却下時は必須",
                                help="保留または却下する場合は理由を入力してください"
                            )
                            
                            col_a, col_h, col_r = st.columns(3)
                            with col_a:
                                approve_btn = st.form_submit_button("✔", help="承認", use_container_width=True)
                            with col_h:
                                hold_btn = st.form_submit_button("⏸", help="保留", use_container_width=True)
                            with col_r:
                                reject_btn = st.form_submit_button("❌", help="却下", use_container_width=True)
                            
                            if approve_btn:
                                res = approve_purchase_request(rid, user_id, comment=admin_comment)
                                if res.get('success'):
                                    st.success("✔ 承認しました")
                                    st.rerun()
                                else:
                                    handle_purchase_request_error(res, rid, user_id)
                            
                            if hold_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 保留理由を入力してください")
                                else:
                                    res = hold_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("⏸ 保留にしました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                            
                            if reject_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 却下理由を入力してください")
                                else:
                                    res = reject_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("❌ 却下しました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                    
                    st.divider()

    # ========== タブ2: 承認済み（APPROVED） ==========
    with tab_approved:
        approved_requests = get_purchase_requests(status="APPROVED", department=query_dept)
        
        if not approved_requests:
            st.info("承認済みの申請はありません")
        else:
            # CSV出力
            df_approved = pd.DataFrame(approved_requests)
            csv_approved = df_approved.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_approved, file_name="approved_requests.csv", mime="text/csv")
            
            st.caption("💡 発注する申請にチェックを入れて「発注書を作成」ボタンを押してください。")
            
            # チェックボックス選択用のセッション管理
            if "selected_request_ids" not in st.session_state:
                st.session_state.selected_request_ids = []
            
            # 全選択/全解除
            col_select, col_clear, col_space = st.columns([1, 1, 3])
            with col_select:
                if st.button("✔ 全て選択", use_container_width=True):
                    st.session_state.selected_request_ids = [req['id'] for req in approved_requests]
                    # 各チェックボックスのSession Stateも更新
                    for req in approved_requests:
                        st.session_state[f"check_{req['id']}"] = True
                    st.rerun()
            with col_clear:
                if st.button("◻ 全て解除", use_container_width=True):
                    st.session_state.selected_request_ids = []
                    # 各チェックボックスのSession Stateも更新
                    for req in approved_requests:
                        st.session_state[f"check_{req['id']}"] = False
                    st.rerun()
            
            st.divider()
            
            # 一覧表示（チェックボックス付き）
            for req in approved_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    col_check, col_info = st.columns([1, 10])
                    
                    with col_check:
                        is_checked = rid in st.session_state.selected_request_ids
                        
                        # チェックボックスの状態をセッションで管理
                        checkbox_key = f"check_{rid}"
                        
                        # Session Stateに値を設定（valueパラメータは使わない）
                        if checkbox_key not in st.session_state or st.session_state.get(f"_force_update_{rid}", False):
                            st.session_state[checkbox_key] = is_checked
                            if f"_force_update_{rid}" in st.session_state:
                                del st.session_state[f"_force_update_{rid}"]
                        
                        if st.checkbox("選択", key=checkbox_key, label_visibility="collapsed"):
                            if rid not in st.session_state.selected_request_ids:
                                st.session_state.selected_request_ids.append(rid)
                        else:
                            if rid in st.session_state.selected_request_ids:
                                st.session_state.selected_request_ids.remove(rid)
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.caption(f"📝 {req['note']}")
                        if req.get('admin_comment'):
                            st.caption(f"💬 管理コメント: {req['admin_comment']}")
                    
                    st.divider()
            
            # 発注書作成・保留・却下ボタン
            selected_count = len(st.session_state.selected_request_ids)
            if selected_count > 0:
                st.markdown(f"### 📦 選択中: {selected_count}件")
                
                col_order, col_hold, col_reject = st.columns(3)
                
                with col_order:
                    if st.button("📝 発注書を作成", type="primary", use_container_width=True):
                        # 選択された申請を一時保存して発注書作成画面へ
                        st.session_state.order_creation_request_ids = st.session_state.selected_request_ids.copy()
                        st.session_state.show_order_creation = True
                        st.rerun()
                
                with col_hold:
                    if st.button("⏸ 選択を保留に", use_container_width=True):
                        st.session_state.show_hold_form = True
                
                with col_reject:
                    if st.button("❌ 選択を却下に", use_container_width=True):
                        st.session_state.show_reject_form = True
                
                # 保留フォームの表示
                if st.session_state.get("show_hold_form", False):
                    with st.form("bulk_hold_form"):
                        st.subheader("⏸ 選択した申請を保留にする")
                        hold_reason = st.text_area(
                            "保留理由（必須）",
                            placeholder="保留する理由を入力してください",
                            height=100
                        )
                        
                        col_submit, col_cancel = st.columns(2)
                        with col_submit:
                            submit_hold = st.form_submit_button("⏸ 保留にする", type="primary", use_container_width=True)
                        with col_cancel:
                            cancel_hold = st.form_submit_button("キャンセル", use_container_width=True)
                        
                        if submit_hold:
                            if not hold_reason or hold_reason.strip() == "":
                                st.error("⚠️ 保留理由を入力してください")
                            else:
                                success_count = 0
                                for req_id in st.session_state.selected_request_ids:
                                    res = hold_purchase_request(req_id, user_id, comment=hold_reason)
                                    if res.get('success'):
                                        success_count += 1
                                
                                if success_count > 0:
                                    st.success(f"⏸ {success_count}件を保留にしました")
                                    st.session_state.selected_request_ids = []
                                    st.session_state.show_hold_form = False
                                    st.rerun()
                        
                        if cancel_hold:
                            st.session_state.show_hold_form = False
                            st.rerun()
                
                # 却下フォームの表示
                if st.session_state.get("show_reject_form", False):
                    with st.form("bulk_reject_form"):
                        st.subheader("❌ 選択した申請を却下にする")
                        reject_reason = st.text_area(
                            "却下理由（必須）",
                            placeholder="却下する理由を入力してください",
                            height=100
                        )
                        
                        col_submit, col_cancel = st.columns(2)
                        with col_submit:
                            submit_reject = st.form_submit_button("❌ 却下にする", type="primary", use_container_width=True)
                        with col_cancel:
                            cancel_reject = st.form_submit_button("キャンセル", use_container_width=True)
                        
                        if submit_reject:
                            if not reject_reason or reject_reason.strip() == "":
                                st.error("⚠️ 却下理由を入力してください")
                            else:
                                success_count = 0
                                for req_id in st.session_state.selected_request_ids:
                                    res = reject_purchase_request(req_id, user_id, comment=reject_reason)
                                    if res.get('success'):
                                        success_count += 1
                                
                                if success_count > 0:
                                    st.success(f"❌ {success_count}件を却下にしました")
                                    st.session_state.selected_request_ids = []
                                    st.session_state.show_reject_form = False
                                    st.rerun()
                        
                        if cancel_reject:
                            st.session_state.show_reject_form = False
                            st.rerun()

    # ========== タブ3: 保留（ON_HOLD） ==========
    with tab_hold:
        hold_requests = get_purchase_requests(status="ON_HOLD", department=query_dept)
        
        if not hold_requests:
            st.info("保留中の申請はありません")
        else:
            # CSV出力
            df_hold = pd.DataFrame(hold_requests)
            csv_hold = df_hold.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_hold, file_name="hold_requests.csv", mime="text/csv")
            
            st.caption("💡 保留中の申請を承認または却下できます。")
            st.divider()
            
            # 一覧表示
            for req in hold_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    # 申請情報の表示
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.caption(f"📝 備考: {req['note']}")
                        
                        if req.get('admin_comment'):
                            st.warning(f"⏸ 保留理由: {req['admin_comment']}")
                    
                    with col_action:
                        # 承認・却下・削除フォーム
                        with st.form(f"hold_action_form_{rid}"):
                            admin_comment = st.text_area(
                                "管理コメント更新",
                                value=req.get('admin_comment') or "",
                                key=f"hold_comment_{rid}",
                                height=60,
                                placeholder="コメントを更新（任意）",
                                help="承認または却下する際のコメント"
                            )
                            
                            col_a, col_r, col_d = st.columns(3)
                            with col_a:
                                approve_btn = st.form_submit_button("✔", help="承認", use_container_width=True)
                            with col_r:
                                reject_btn = st.form_submit_button("❌", help="却下", use_container_width=True)
                            with col_d:
                                delete_btn = st.form_submit_button("🗑️", help="削除", use_container_width=True)
                            
                            if approve_btn:
                                res = approve_purchase_request(rid, user_id, comment=admin_comment)
                                if res.get('success'):
                                    st.success("✔ 承認しました")
                                    st.rerun()
                                else:
                                    handle_purchase_request_error(res, rid, user_id)
                            
                            if reject_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 却下理由を入力してください")
                                else:
                                    res = reject_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("❌ 却下しました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                            
                            if delete_btn:
                                res = delete_purchase_request(rid, user_id)
                                if res.get('success'):
                                    st.success("🗑️ 削除しました")
                                    st.rerun()
                                else:
                                    st.error(res.get('message'))
                    
                    st.divider()

    # ========== タブ4: 却下（REJECTED） ==========
    with tab_rejected:
        rejected_requests = get_purchase_requests(status="REJECTED", department=query_dept)
        
        if not rejected_requests:
            st.info("却下された申請はありません")
        else:
            # CSV出力
            df_rejected = pd.DataFrame(rejected_requests)
            csv_rejected = df_rejected.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_rejected, file_name="rejected_requests.csv", mime="text/csv")
            
            st.caption("💡 却下された申請を確認できます。承認に戻すこともできます。")
            st.divider()
            
            # 一覧表示
            for req in rejected_requests:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container():
                    # 申請情報の表示
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        st.markdown(f"**{req['item_name']}** {priority_badge}")
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.caption(f"👤 {req.get('requester_name', '')} ({req['requested_by_department']})")
                            st.caption(f"📅 {req.get('created_at', '')}")
                        with col_b:
                            st.caption(f"📦 数量: {req['requested_qty']}個")
                            st.caption(f"📊 現在庫: {req.get('current_stock', 0)}個")
                        with col_c:
                            st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                            st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        
                        if req.get('note'):
                            st.caption(f"📝 備考: {req['note']}")
                        
                        if req.get('admin_comment'):
                            st.error(f"❌ 却下理由: {req['admin_comment']}")
                    
                    with col_action:
                        # 承認待ち・保留・削除フォーム
                        with st.form(f"reject_action_form_{rid}"):
                            admin_comment = st.text_area(
                                "管理コメント更新",
                                value=req.get('admin_comment') or "",
                                key=f"reject_comment_{rid}",
                                height=60,
                                placeholder="コメントを更新（任意）",
                                help="承認待ちまたは保留する際のコメント"
                            )
                            
                            col_p, col_h, col_d = st.columns(3)
                            with col_p:
                                pending_btn = st.form_submit_button("🔄", help="承認待ちに戻す", use_container_width=True)
                            with col_h:
                                hold_btn = st.form_submit_button("⏸", help="保留", use_container_width=True)
                            with col_d:
                                delete_btn = st.form_submit_button("🗑️", help="削除", use_container_width=True)
                            
                            if pending_btn:
                                res = reset_purchase_request_to_pending(rid, user_id, comment=admin_comment)
                                if res.get('success'):
                                    st.success("🔄 承認待ちに戻しました")
                                    st.rerun()
                                else:
                                    st.error(res.get('message'))
                            
                            if hold_btn:
                                if not admin_comment or admin_comment.strip() == "":
                                    st.error("⚠️ 保留理由を入力してください")
                                else:
                                    res = hold_purchase_request(rid, user_id, comment=admin_comment)
                                    if res.get('success'):
                                        st.success("⏸ 保留にしました")
                                        st.rerun()
                                    else:
                                        handle_purchase_request_error(res, rid, user_id)
                            
                            if delete_btn:
                                res = delete_purchase_request(rid, user_id)
                                if res.get('success'):
                                    st.success("🗑️ 削除しました")
                                    st.rerun()
                                else:
                                    st.error(res.get('message'))
                    
                    st.divider()

    # ========== タブ5: 入庫待ち（ORDERED） ==========
    with tab_waiting:
        st.caption("💡 発注処理が完了し、現場での入庫待ちの申請です。")
        
        if not waiting_for_receipt:
            st.info("入庫待ちの申請はありません")
        else:
            # CSV出力
            df_waiting = pd.DataFrame(waiting_for_receipt)
            csv_waiting = df_waiting.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV出力", data=csv_waiting, file_name="waiting_for_receipt.csv", mime="text/csv")
            
            st.divider()
            
            # 一覧表示
            for req in waiting_for_receipt:
                rid = req['id']
                priority_badge = "🔴至急" if req.get('priority') == 'urgent' else ""
                
                with st.container(border=True):
                    st.markdown(f"### {req['item_name']} {priority_badge}")
                    
                    # 基本情報
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write("**📋 申請情報**")
                        st.caption(f"👤 申請者: {req.get('requester_name', '')} ({req['requested_by_department']})")
                        st.caption(f"📅 申請日: {req.get('created_at', '')[:10] if req.get('created_at') else ''}")
                        st.caption(f"📦 希望数量: {req['requested_qty']}個")
                        if req.get('note'):
                            st.caption(f"📝 申請メモ: {req['note']}")
                    
                    with col2:
                        st.write("**✅ 承認・発注情報**")
                        if req.get('approved_at'):
                            st.caption(f"✅ 承認日: {req['approved_at'][:10]}")
                        if req.get('ordered_at'):
                            st.caption(f"🚚 発注日: {req['ordered_at'][:10]}")
                        if req.get('order_channel'):
                            channel_map = {'email': 'メール', 'pdf': 'PDF', 'excel': 'Excel'}
                            st.caption(f"📤 発注方法: {channel_map.get(req['order_channel'], req['order_channel'])}")
                        if req.get('generated_document_name'):
                            st.caption(f"📄 発注書: {req['generated_document_name']}")
                    
                    with col3:
                        st.write("**📦 物品情報**")
                        st.caption(f"品目コード: {req.get('item_code', '-')}")
                        st.caption(f"🏢 業者: {req.get('vendor_name', '未設定')}")
                        st.caption(f"💰 単価: ¥{req.get('unit_price', 0):,.0f}")
                        st.caption(f"💰 合計: ¥{req['requested_qty'] * req.get('unit_price', 0):,.0f}")
                    
                    if req.get('admin_comment'):
                        st.info(f"💬 管理者コメント: {req['admin_comment']}")
                    
                    # 入庫ページへのリンク案内
                    st.success("📍 入庫処理は「➕ 入庫」→「🚚 発注品入庫」タブで行えます")
                    
                st.divider()


def show_order_creation_screen(user_id: int):
    """発注書作成画面（メール文面・PDF・Excel出力対応）"""
    from datetime import datetime
    from purchase_order_payload import build_purchase_order_payloads
    from purchase_order_renderers import generate_email_text, render_pdf, render_excel
    
    st.header("📝 発注書作成")
    
    # 戻るボタン
    if st.button("← 発注申請管理に戻る"):
        st.session_state.show_order_creation = False
        for key in ["order_creation_request_ids", "order_draft_text", "po_generated",
                    "last_output_channel", "last_document_name", "order_payloads"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
    
    st.divider()
    
    # 選択された申請IDを取得
    request_ids = st.session_state.get("order_creation_request_ids", [])
    if not request_ids:
        st.error("申請が選択されていません。発注申請管理画面に戻ってください。")
        return
    
    # ========== payload生成（正本データ） ==========
    if "order_payloads" not in st.session_state:
        # DBからpayloadを一度だけ生成
        with get_db_connection() as conn:
            st.session_state.order_payloads = build_purchase_order_payloads(request_ids, conn)
    
    payloads = st.session_state.order_payloads
    
    if not payloads:
        st.error("発注データの生成に失敗しました。")
        return
    
    # ========== 単価未設定チェック ==========
    total_unpriced = sum(1 for p in payloads if p.get("has_unpriced_items", False))
    
    if total_unpriced > 0:
        unconfirmed_items = []
        for payload in payloads:
            if payload.get("has_unpriced_items"):
                for item in payload.get("items", []):
                    if item.get("unit_price") is None:
                        unconfirmed_items.append({
                            'vendor': payload.get("vendor", "不明業者"),
                            'item_name': item.get("item_name", ""),
                            'item_code': item.get("item_code", ""),
                            'qty': item.get("quantity", 0)
                        })
        
        st.warning(f"⚠️ **単価未設定の品目が {len(unconfirmed_items)}件 あります。発注書の金額は「要確認」となります。**")
        with st.expander(f"📋 単価未設定の品目一覧 ({len(unconfirmed_items)}件)", expanded=False):
            for item in unconfirmed_items:
                st.write(f"- **{item['item_name']}** ({item['item_code']}) × {item['qty']}個 - 業者: {item['vendor']}")
    
    # ========== 発注明細テーブル表示 ==========
    total_items = sum(len(p.get("items", [])) for p in payloads)
    st.subheader(f"📦 発注対象: {total_items}件（{len(payloads)}業者）")
    
    for payload in payloads:
        vendor = payload.get("vendor", "不明業者")
        items = payload.get("items", [])
        with st.expander(f"🏢 {vendor} ({len(items)}件)", expanded=True):
            for item in items:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"**{item.get('item_name', '')}**")
                    st.caption(f"品目コード: {item.get('item_code', '')}")
                with col2:
                    st.write(f"数量: {item.get('quantity', 0)}個")
                with col3:
                    unit_price = item.get('unit_price')
                    if unit_price is not None:
                        st.write(f"単価: ¥{unit_price:,.0f}")
                    else:
                        st.warning("単価: 未設定")
    
    st.divider()
    
    # ========== AI文案生成・編集エリア ==========
    st.subheader("📝 発注文案の生成・編集")
    
    # テンプレート文案を生成する関数
    def generate_template_draft(payloads_list):
        """テンプレート発注文案を生成（payloadベース）"""
        all_drafts = []
        for payload in payloads_list:
            vendor = payload.get("vendor", "不明業者")
            items = payload.get("items", [])
            has_unpriced = payload.get("has_unpriced_items", False)
            total = payload.get("total")
            
            draft_lines = [f"【{vendor} 御中】", ""]
            draft_lines.append("いつもお世話になっております。")
            draft_lines.append("下記の通り発注いたしますので、納品のほどよろしくお願い申し上げます。")
            draft_lines.append("")
            draft_lines.append("【発注明細】")
            
            for idx, item in enumerate(items, 1):
                item_name = item.get("item_name", "")
                item_code = item.get("item_code", "")
                qty = item.get("quantity", 0)
                unit_price = item.get("unit_price")
                subtotal = item.get("subtotal")
                
                if unit_price is not None and subtotal is not None:
                    draft_lines.append(f"{idx}. {item_name}（{item_code}）× {qty}個 @ ¥{unit_price:,.0f} = ¥{subtotal:,.0f}")
                else:
                    draft_lines.append(f"{idx}. {item_name}（{item_code}）× {qty}個 @ 単価未設定 = 要確認")
            
            draft_lines.append("")
            if has_unpriced or total is None:
                draft_lines.append("【合計金額】要確認")
            else:
                draft_lines.append(f"【合計金額】¥{total:,.0f}")
            draft_lines.append("")
            draft_lines.append("以上、よろしくお願いいたします。")
            
            all_drafts.append("\n".join(draft_lines))
        
        return "\n\n" + "="*60 + "\n\n".join(all_drafts)
    
    # 初期表示: テンプレート文案
    if "order_draft_text" not in st.session_state:
        st.session_state.order_draft_text = generate_template_draft(payloads)
    
    # AI生成ボタン（AI有効時のみ表示）
    import os
    can_use_ai = AI_ENABLED and os.getenv("OPENAI_API_KEY")
    
    if can_use_ai:
        # DEBUG: AI入力データの確認
        if st.checkbox("🔧 DEBUG: AI入力データを表示", key="debug_ai_input"):
            st.write("DEBUG payloads (AI input):", payloads)

        if st.button("🤖 AIで文案を生成", use_container_width=True):
            try:
                with st.spinner("🤖 AI文案を生成中..."):
                    # payloadごとにAI文案を生成
                    all_drafts = []
                    for payload in payloads:
                        draft = generate_email_text(payload, use_ai=True)
                        all_drafts.append(draft)
                    
                    # 複数業者の場合は区切り線で結合
                    st.session_state.order_draft_text = "\n\n" + "="*80 + "\n\n".join(all_drafts)
                    st.success("✅ AI文案を生成しました")
                    st.rerun()
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                st.error(f"⚠️ AI生成に失敗しました。テンプレート文案を使用してください。\n\nエラー: {str(e)}\n\n詳細:\n{error_detail}")
    
    # 文案編集エリア
    edited_draft = st.text_area(
        "発注文案（編集可能）",
        value=st.session_state.order_draft_text,
        height=300,
        help="この文案はメール出力に反映されます"
    )
    
    # 編集内容を保存
    if edited_draft != st.session_state.order_draft_text:
        st.session_state.order_draft_text = edited_draft
    
    # テンプレートに戻すボタン
    if st.button("🔄 テンプレート文案に戻す", use_container_width=True):
        st.session_state.order_draft_text = generate_template_draft(payloads)
        st.rerun()
    
    st.divider()
    
    # ========== 出力ボタン ==========
    st.subheader("📤 発注書の出力")
    st.caption("いずれかの形式で出力してください。出力後に「発注済み確定」ボタンが有効になります。")
    
    col_email, col_pdf, col_excel = st.columns(3)
    
    with col_email:
        if st.button("📧 メール文面を生成", use_container_width=True, type="primary"):
            email_texts = []
            for payload in payloads:
                # 編集済みdraft_textをメール文面として使用
                email_text = st.session_state.order_draft_text
                email_texts.append(email_text)
            
            st.session_state.email_output = st.session_state.order_draft_text
            st.session_state.po_generated = True
            st.session_state.last_output_channel = "email"
            st.session_state.last_document_name = f"email_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d_%H%M%S')}.txt"
            st.success("✅ メール文面を生成しました")
    
    with col_pdf:
        if st.button("📄 PDFで発注書出力", use_container_width=True, type="primary"):
            # 最初の業者のPDFを生成
            first_payload = payloads[0]
            
            try:
                pdf_data = render_pdf(first_payload)
                st.session_state.pdf_output = pdf_data
                st.session_state.po_generated = True
                st.session_state.last_output_channel = "pdf"
                st.session_state.last_document_name = f"purchase_order_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d_%H%M%S')}.pdf"
                st.success("✅ PDFを生成しました")
            except Exception as e:
                st.error(f"❌ PDF生成エラー: {str(e)}")
    
    with col_excel:
        if st.button("📊 Excelで発注書出力", use_container_width=True, type="primary"):
            try:
                excel_data = render_excel(payloads)
                st.session_state.excel_output = excel_data
                st.session_state.po_generated = True
                st.session_state.last_output_channel = "excel"
                st.session_state.last_document_name = f"purchase_order_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d_%H%M%S')}.xlsx"
                st.success("✅ Excelを生成しました")
            except Exception as e:
                st.error(f"❌ Excel生成エラー: {str(e)}")
    
    st.divider()
    
    # ========== 出力結果の表示・ダウンロード ==========
    if st.session_state.get("email_output"):
        st.subheader("📧 生成されたメール文面")
        st.code(st.session_state.email_output, language="text")
        st.download_button(
            "📥 メール文面をダウンロード",
            data=st.session_state.email_output.encode("utf-8"),
            file_name=st.session_state.get("last_document_name", "email.txt"),
            mime="text/plain",
            use_container_width=True
        )
        st.divider()
    
    if st.session_state.get("pdf_output"):
        st.subheader("📄 生成されたPDF発注書")
        st.success("PDFが生成されました。ダウンロードボタンからダウンロードしてください。")
        st.download_button(
            "📥 PDFをダウンロード",
            data=st.session_state.pdf_output,
            file_name=st.session_state.get("last_document_name", "purchase_order.pdf"),
            mime="application/pdf",
            use_container_width=True
        )
        st.divider()
    
    if st.session_state.get("excel_output"):
        st.subheader("📊 生成されたExcel発注書")
        st.success("Excelファイルが生成されました。ダウンロードボタンからダウンロードしてください。")
        st.download_button(
            "📥 Excelをダウンロード",
            data=st.session_state.excel_output,
            file_name=st.session_state.get("last_document_name", "purchase_order.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.divider()
    
    # ========== 発注済み確定ボタン ==========
    if st.session_state.get("po_generated", False):
        st.subheader("✅ 発注済みに確定")
        st.warning("⚠️ この操作を実行すると、選択した申請が「発注済み（ORDERED）」になります。")
        
        if st.button("✅ 発注済みに確定する", type="primary", use_container_width=True):
            # 二重実行防止
            if st.session_state.get("order_finalized", False):
                st.error("既に発注済みに確定しています。")
            else:
                result = mark_requests_ordered(
                    request_ids, 
                    user_id,
                    order_channel=st.session_state.get("last_output_channel"),
                    document_name=st.session_state.get("last_document_name")
                )
                
                if result.get("success"):
                    st.balloons()
                    st.success(f"🎉 {result['count']}件を発注済みにしました！")
                    st.session_state.order_finalized = True
                    
                    # セッションクリア
                    import time
                    time.sleep(2)
                    
                    # クリーンアップ
                    for key in ["order_creation_request_ids", "order_draft_text", "email_output", 
                                "pdf_output", "excel_output", "po_generated", 
                                "last_output_channel", "last_document_name", "order_finalized", "order_payloads"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    
                    st.session_state.selected_request_ids = []
                    st.session_state.show_order_creation = False
                    st.rerun()
                else:
                    st.error(result.get("message"))
    else:
        st.info("💡 メール文面・PDF・Excelのいずれかを生成すると、発注済み確定ボタンが表示されます。")


if __name__ == "__main__":
    main()

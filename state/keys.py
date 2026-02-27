"""
session_state キー定数の一元管理

全ての session_state キーはこのモジュールに定義し、
文字列リテラルの散在を防止する。
"""


class K:
    """session_state キー定数（短縮名で使いやすく）"""

    # ─── 認証・初期化 ───
    LOGGED_IN = "logged_in"
    CURRENT_USER = "current_user"
    INITIALIZED = "initialized"
    DB_CHECK_DONE = "db_check_done"
    DISPLAY_SIZE = "display_size"
    REFRESH_TOKEN = "refresh_token"

    # ─── メニュー・ナビゲーション ───
    MENU_ID = "menu_id"
    PENDING_MENU_ID = "pending_menu_id"
    SB_MENU = "sb_menu"
    MENU_LEGACY = "menu"  # 旧日本語ラベル（互換性用）
    CURRENT_PAGE = "current_page"

    # ─── 出庫関連 ───
    LAST_OUTBOUND_SUCCESS = "last_outbound_success"
    OUTBOUND_SUCCESS_DISPLAY = "outbound_success_display"
    OUTBOUND_FORM_SUCCESS = "outbound_form_success"
    OUTBOUND_BUTTON_DISABLED = "outbound_button_disabled"
    LAST_UNDO_OUTBOUND_SUCCESS = "last_undo_outbound_success"
    LAST_UNDO_OUTBOUND_ERROR = "last_undo_outbound_error"
    QUICK_OUTBOUND_SUCCESS = "quick_outbound_success"
    CANCEL_SUCCESS_MESSAGE = "cancel_success_message"
    CANCEL_ERROR_MESSAGE = "cancel_error_message"

    # ─── 入庫関連 ───
    LAST_INBOUND_SUCCESS = "last_inbound_success"
    INBOUND_SUCCESS_DISPLAY = "inbound_success_display"
    INBOUND_FORM_SUCCESS = "inbound_form_success"
    INBOUND_BUTTON_DISABLED = "inbound_button_disabled"
    LAST_UNDO_INBOUND_SUCCESS = "last_undo_inbound_success"
    LAST_UNDO_INBOUND_ERROR = "last_undo_inbound_error"
    RECEIVE_SUCCESS_MESSAGE = "receive_success_message"

    # ─── 在庫調整 ───
    LAST_ADJUST_SUCCESS = "last_adjust_success"

    # ─── 承認管理 ───
    APPROVAL_SUCCESS_MESSAGE = "approval_success_message"
    APPROVAL_ERROR_MESSAGE = "approval_error_message"

    # ─── ユーザー管理 ───
    USER_PAGE = "user_page"
    USER_PREV_FILTERS = "user_prev_filters"
    USER_SELECTED_ID = "user_selected_id"

    # ─── 物品マスター管理 ───
    ITEM_PAGE = "item_page"
    VIEWING_ITEM_ID = "viewing_item_id"
    EDITING_ITEM_ID = "editing_item_id"
    FORM_RESET_COUNTER = "form_reset_counter"
    ITEM_REGISTER_SUCCESS = "item_register_success"

    # ─── 業者管理 ───
    VENDOR_PAGE = "vendor_page"
    VENDOR_PREV_FILTERS = "vendor_prev_filters"
    VENDOR_SELECTED_ID = "vendor_selected_id"
    VENDOR_REGISTER_SUCCESS = "vendor_register_success"
    VENDOR_FORM_RESET_COUNTER = "vendor_form_reset_counter"

    # ─── 部署管理 ───
    DEPT_PAGE = "dept_page"
    DEPT_PREV_FILTERS = "dept_prev_filters"
    DEPT_SELECTED_ID = "dept_selected_id"

    # ─── 廃棄申請 ───
    PREFILL_DISPOSAL_ITEM_ID = "prefill_disposal_item_id"
    PREFILL_DISPOSAL_QUANTITY = "prefill_disposal_quantity"
    PREFILL_DISPOSAL_REASON = "prefill_disposal_reason"
    LAST_DISPOSAL_SUCCESS = "last_disposal_success"
    LAST_DISPOSAL_REQUEST_HASH = "last_disposal_request_hash"

    # ─── 発注申請 ───
    PREFILL_PURCHASE_ITEM_ID = "prefill_purchase_item_id"
    PREFILL_PURCHASE_QUANTITY = "prefill_purchase_quantity"
    PREFILL_PURCHASE_REASON = "prefill_purchase_reason"
    PR_PREFILL_ITEM_ID = "pr_prefill_item_id"
    PR_PREFILL_QTY = "pr_prefill_qty"
    LAST_PURCHASE_REQUEST_SUCCESS = "last_purchase_request_success"
    PURCHASE_REQUEST_SUCCESS_DISPLAY = "purchase_request_success_display"
    LAST_PR_SUBMISSION = "last_pr_submission"

    # ─── 発注申請管理（ADMIN） ───
    PR_DEPT_FILTER = "pr_dept_filter"
    SELECTED_REQUEST_IDS = "selected_request_ids"
    SHOW_ORDER_CREATION = "show_order_creation"
    SHOW_HOLD_FORM = "show_hold_form"
    SHOW_REJECT_FORM = "show_reject_form"
    ORDER_CREATION_REQUEST_IDS = "order_creation_request_ids"
    ORDER_DRAFT_TEXT = "order_draft_text"
    ORDER_PAYLOADS = "order_payloads"
    PO_GENERATED = "po_generated"
    LAST_OUTPUT_CHANNEL = "last_output_channel"
    LAST_DOCUMENT_NAME = "last_document_name"
    ORDER_FINALIZED = "order_finalized"
    EMAIL_OUTPUT = "email_output"
    PDF_OUTPUT = "pdf_output"
    EXCEL_OUTPUT = "excel_output"

    # ─── CSV取り込み ───
    CSV_VALIDATION_DONE = "csv_validation_done"
    CSV_VALIDATION_RESULTS = "csv_validation_results"
    CSV_DATA = "csv_data"
    CSV_ERROR_COUNT = "csv_error_count"

    # ─── AIアシスタント ───
    AI_CHAT_HISTORY = "ai_chat_history"

    # ─── デモモード ───
    DEMO_RESET_CONFIRM = "demo_reset_confirm"

    # ─── 動的キー生成ヘルパー ───
    @staticmethod
    def confirm_undo_out(history_id: int) -> str:
        return f"confirm_undo_out_{history_id}"

    @staticmethod
    def confirm_undo_in(history_id: int) -> str:
        return f"confirm_undo_in_{history_id}"

    @staticmethod
    def confirm_cancel_pending(pending_id: int) -> str:
        return f"confirm_cancel_pending_{pending_id}"

    @staticmethod
    def processing_approval(pending_id: int) -> str:
        return f"processing_approval_{pending_id}"

    @staticmethod
    def processing_reject(pending_id: int) -> str:
        return f"processing_reject_{pending_id}"

    @staticmethod
    def show_reject(request_id: int) -> str:
        return f"show_reject_{request_id}"

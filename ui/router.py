"""
ルーターモジュール

メニューIDに基づいて適切なページ関数にルーティングする。
新規ページを追加する場合は PAGE_REGISTRY に1行追加するだけ。
"""

import streamlit as st

# (モジュールパス, 関数名) のマッピング
# 遅延インポートにより起動時間を短縮し、循環インポートを回避
PAGE_REGISTRY: dict[str, tuple[str, str]] = {
    "inventory":          ("ui.pages.inventory",                           "show_inventory_page"),
    "alert":              ("ui.pages.alert",                               "show_alert_page"),
    "purchase_request":   ("ui.pages.purchase_request",                    "show_purchase_request_page"),
    "disposal_request":   ("ui.pages.disposal_request",                    "show_disposal_request_page"),
    "inbound":            ("ui.pages.inbound",                             "show_inbound_page"),
    "outbound":           ("ui.pages.outbound",                            "show_outbound_page"),
    "history":            ("ui.pages.history",                             "show_history_page"),
    "stats":              ("ui.pages.statistics",                          "show_statistics_page"),
    "ai":                 ("ui.pages.ai_assistant",                        "show_ai_assistant_page"),
    "approval":           ("ui.pages.approval",                            "show_approval_page"),
    "disposal_approval":  ("ui.pages.disposal_approval",                   "show_disposal_approval_page"),
    "purchase_admin":     ("ui.pages.purchase_admin",                      "show_purchase_request_admin_page"),
    "adjust":             ("ui.pages.adjust",                              "show_adjust_page"),
    "item_master":        ("ui.pages.item_master",                         "show_item_master_management_page"),
    "vendor":             ("ui.pages.vendor",                              "show_vendor_management_page"),
    "users":              ("ui.pages.users",                               "show_user_management_page"),
    "departments":        ("ui.pages.departments",                         "show_department_management_page"),
    "maintenance":        ("ui.pages.maintenance",                         "show_maintenance_page"),
    "demo":               ("ui.pages.demo",                                "show_demo_mode_page"),
    "stocktake_sessions": ("ui.pages.stocktake.stocktake_sessions_page",   "show_stocktake_sessions_page"),
    "stocktake_entry":    ("ui.pages.stocktake.stocktake_entry_page",      "show_stocktake_entry_page"),
    "stocktake_review":   ("ui.pages.stocktake.stocktake_review_page",     "show_stocktake_review_page"),
    "stocktake_report":   ("ui.pages.stocktake.stocktake_report_page",     "show_stocktake_report_page"),
    "stocktake_admin":    ("ui.pages.stocktake.stocktake_admin_page",      "show_stocktake_admin_page"),
}


def route(menu_id: str):
    """メニューIDに対応するページを表示する。"""
    entry = PAGE_REGISTRY.get(menu_id)
    if entry:
        import importlib
        module_path, func_name = entry
        module = importlib.import_module(module_path)
        getattr(module, func_name)()
    else:
        st.info(f"機能 {menu_id} は実装準備中です")

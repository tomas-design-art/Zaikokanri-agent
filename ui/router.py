"""
ルーターモジュール

メニューIDに基づいて適切なページ関数にルーティングする。
"""

import streamlit as st


def route(menu_id: str):
    """
    メニューIDに対応するページを表示する。
    
    遅延インポートを使用してページモジュールを読み込むことで、
    起動時間を短縮し、循環インポートを回避する。
    """
    if menu_id == "inventory":
        from ui.pages.inventory import show_inventory_page
        show_inventory_page()
    elif menu_id == "alert":
        from ui.pages.alert import show_alert_page
        show_alert_page()
    elif menu_id == "purchase_request":
        from ui.pages.purchase_request import show_purchase_request_page
        show_purchase_request_page()
    elif menu_id == "disposal_request":
        from ui.pages.disposal_request import show_disposal_request_page
        show_disposal_request_page()
    elif menu_id == "inbound":
        from ui.pages.inbound import show_inbound_page
        show_inbound_page()
    elif menu_id == "outbound":
        from ui.pages.outbound import show_outbound_page
        show_outbound_page()
    elif menu_id == "history":
        from ui.pages.history import show_history_page
        show_history_page()
    elif menu_id == "stats":
        from ui.pages.statistics import show_statistics_page
        show_statistics_page()
    elif menu_id == "ai":
        from ui.pages.ai_assistant import show_ai_assistant_page
        show_ai_assistant_page()
    elif menu_id == "approval":
        from ui.pages.approval import show_approval_page
        show_approval_page()
    elif menu_id == "disposal_approval":
        from ui.pages.disposal_approval import show_disposal_approval_page
        show_disposal_approval_page()
    elif menu_id == "purchase_admin":
        from ui.pages.purchase_admin import show_purchase_request_admin_page
        show_purchase_request_admin_page()
    elif menu_id == "adjust":
        from ui.pages.adjust import show_adjust_page
        show_adjust_page()
    elif menu_id == "item_master":
        from ui.pages.item_master import show_item_master_management_page
        show_item_master_management_page()
    elif menu_id == "vendor":
        from ui.pages.vendor import show_vendor_management_page
        show_vendor_management_page()
    elif menu_id == "users":
        from ui.pages.users import show_user_management_page
        show_user_management_page()
    elif menu_id == "departments":
        from ui.pages.departments import show_department_management_page
        show_department_management_page()
    elif menu_id == "maintenance":
        from ui.pages.maintenance import show_maintenance_page
        show_maintenance_page()
    elif menu_id == "demo":
        from ui.pages.demo import show_demo_mode_page
        show_demo_mode_page()
    else:
        st.info(f"機能 {menu_id} は実装準備中です")

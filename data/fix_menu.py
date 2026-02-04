import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# メニュー追加箇所（文字化け修正と業者管理追加）
old_menu = """            if is_admin():
                menu_options.append("� 物品マスター管理")
                menu_options.append("�👥 ユーザー管理")
                menu_options.append("🏢 部署管理")"""

new_menu = """            if is_admin():
                menu_options.append("📦 物品マスター管理")
                menu_options.append("🏢 業者管理")
                menu_options.append("👥 ユーザー管理")
                menu_options.append("🏢 部署管理")"""

content = content.replace(old_menu, new_menu)

# メニュー分岐箇所（文字化け修正と業者管理追加）
old_routing = """    elif menu == "� 物品マスター管理":
        show_item_master_management_page()
    elif menu == "�👥 ユーザー管理":
        show_user_management_page()"""

new_routing = """    elif menu == "📦 物品マスター管理":
        show_item_master_management_page()
    elif menu == "🏢 業者管理":
        show_vendor_management_page()
    elif menu == "👥 ユーザー管理":
        show_user_management_page()"""

content = content.replace(old_routing, new_routing)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ メニューに業者管理を追加し、文字化けを修正しました')

"""物品マスター管理ページ"""

import streamlit as st
import pandas as pd

from utils.auth import require_role
from utils.validation import (
    validate_required_text, to_float_safe, needs_correction_warning
)
from repositories.item_repo import (
    list_items, count_items, get_item_master_by_id,
    insert_item, update_item, deactivate_item, activate_item
)
from repositories.category_repo import get_category_names, list_categories, insert_category
from repositories.vendor_repo import (
    get_vendor_names, get_vendor_by_name, insert_vendor
)
from repositories.department_repo import get_all_departments
from ui.components.refresh_button import show_refresh_button
from csv_import_helper import (
    generate_sample_csv, validate_csv_row, check_duplicate, prepare_import_data
)


def show_item_master_management_page():
    """物品マスター管理ページ（管理者専用）- 表形式表示"""
    st.header("📦 物品マスター管理")
    
    # 更新ボタン
    show_refresh_button()
    
    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "物品管理は管理者のみ使用できます"):
        return
    
    # セクション切替（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["📋 物品一覧", "➕ 新規登録", "🏷️ カテゴリ管理", "📥 CSV取り込み"],
        horizontal=True,
        key="item_master_section",
    )

    if section == "📋 物品一覧":
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
                    "棚卸対象": "✅" if item.get('is_inventory_target', 1) else "⬜",
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
                    inv_target = item.get('is_inventory_target', 1)
                    st.write(f"**棚卸し対象:** {'✅ 対象' if inv_target else '⬜ 対象外'}")
                    
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
    
    if section == "➕ 新規登録":
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
    
    if section == "🏷️ カテゴリ管理":
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
                
                # 棚卸し対象フラグ
                is_inventory_target = st.checkbox(
                    "📋 棚卸し対象",
                    value=bool(item.get('is_inventory_target', 1)),
                    key=f"inv_target_edit_{item_id}",
                    help="チェックを外すと棚卸しセッションの対象から除外されます"
                )
                
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
                            is_common=1 if is_common else 0,
                            is_inventory_target=1 if is_inventory_target else 0
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
    
    if section == "📥 CSV取り込み":
        # === CSV取り込み ===
        show_csv_import_tab()


def show_csv_import_tab():
    """CSV取り込みタブの内容"""
    import io
    
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

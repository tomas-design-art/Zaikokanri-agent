"""
棚卸し管理ページ

テンプレート管理・フィールドマッピング設定を提供する。
"""

import streamlit as st
from state.keys import K
from utils.auth import get_current_user, is_admin
from services.stocktake_service import (
    get_stocktake_templates,
    get_stocktake_template_by_id,
    create_stocktake_template,
    update_stocktake_template,
    set_template_mappings,
    get_template_mappings,
)


# デフォルトのフィールド候補
DEFAULT_FIELDS = [
    {"field_name": "item_code", "display_label": "品番"},
    {"field_name": "item_name", "display_label": "物品名"},
    {"field_name": "category", "display_label": "カテゴリ"},
    {"field_name": "department_tags", "display_label": "部署"},
    {"field_name": "location_text", "display_label": "保管場所"},
    {"field_name": "system_qty", "display_label": "システム数量"},
    {"field_name": "actual_qty", "display_label": "実数量"},
    {"field_name": "diff_qty", "display_label": "差異"},
    {"field_name": "unit_price", "display_label": "単価"},
    {"field_name": "diff_amount", "display_label": "差異金額"},
    {"field_name": "counted_by_name", "display_label": "入力者"},
    {"field_name": "counted_at", "display_label": "入力日時"},
    {"field_name": "verified_by_name", "display_label": "確認者"},
    {"field_name": "approved_by_name", "display_label": "承認者"},
    {"field_name": "note", "display_label": "備考"},
    {"field_name": "status", "display_label": "ステータス"},
]


def show_stocktake_admin_page():
    """棚卸し管理ページ"""
    st.header("⚙️ 棚卸し管理")
    
    user = get_current_user()
    if not user or not is_admin():
        st.warning("この機能は管理者のみ利用できます")
        return
    
    if K.STOCKTAKE_SUCCESS_MSG in st.session_state:
        st.success(st.session_state.pop(K.STOCKTAKE_SUCCESS_MSG))
    if K.STOCKTAKE_ERROR_MSG in st.session_state:
        st.error(st.session_state.pop(K.STOCKTAKE_ERROR_MSG))
    
    section = st.radio(
        "表示セクション",
        options=["📋 テンプレート一覧", "➕ 新規テンプレート作成"],
        horizontal=True,
        key="stocktake_admin_section",
    )

    if section == "📋 テンプレート一覧":
        _render_template_list()
    else:
        _render_create_template()


def _render_template_list():
    """テンプレート一覧と編集"""
    templates = get_stocktake_templates(active_only=False)
    
    if not templates:
        st.info("テンプレートがありません。「新規テンプレート作成」タブから作成してください。")
        return
    
    for tmpl in templates:
        tmpl_id = tmpl["id"]
        status = "🟢 有効" if tmpl.get("is_active") else "🔴 無効"
        
        with st.expander(f"{tmpl['name']} ({tmpl.get('file_type', 'excel')}) - {status}"):
            st.write(f"**説明:** {tmpl.get('description', '-')}")
            st.write(f"**作成日:** {tmpl.get('created_at', '-')}")
            
            # マッピング表示
            mappings = get_template_mappings(tmpl_id)
            if mappings:
                st.write("**フィールドマッピング:**")
                for m in mappings:
                    st.write(f"  - `{m['field_name']}` ({m.get('display_label', '')}) → セル `{m['excel_cell']}`")
            else:
                st.caption("マッピング未設定")
            
            st.divider()
            
            # マッピング編集
            st.write("**マッピング設定:**")
            st.caption("フィールドとExcelセル位置の対応を設定します")
            
            with st.form(f"mapping_form_{tmpl_id}"):
                new_mappings = []
                
                # 既存マッピングまたはデフォルトを表示
                fields_to_show = mappings if mappings else DEFAULT_FIELDS[:8]
                
                for i, field_info in enumerate(fields_to_show):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        if mappings:
                            field_name = st.text_input(
                                "フィールド名", value=field_info.get("field_name", ""),
                                key=f"fn_{tmpl_id}_{i}"
                            )
                        else:
                            field_name = st.selectbox(
                                "フィールド",
                                [f["field_name"] for f in DEFAULT_FIELDS],
                                index=min(i, len(DEFAULT_FIELDS) - 1),
                                format_func=lambda x: next(
                                    (f["display_label"] for f in DEFAULT_FIELDS if f["field_name"] == x), x
                                ),
                                key=f"fn_{tmpl_id}_{i}"
                            )
                    with col2:
                        excel_cell = st.text_input(
                            "Excelセル", value=field_info.get("excel_cell", f"A{i+1}"),
                            key=f"ec_{tmpl_id}_{i}",
                            help="例: A1, B2, C3"
                        )
                    with col3:
                        label = st.text_input(
                            "表示名", value=field_info.get("display_label", ""),
                            key=f"dl_{tmpl_id}_{i}"
                        )
                    
                    if field_name and excel_cell:
                        new_mappings.append({
                            "field_name": field_name,
                            "excel_cell": excel_cell,
                            "display_label": label,
                        })
                
                if st.form_submit_button("💾 マッピング保存", use_container_width=True):
                    result = set_template_mappings(tmpl_id, new_mappings)
                    if result.get("success"):
                        st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                    else:
                        st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                    st.rerun()
            
            # 有効/無効切替
            col1, col2 = st.columns(2)
            with col1:
                new_active = 0 if tmpl.get("is_active") else 1
                label = "🔴 無効にする" if tmpl.get("is_active") else "🟢 有効にする"
                if st.button(label, key=f"toggle_{tmpl_id}"):
                    result = update_stocktake_template(tmpl_id, is_active=new_active)
                    if result.get("success"):
                        st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                    else:
                        st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                    st.rerun()


def _render_create_template():
    """テンプレート新規作成"""
    st.subheader("テンプレート新規作成")
    st.caption("法人フォーマットに合わせたExcel出力テンプレートを作成します")
    
    with st.form("create_template_form"):
        name = st.text_input("テンプレート名 *", placeholder="例: 本社棚卸しフォーマット")
        description = st.text_area("説明", height=80)
        file_type = st.selectbox("ファイル種別", ["excel"])
        
        submitted = st.form_submit_button("➕ 作成", type="primary",
                                           use_container_width=True)
    
    if submitted:
        if not name.strip():
            st.error("❌ テンプレート名は必須です")
            return
        
        result = create_stocktake_template(name.strip(), description.strip(), file_type)
        if result.get("success"):
            st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
            st.rerun()
        else:
            st.error(result.get("message", "エラーが発生しました"))

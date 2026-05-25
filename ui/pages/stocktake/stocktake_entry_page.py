"""
棚卸し入力ページ

現場スタッフが実数を入力するページ。
カテゴリ・部署・キーワードでフィルタリング可能。
"""

import streamlit as st
import pandas as pd
from state.keys import K
from utils.auth import get_current_user
from services.stocktake_service import (
    get_stocktake_sessions,
    get_stocktake_session_by_id,
    get_stocktake_records,
    get_session_progress,
    record_count,
)
from repositories.inventory_query import get_categories


def show_stocktake_entry_page():
    """棚卸し入力ページ"""
    st.header("📝 棚卸し入力")
    
    user = get_current_user()
    if not user:
        st.warning("ログインしてください")
        return
    
    # 成功・エラーメッセージ
    if K.STOCKTAKE_SUCCESS_MSG in st.session_state:
        st.success(st.session_state.pop(K.STOCKTAKE_SUCCESS_MSG))
    if K.STOCKTAKE_ERROR_MSG in st.session_state:
        st.error(st.session_state.pop(K.STOCKTAKE_ERROR_MSG))
    
    # セッション選択
    session_id = _select_session()
    if not session_id:
        return
    
    session = get_stocktake_session_by_id(session_id)
    if not session:
        st.error("セッションが見つかりません")
        return
    
    if session["status"] != "OPEN":
        st.warning("🔒 このセッションはクローズ済みです（閲覧のみ）")
    
    # 進捗表示
    progress = get_session_progress(session_id)
    _render_progress_bar(progress)
    
    st.divider()
    
    # フィルター
    records = _get_filtered_records(session_id)
    
    if not records:
        st.info("表示する記録がありません")
        return
    
    # 入力モード切替
    input_mode = st.radio(
        "入力方式", ["個別入力", "一括入力"],
        horizontal=True, key="stocktake_input_mode"
    )
    
    if input_mode == "個別入力":
        _render_individual_entry(records, user, session["status"] == "OPEN")
    else:
        _render_bulk_entry(records, user, session["status"] == "OPEN")


def _select_session() -> int:
    """OPENセッションを選択"""
    # セッション選択済みの場合
    stored_id = st.session_state.get(K.STOCKTAKE_SESSION)
    
    open_sessions = get_stocktake_sessions(status="OPEN")
    closed_sessions = get_stocktake_sessions(status="CLOSED")
    all_sessions = open_sessions + closed_sessions
    
    if not all_sessions:
        st.info("棚卸しセッションがありません。セッション管理画面で作成してください。")
        return None
    
    session_options = {s["id"]: f"{s['name']} ({s['start_date']}) [{s['status']}]" 
                       for s in all_sessions}
    
    # デフォルトインデックス
    session_ids = list(session_options.keys())
    default_idx = 0
    if stored_id and stored_id in session_ids:
        default_idx = session_ids.index(stored_id)
    
    selected_id = st.selectbox(
        "棚卸しセッション",
        options=session_ids,
        format_func=lambda x: session_options[x],
        index=default_idx,
        key="stocktake_session_select"
    )
    
    st.session_state[K.STOCKTAKE_SESSION] = selected_id
    return selected_id


def _render_progress_bar(progress: dict):
    """進捗バーを表示"""
    cols = st.columns([3, 1, 1, 1, 1])
    with cols[0]:
        pct = progress.get("progress_pct", 0)
        st.progress(pct / 100, text=f"入力進捗: {pct}% ({progress.get('total_items', 0) - progress.get('pending_count', 0)}/{progress.get('total_items', 0)})")
    with cols[1]:
        st.metric("未入力", progress.get("pending_count", 0))
    with cols[2]:
        st.metric("入力済", progress.get("counted_count", 0))
    with cols[3]:
        st.metric("差異あり", progress.get("diff_count", 0))
    with cols[4]:
        st.metric("承認済", progress.get("approved_count", 0))


def _get_filtered_records(session_id: int) -> list:
    """フィルタリングされた記録を取得"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        status_opts = ["すべて", "PENDING", "COUNTED", "VERIFIED", "APPROVED", "APPLIED"]
        status_labels = {
            "すべて": "すべて", "PENDING": "⬜ 未入力",
            "COUNTED": "✏️ 入力済", "VERIFIED": "✅ 確認済",
            "APPROVED": "👑 承認済", "APPLIED": "🔄 反映済"
        }
        status = st.selectbox(
            "ステータス", status_opts,
            format_func=lambda x: status_labels.get(x, x),
            key=K.STOCKTAKE_FILTER_STATUS
        )
    
    with col2:
        categories = get_categories()
        cat_options = ["すべて"] + categories
        category = st.selectbox("カテゴリ", cat_options, key=K.STOCKTAKE_FILTER_CATEGORY)
    
    with col3:
        department = st.text_input("部署フィルター", key=K.STOCKTAKE_FILTER_DEPARTMENT)
    
    with col4:
        search = st.text_input("🔍 検索", key=K.STOCKTAKE_FILTER_SEARCH,
                               placeholder="物品名・品番")
    
    return get_stocktake_records(
        session_id,
        status=status if status != "すべて" else None,
        category=category if category != "すべて" else None,
        department=department if department else None,
        search=search if search else None,
    )


def _render_individual_entry(records: list, user: dict, is_editable: bool):
    """個別入力モード"""
    st.caption(f"📦 {len(records)}件表示中")
    
    for rec in records:
        rec_id = rec["id"]
        status_emoji = {
            "PENDING": "⬜", "COUNTED": "✏️",
            "VERIFIED": "✅", "APPROVED": "👑", "APPLIED": "🔄"
        }.get(rec["status"], "❓")
        
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1, 2, 1])
            
            with cols[0]:
                code_str = f"[{rec.get('item_code', '')}] " if rec.get('item_code') else ""
                st.write(f"**{code_str}{rec['item_name']}**")
                st.caption(f"{rec.get('category', '')} / {rec.get('department_tags', '') or '-'}")
            
            with cols[1]:
                st.metric("システム", rec["system_qty"])
            
            with cols[2]:
                if rec.get("actual_qty") is not None:
                    st.metric("実数", rec["actual_qty"])
                else:
                    st.write("実数: **未入力**")
            
            with cols[3]:
                diff = rec.get("diff_qty", 0)
                if rec.get("actual_qty") is not None:
                    if diff > 0:
                        st.metric("差異", f"+{diff}", delta=diff, delta_color="inverse")
                    elif diff < 0:
                        st.metric("差異", str(diff), delta=diff, delta_color="inverse")
                    else:
                        st.metric("差異", "0")
                else:
                    st.write("差異: -")
            
            with cols[4]:
                if is_editable and rec["status"] in ("PENDING", "COUNTED"):
                    actual = st.number_input(
                        "実数入力",
                        min_value=0,
                        value=rec.get("actual_qty") or rec["system_qty"],
                        key=f"actual_{rec_id}",
                        label_visibility="collapsed"
                    )
                    note = st.text_input(
                        "備考", value=rec.get("note") or "",
                        key=f"note_{rec_id}",
                        label_visibility="collapsed",
                        placeholder="備考"
                    )
                else:
                    st.write(f"{status_emoji} {rec['status']}")
                    if rec.get("note"):
                        st.caption(rec["note"])
            
            with cols[5]:
                if is_editable and rec["status"] in ("PENDING", "COUNTED"):
                    if st.button("✅ 記録", key=f"save_{rec_id}"):
                        actual_val = st.session_state.get(f"actual_{rec_id}", rec["system_qty"])
                        note_val = st.session_state.get(f"note_{rec_id}", "")
                        result = record_count(
                            rec_id, actual_val, user["id"], note_val
                        )
                        if result.get("success"):
                            st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                        else:
                            st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                        st.rerun()
                elif rec.get("counted_by_name"):
                    st.caption(f"by {rec['counted_by_name']}")


def _render_bulk_entry(records: list, user: dict, is_editable: bool):
    """一括入力モード（テーブル形式）"""
    pending_records = [r for r in records if r["status"] in ("PENDING", "COUNTED")]
    
    if not pending_records and is_editable:
        st.success("全ての物品が入力済みです")
    
    # 表示用DataFrame
    display_data = []
    for rec in records:
        actual = rec.get("actual_qty")
        diff = rec.get("diff_qty", 0)
        display_data.append({
            "ID": rec["id"],
            "品番": rec.get("item_code", "-"),
            "物品名": rec["item_name"],
            "カテゴリ": rec.get("category", ""),
            "システム数": rec["system_qty"],
            "実数": actual if actual is not None else "",
            "差異": diff if actual is not None else "",
            "状態": rec["status"],
            "入力者": rec.get("counted_by_name", ""),
        })
    
    if display_data:
        df = pd.DataFrame(display_data)
        st.dataframe(df, use_container_width=True, hide_index=True,
                      column_config={
                          "ID": st.column_config.NumberColumn(width="small"),
                          "差異": st.column_config.NumberColumn(
                              help="+ は過剰、- は不足"
                          ),
                      })
    
    # 一括入力フォーム
    if is_editable and pending_records:
        st.subheader("一括入力")
        st.caption("⬇️ 未入力の物品について実数を入力してください")
        
        with st.form("bulk_entry_form"):
            entries = []
            for rec in pending_records[:50]:  # 最大50件
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"{rec.get('item_code', '')} - {rec['item_name']}")
                with col2:
                    st.write(f"システム: {rec['system_qty']}")
                with col3:
                    actual = st.number_input(
                        "実数", min_value=0,
                        value=rec["system_qty"],
                        key=f"bulk_{rec['id']}",
                        label_visibility="collapsed"
                    )
                entries.append((rec["id"], actual))
            
            if st.form_submit_button("📤 一括記録", type="primary",
                                      use_container_width=True):
                success_count = 0
                for rec_id, actual_val in entries:
                    result = record_count(rec_id, actual_val, user["id"])
                    if result.get("success"):
                        success_count += 1
                
                st.session_state[K.STOCKTAKE_SUCCESS_MSG] = f"✅ {success_count}件を記録しました"
                st.rerun()

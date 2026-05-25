"""
棚卸し確認・承認ページ

総務確認 → 上長承認 のワークフローを提供する。
"""

import streamlit as st
from state.keys import K
from utils.auth import get_current_user, is_admin
from services.stocktake_service import (
    get_stocktake_sessions,
    get_stocktake_session_by_id,
    get_stocktake_records,
    get_session_progress,
    verify_item,
    approve_item,
    batch_verify,
    batch_approve,
    close_session,
    apply_stocktake_adjustments,
)
from repositories.stocktake_repo import apply_stocktake_adjustments as repo_apply


def show_stocktake_review_page():
    """棚卸し確認・承認ページ"""
    st.header("✅ 棚卸し確認・承認")
    
    user = get_current_user()
    if not user:
        st.warning("ログインしてください")
        return
    
    if K.STOCKTAKE_SUCCESS_MSG in st.session_state:
        st.success(st.session_state.pop(K.STOCKTAKE_SUCCESS_MSG))
    if K.STOCKTAKE_ERROR_MSG in st.session_state:
        st.error(st.session_state.pop(K.STOCKTAKE_ERROR_MSG))
    
    # セッション選択
    session_id = _select_open_session()
    if not session_id:
        return
    
    session = get_stocktake_session_by_id(session_id)
    if not session:
        st.error("セッションが見つかりません")
        return
    
    # 進捗
    progress = get_session_progress(session_id)
    _render_review_summary(progress)
    
    st.divider()

    section = st.radio(
        "作業セクション",
        options=[
            "✏️ 総務確認（COUNTED→VERIFIED）",
            "👑 上長承認（VERIFIED→APPROVED）",
            "🔄 在庫反映",
        ],
        horizontal=True,
        key="stocktake_review_section",
    )

    if section == "✏️ 総務確認（COUNTED→VERIFIED）":
        _render_verify_tab(session_id, user)
    elif section == "👑 上長承認（VERIFIED→APPROVED）":
        _render_approve_tab(session_id, user)
    else:
        if is_admin():
            _render_apply_tab(session_id, session, user)
        else:
            st.info("在庫反映は管理者のみ実行できます")


def _select_open_session() -> int:
    """セッション選択"""
    stored = st.session_state.get(K.STOCKTAKE_SESSION)
    sessions = get_stocktake_sessions()
    
    if not sessions:
        st.info("棚卸しセッションがありません")
        return None
    
    opts = {s["id"]: f"{s['name']} ({s['start_date']}) [{s['status']}]" for s in sessions}
    ids = list(opts.keys())
    
    default_idx = 0
    if stored and stored in ids:
        default_idx = ids.index(stored)
    
    selected = st.selectbox("セッション", ids,
                             format_func=lambda x: opts[x],
                             index=default_idx,
                             key="review_session_select")
    st.session_state[K.STOCKTAKE_SESSION] = selected
    return selected


def _render_review_summary(progress: dict):
    """確認・承認の進捗サマリー"""
    cols = st.columns(6)
    labels = [("未入力", "pending_count"), ("入力済", "counted_count"),
              ("確認済", "verified_count"), ("承認済", "approved_count"),
              ("反映済", "applied_count"), ("差異あり", "diff_count")]
    for col, (label, key) in zip(cols, labels):
        with col:
            st.metric(label, progress.get(key, 0))


def _render_verify_tab(session_id: int, user: dict):
    """総務確認タブ"""
    st.subheader("入力済み → 確認済みへ")
    st.caption("現場入力された記録を総務が確認します")
    
    records = get_stocktake_records(session_id, status="COUNTED")
    
    if not records:
        st.success("確認待ちの記録はありません")
        return
    
    st.write(f"📋 {len(records)}件の確認待ち")
    
    # 一括確認
    selected_ids = []
    select_all = st.checkbox("全件選択", key="verify_select_all")
    
    for rec in records:
        rec_id = rec["id"]
        diff = rec.get("diff_qty", 0)
        diff_str = f"差異: +{diff}" if diff > 0 else f"差異: {diff}" if diff < 0 else "差異なし"
        
        with st.container(border=True):
            cols = st.columns([0.5, 3, 1, 1, 1, 1])
            
            with cols[0]:
                checked = st.checkbox("", value=select_all, key=f"vcheck_{rec_id}",
                                      label_visibility="collapsed")
                if checked:
                    selected_ids.append(rec_id)
            
            with cols[1]:
                code = f"[{rec.get('item_code', '')}] " if rec.get("item_code") else ""
                st.write(f"**{code}{rec['item_name']}**")
                st.caption(f"{rec.get('category', '')} / 入力者: {rec.get('counted_by_name', '-')}")
            
            with cols[2]:
                st.metric("システム", rec["system_qty"])
            
            with cols[3]:
                st.metric("実数", rec.get("actual_qty", "-"))
            
            with cols[4]:
                if diff != 0:
                    color = "🟢" if diff > 0 else "🔴"
                    st.write(f"{color} {diff_str}")
                else:
                    st.write("✅ 一致")
            
            with cols[5]:
                if st.button("✅ 確認", key=f"verify_{rec_id}"):
                    result = verify_item(rec_id, user["id"])
                    if result.get("success"):
                        st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                    else:
                        st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                    st.rerun()
            
            if rec.get("note"):
                st.caption(f"📝 {rec['note']}")
    
    # 一括確認ボタン
    if selected_ids:
        if st.button(f"✅ 選択した{len(selected_ids)}件を一括確認",
                      type="primary", use_container_width=True):
            result = batch_verify(selected_ids, user["id"])
            if result.get("success"):
                st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
            else:
                st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
            st.rerun()


def _render_approve_tab(session_id: int, user: dict):
    """上長承認タブ"""
    st.subheader("確認済み → 承認済みへ")
    st.caption("総務確認された記録を上長が承認します")
    
    if not is_admin():
        st.warning("承認は管理者のみ実行できます")
    
    records = get_stocktake_records(session_id, status="VERIFIED")
    
    if not records:
        st.success("承認待ちの記録はありません")
        return
    
    st.write(f"📋 {len(records)}件の承認待ち")
    
    selected_ids = []
    select_all = st.checkbox("全件選択", key="approve_select_all")
    
    for rec in records:
        rec_id = rec["id"]
        diff = rec.get("diff_qty", 0)
        
        with st.container(border=True):
            cols = st.columns([0.5, 3, 1, 1, 1, 1])
            
            with cols[0]:
                checked = st.checkbox("", value=select_all, key=f"acheck_{rec_id}",
                                      label_visibility="collapsed")
                if checked:
                    selected_ids.append(rec_id)
            
            with cols[1]:
                code = f"[{rec.get('item_code', '')}] " if rec.get("item_code") else ""
                st.write(f"**{code}{rec['item_name']}**")
                st.caption(f"確認者: {rec.get('verified_by_name', '-')} / "
                          f"入力者: {rec.get('counted_by_name', '-')}")
            
            with cols[2]:
                st.metric("システム", rec["system_qty"])
            
            with cols[3]:
                st.metric("実数", rec.get("actual_qty", "-"))
            
            with cols[4]:
                if diff != 0:
                    color = "🟢" if diff > 0 else "🔴"
                    st.write(f"{color} 差異: {'+' if diff > 0 else ''}{diff}")
                else:
                    st.write("✅ 一致")
            
            with cols[5]:
                if is_admin():
                    if st.button("👑 承認", key=f"approve_{rec_id}"):
                        result = approve_item(rec_id, user["id"])
                        if result.get("success"):
                            st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                        else:
                            st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                        st.rerun()
    
    if selected_ids and is_admin():
        if st.button(f"👑 選択した{len(selected_ids)}件を一括承認",
                      type="primary", use_container_width=True):
            result = batch_approve(selected_ids, user["id"])
            if result.get("success"):
                st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
            else:
                st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
            st.rerun()


def _render_apply_tab(session_id: int, session: dict, user: dict):
    """在庫反映タブ"""
    st.subheader("承認済み → 在庫反映")
    st.caption("承認済みの差異を在庫に反映し、在庫調整履歴を記録します")
    
    progress = get_session_progress(session_id)
    approved = progress.get("approved_count", 0)
    
    if approved == 0:
        st.info("反映対象の承認済み記録がありません")
        return
    
    # 差異ありの承認済み記録を表示
    records = get_stocktake_records(session_id, status="APPROVED")
    diff_records = [r for r in records if r.get("diff_qty", 0) != 0]
    
    if diff_records:
        st.warning(f"⚠️ {len(diff_records)}件の差異ありの承認済み記録があります")
        
        for rec in diff_records:
            diff = rec["diff_qty"]
            st.write(
                f"- {rec.get('item_code', '')} {rec['item_name']}: "
                f"{rec['system_qty']} → {rec['actual_qty']} "
                f"（差異: {'+'if diff > 0 else ''}{diff}）"
            )
    else:
        st.success("差異のある承認済み記録はありません（全て一致）")
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 在庫に反映", type="primary", use_container_width=True):
            from repositories.stocktake_repo import apply_stocktake_adjustments
            result = apply_stocktake_adjustments(
                session_id,
                user.get("display_name", ""),
                user.get("department", "")
            )
            if result.get("success"):
                st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
            else:
                st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
            st.rerun()
    
    with col2:
        if session["status"] == "OPEN":
            if st.button("🔒 セッション終了 + 反映", type="secondary",
                          use_container_width=True):
                result = close_session(
                    session_id,
                    user.get("display_name", ""),
                    user.get("department", "")
                )
                if result.get("success"):
                    st.session_state[K.STOCKTAKE_SUCCESS_MSG] = result["message"]
                else:
                    st.session_state[K.STOCKTAKE_ERROR_MSG] = result["message"]
                st.rerun()

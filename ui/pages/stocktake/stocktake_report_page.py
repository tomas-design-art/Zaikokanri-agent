"""
棚卸しレポートページ

HTML報告書の表示とExcelダウンロードを提供する。
"""

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from utils.date_utils import JST
from state.keys import K
from utils.auth import get_current_user
from services.stocktake_service import (
    get_stocktake_sessions,
    get_stocktake_session_by_id,
    get_session_progress,
    get_stocktake_summary,
    get_stocktake_diff_records,
    generate_stocktake_html_report,
    generate_stocktake_excel_data,
)
from renderers.stocktake_renderer import render_stocktake_excel


def show_stocktake_report_page():
    """棚卸しレポートページ"""
    st.header("📊 棚卸しレポート")
    
    user = get_current_user()
    if not user:
        st.warning("ログインしてください")
        return
    
    # セッション選択
    sessions = get_stocktake_sessions()
    if not sessions:
        st.info("棚卸しセッションがありません")
        return
    
    stored = st.session_state.get(K.STOCKTAKE_SESSION)
    opts = {s["id"]: f"{s['name']} ({s['start_date']}) [{s['status']}]" for s in sessions}
    ids = list(opts.keys())
    
    default_idx = 0
    if stored and stored in ids:
        default_idx = ids.index(stored)
    
    session_id = st.selectbox("セッション", ids,
                               format_func=lambda x: opts[x],
                               index=default_idx,
                               key="report_session_select")
    
    session = get_stocktake_session_by_id(session_id)
    if not session:
        st.error("セッションが見つかりません")
        return
    
    # サマリー概要
    progress = get_session_progress(session_id)
    summary = get_stocktake_summary(session_id)
    
    st.divider()
    
    # サマリーカード
    cols = st.columns(4)
    with cols[0]:
        st.metric("対象品目", summary.get("total_items", 0))
    with cols[1]:
        st.metric("差異あり", summary.get("diff_count", 0))
    with cols[2]:
        st.metric("過剰合計", f"+{summary.get('total_surplus', 0)}")
    with cols[3]:
        st.metric("不足合計", f"-{summary.get('total_shortage', 0)}")
    
    pct = progress.get("completion_pct", 0)
    st.progress(pct / 100, text=f"完了率: {pct}%")
    
    st.divider()
    
    section = st.radio(
        "表示セクション",
        options=["📊 差異サマリー", "📄 HTML報告書", "📥 Excel出力"],
        horizontal=True,
        key="stocktake_report_section",
    )

    if section == "📊 差異サマリー":
        _render_diff_summary(session_id)
    elif section == "📄 HTML報告書":
        _render_html_report(session_id)
    else:
        _render_excel_download(session_id, session, summary)


def _render_diff_summary(session_id: int):
    """差異サマリー"""
    diff_records = get_stocktake_diff_records(session_id)
    
    if not diff_records:
        st.success("✅ 差異のある物品はありません")
        return
    
    st.subheader(f"⚠️ 差異一覧 ({len(diff_records)}件)")
    
    # カテゴリ別集計
    cat_summary = {}
    for rec in diff_records:
        cat = rec.get("category", "未分類")
        if cat not in cat_summary:
            cat_summary[cat] = {"surplus": 0, "shortage": 0, "count": 0}
        cat_summary[cat]["count"] += 1
        diff = rec.get("diff_qty", 0)
        if diff > 0:
            cat_summary[cat]["surplus"] += diff
        else:
            cat_summary[cat]["shortage"] += abs(diff)
    
    st.write("**カテゴリ別集計:**")
    for cat, data in cat_summary.items():
        st.write(f"- **{cat}**: {data['count']}件 (過剰: +{data['surplus']}, 不足: -{data['shortage']})")
    
    st.divider()
    
    # 詳細テーブル
    import pandas as pd
    rows = []
    for rec in diff_records:
        diff = rec.get("diff_qty", 0)
        price = rec.get("unit_price", 0) or 0
        rows.append({
            "品番": rec.get("item_code", "-"),
            "物品名": rec.get("item_name", ""),
            "カテゴリ": rec.get("category", ""),
            "システム数": rec.get("system_qty", 0),
            "実数": rec.get("actual_qty", ""),
            "差異": diff,
            "金額差異": f"¥{diff * price:,.0f}" if price else "-",
            "状態": rec.get("status", ""),
            "入力者": rec.get("counted_by_name", "-"),
            "備考": rec.get("note", "") or "",
        })
    
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_html_report(session_id: int):
    """HTML報告書プレビュー"""
    st.subheader("📄 HTML報告書")
    st.caption("ブラウザの印刷機能でPDF化できます")
    
    html = generate_stocktake_html_report(session_id)
    components.html(html, height=800, scrolling=True)


def _render_excel_download(session_id: int, session: dict, summary: dict):
    """Excelダウンロード"""
    st.subheader("📥 Excel出力")
    
    data_rows = generate_stocktake_excel_data(session_id)
    
    if not data_rows:
        st.info("出力するデータがありません")
        return
    
    st.write(f"📦 {len(data_rows)}件のデータを出力します")
    
    # Excel生成
    excel_bytes = render_stocktake_excel(data_rows, session, summary)
    
    now_str = datetime.now(JST).strftime('%Y%m%d_%H%M%S')
    file_name = f"棚卸し_{session.get('name', '')}_{now_str}.xlsx"
    
    st.download_button(
        "📥 Excelダウンロード",
        data=excel_bytes,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

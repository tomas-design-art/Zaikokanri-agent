"""
棚卸しサービス

棚卸しセッション管理・記録操作・レポート生成の
ビジネスロジックを提供する。
"""

from datetime import datetime
from utils.date_utils import JST
from utils.exceptions import ValidationError, BusinessRuleError, NotFoundError, ng  # noqa: F401
from repositories.stocktake_repo import (
    create_stocktake_session,
    get_stocktake_sessions,
    get_stocktake_session_by_id,
    update_stocktake_session_status,
    initialize_stocktake_records,
    get_stocktake_records,
    update_stocktake_record_count,
    verify_stocktake_record,
    approve_stocktake_record,
    batch_verify_stocktake_records,
    batch_approve_stocktake_records,
    apply_stocktake_adjustments,
    get_stocktake_summary,
    get_stocktake_diff_records,
    create_stocktake_template,
    get_stocktake_templates,
    get_stocktake_template_by_id,
    update_stocktake_template,
    set_template_mappings,
    get_template_mappings,
    delete_stocktake_session,
)


def start_new_session(name: str, end_date: str = None, note: str = "",
                      created_by: int = None) -> dict:
    """
    新規棚卸しセッションを開始し、対象物品の記録を自動生成する。
    """
    start_date = datetime.now(JST).strftime('%Y-%m-%d')
    result = create_stocktake_session(
        name=name,
        start_date=start_date,
        end_date=end_date,
        note=note,
        created_by=created_by,
    )
    if not result.get("success"):
        return result
    
    session_id = result["session_id"]
    init_result = initialize_stocktake_records(session_id)
    if not init_result.get("success"):
        return init_result
    
    return {
        "success": True,
        "message": f"✅ セッション「{name}」を作成し、{init_result.get('count', 0)}件の物品を登録しました",
        "session_id": session_id,
        "count": init_result.get("count", 0),
    }


def close_session(session_id: int, user_name: str, department: str = "",
                  apply_adjustments: bool = True) -> dict:
    """
    棚卸しセッションをクローズする。
    apply_adjustments=True の場合、承認済みの差異を在庫に反映してからクローズ。
    """
    session = get_stocktake_session_by_id(session_id)
    if not session:
        return {"success": False, "message": "❌ セッションが見つかりません"}
    if session["status"] == "CLOSED":
        return {"success": False, "message": "❌ 既にクローズされています"}
    
    if apply_adjustments:
        adj_result = apply_stocktake_adjustments(session_id, user_name, department)
        if not adj_result.get("success"):
            return adj_result
    
    return update_stocktake_session_status(session_id, "CLOSED")


def record_count(record_id: int, actual_qty: int, counted_by: int,
                 note: str = "") -> dict:
    """実数カウントを記録"""
    if actual_qty < 0:
        return {"success": False, "message": "❌ 実数は0以上を入力してください"}
    return update_stocktake_record_count(record_id, actual_qty, counted_by, note)


def verify_item(record_id: int, verified_by: int) -> dict:
    """記録を総務確認する"""
    return verify_stocktake_record(record_id, verified_by)


def approve_item(record_id: int, approved_by: int) -> dict:
    """記録を上長承認する"""
    return approve_stocktake_record(record_id, approved_by)


def batch_verify(record_ids: list, verified_by: int) -> dict:
    """一括確認"""
    if not record_ids:
        return {"success": False, "message": "❌ 確認対象が選択されていません"}
    return batch_verify_stocktake_records(record_ids, verified_by)


def batch_approve(record_ids: list, approved_by: int) -> dict:
    """一括承認"""
    if not record_ids:
        return {"success": False, "message": "❌ 承認対象が選択されていません"}
    return batch_approve_stocktake_records(record_ids, approved_by)


def get_session_progress(session_id: int) -> dict:
    """セッションの進捗率を含むサマリーを返す"""
    summary = get_stocktake_summary(session_id)
    total = summary.get("total_items", 0)
    if total > 0:
        counted = total - summary.get("pending_count", 0)
        summary["progress_pct"] = round(counted / total * 100, 1)
        summary["completion_pct"] = round(
            (summary.get("approved_count", 0) + summary.get("applied_count", 0)) / total * 100, 1
        )
    else:
        summary["progress_pct"] = 0.0
        summary["completion_pct"] = 0.0
    return summary


def generate_stocktake_html_report(session_id: int) -> str:
    """棚卸し差異レポートをHTML形式で生成"""
    session = get_stocktake_session_by_id(session_id)
    if not session:
        return "<p>セッションが見つかりません</p>"
    
    summary = get_stocktake_summary(session_id)
    diff_records = get_stocktake_diff_records(session_id)
    all_records = get_stocktake_records(session_id)
    
    now_str = datetime.now(JST).strftime('%Y年%m月%d日 %H:%M')
    
    html = f"""
    <html>
    <head>
    <meta charset="utf-8">
    <title>棚卸し報告書 - {session['name']}</title>
    <style>
        body {{ font-family: 'Noto Sans JP', sans-serif; margin: 20px; color: #333; }}
        h1 {{ text-align: center; border-bottom: 3px solid #2196F3; padding-bottom: 10px; }}
        h2 {{ color: #1565C0; margin-top: 30px; }}
        .meta {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .meta table {{ border: none; }}
        .meta td {{ padding: 5px 15px; border: none; }}
        .summary-grid {{ display: flex; gap: 15px; margin: 15px 0; flex-wrap: wrap; }}
        .summary-card {{ background: #e3f2fd; padding: 15px; border-radius: 8px; text-align: center; min-width: 120px; }}
        .summary-card .num {{ font-size: 28px; font-weight: bold; color: #1565C0; }}
        .summary-card .label {{ font-size: 12px; color: #666; }}
        table.data {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }}
        table.data th {{ background: #1565C0; color: white; padding: 8px; text-align: left; }}
        table.data td {{ border: 1px solid #ddd; padding: 6px 8px; }}
        table.data tr:nth-child(even) {{ background: #f9f9f9; }}
        .surplus {{ color: #1B5E20; font-weight: bold; }}
        .shortage {{ color: #B71C1C; font-weight: bold; }}
        .print-btn {{ display: block; text-align: center; margin: 20px; }}
        @media print {{
            .print-btn {{ display: none; }}
        }}
    </style>
    </head>
    <body>
    <div class="print-btn"><button onclick="window.print()">🖨️ 印刷</button></div>
    <h1>📋 棚卸し報告書</h1>
    
    <div class="meta">
    <table>
        <tr><td><strong>セッション名:</strong></td><td>{session['name']}</td></tr>
        <tr><td><strong>実施期間:</strong></td><td>{session['start_date']} ～ {session.get('end_date') or '未定'}</td></tr>
        <tr><td><strong>ステータス:</strong></td><td>{session['status']}</td></tr>
        <tr><td><strong>作成者:</strong></td><td>{session.get('creator_name', '-')}</td></tr>
        <tr><td><strong>出力日時:</strong></td><td>{now_str}</td></tr>
    </table>
    </div>
    
    <h2>📊 サマリー</h2>
    <div class="summary-grid">
        <div class="summary-card"><div class="num">{summary.get('total_items', 0)}</div><div class="label">対象品目</div></div>
        <div class="summary-card"><div class="num">{summary.get('counted_count', 0) + summary.get('verified_count', 0) + summary.get('approved_count', 0) + summary.get('applied_count', 0)}</div><div class="label">入力済み</div></div>
        <div class="summary-card"><div class="num">{summary.get('pending_count', 0)}</div><div class="label">未入力</div></div>
        <div class="summary-card"><div class="num">{summary.get('diff_count', 0)}</div><div class="label">差異あり</div></div>
        <div class="summary-card"><div class="num">{summary.get('total_surplus', 0)}</div><div class="label">過剰合計</div></div>
        <div class="summary-card"><div class="num">{summary.get('total_shortage', 0)}</div><div class="label">不足合計</div></div>
    </div>
    """
    
    # 差異一覧テーブル
    if diff_records:
        html += """
        <h2>⚠️ 差異一覧</h2>
        <table class="data">
        <thead>
            <tr>
                <th>品番</th><th>物品名</th><th>カテゴリ</th>
                <th>システム数</th><th>実数</th><th>差異</th>
                <th>金額差異</th><th>状態</th><th>入力者</th><th>備考</th>
            </tr>
        </thead>
        <tbody>
        """
        for rec in diff_records:
            diff = rec.get("diff_qty", 0)
            diff_class = "surplus" if diff > 0 else "shortage"
            diff_display = f"+{diff}" if diff > 0 else str(diff)
            price = rec.get("unit_price", 0) or 0
            amount_diff = diff * price
            amount_display = f"¥{amount_diff:,.0f}" if amount_diff != 0 else "-"
            
            html += f"""
            <tr>
                <td>{rec.get('item_code', '-')}</td>
                <td>{rec.get('item_name', '')}</td>
                <td>{rec.get('category', '')}</td>
                <td style="text-align:right">{rec.get('system_qty', 0)}</td>
                <td style="text-align:right">{rec.get('actual_qty', '-')}</td>
                <td style="text-align:right" class="{diff_class}">{diff_display}</td>
                <td style="text-align:right">{amount_display}</td>
                <td>{rec.get('status', '')}</td>
                <td>{rec.get('counted_by_name', '-')}</td>
                <td>{rec.get('note', '') or ''}</td>
            </tr>
            """
        html += "</tbody></table>"
    else:
        html += "<h2>⚠️ 差異一覧</h2><p>差異のある物品はありません。</p>"
    
    # 全件一覧
    html += """
    <h2>📦 全物品一覧</h2>
    <table class="data">
    <thead>
        <tr>
            <th>品番</th><th>物品名</th><th>カテゴリ</th>
            <th>システム数</th><th>実数</th><th>差異</th><th>状態</th>
        </tr>
    </thead>
    <tbody>
    """
    for rec in all_records:
        diff = rec.get("diff_qty", 0)
        actual = rec.get("actual_qty")
        actual_display = str(actual) if actual is not None else "未入力"
        diff_display = ""
        diff_class = ""
        if actual is not None:
            diff_display = f"+{diff}" if diff > 0 else str(diff) if diff != 0 else "0"
            diff_class = "surplus" if diff > 0 else "shortage" if diff < 0 else ""
        
        html += f"""
        <tr>
            <td>{rec.get('item_code', '-')}</td>
            <td>{rec.get('item_name', '')}</td>
            <td>{rec.get('category', '')}</td>
            <td style="text-align:right">{rec.get('system_qty', 0)}</td>
            <td style="text-align:right">{actual_display}</td>
            <td style="text-align:right" class="{diff_class}">{diff_display}</td>
            <td>{rec.get('status', '')}</td>
        </tr>
        """
    html += "</tbody></table>"
    html += "</body></html>"
    return html


def generate_stocktake_excel_data(session_id: int) -> list:
    """棚卸しExcel用データを生成（リスト of dict）"""
    records = get_stocktake_records(session_id)
    rows = []
    for rec in records:
        actual = rec.get("actual_qty")
        diff = rec.get("diff_qty", 0)
        price = rec.get("unit_price", 0) or 0
        rows.append({
            "品番": rec.get("item_code", ""),
            "物品名": rec.get("item_name", ""),
            "カテゴリ": rec.get("category", ""),
            "部署": rec.get("department_tags", ""),
            "保管場所": rec.get("location_text", "") or rec.get("inv_location", "") or "",
            "システム数量": rec.get("system_qty", 0),
            "実数量": actual if actual is not None else "",
            "差異": diff if actual is not None else "",
            "差異金額": diff * price if actual is not None and price else "",
            "状態": rec.get("status", ""),
            "入力者": rec.get("counted_by_name", ""),
            "入力日時": rec.get("counted_at", ""),
            "確認者": rec.get("verified_by_name", ""),
            "承認者": rec.get("approved_by_name", ""),
            "備考": rec.get("note", "") or "",
        })
    return rows


# Re-export for convenience
__all__ = [
    'start_new_session',
    'close_session',
    'record_count',
    'verify_item',
    'approve_item',
    'batch_verify',
    'batch_approve',
    'get_session_progress',
    'generate_stocktake_html_report',
    'generate_stocktake_excel_data',
    # pass-through
    'get_stocktake_sessions',
    'get_stocktake_session_by_id',
    'get_stocktake_records',
    'get_stocktake_summary',
    'get_stocktake_diff_records',
    'get_stocktake_templates',
    'get_stocktake_template_by_id',
    'create_stocktake_template',
    'update_stocktake_template',
    'set_template_mappings',
    'get_template_mappings',
    'delete_stocktake_session',
]

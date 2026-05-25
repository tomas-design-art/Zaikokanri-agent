"""
棚卸しExcelレンダラー

棚卸し結果をExcelファイルとして出力する。
"""

import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter


def render_stocktake_excel(data_rows: list, session_info: dict = None,
                            summary: dict = None) -> bytes:
    """
    棚卸しデータをExcel形式で出力する。
    
    Args:
        data_rows: generate_stocktake_excel_data() の戻り値
        session_info: セッション情報 dict
        summary: サマリー情報 dict
    
    Returns:
        Excel ファイルの bytes
    """
    wb = Workbook()
    
    # --- シート1: 棚卸し結果一覧 ---
    ws = wb.active
    ws.title = "棚卸し結果"
    
    # スタイル定義
    header_font = Font(name="Noto Sans JP", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    data_font = Font(name="Noto Sans JP", size=10)
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    surplus_font = Font(name="Noto Sans JP", size=10, color="1B5E20", bold=True)
    shortage_font = Font(name="Noto Sans JP", size=10, color="B71C1C", bold=True)
    
    # ヘッダー情報
    row_offset = 1
    if session_info:
        ws.merge_cells("A1:O1")
        title_cell = ws["A1"]
        title_cell.value = f"棚卸し報告書 - {session_info.get('name', '')}"
        title_cell.font = Font(name="Noto Sans JP", bold=True, size=16)
        title_cell.alignment = Alignment(horizontal="center")
        
        ws["A3"] = "実施期間:"
        ws["B3"] = f"{session_info.get('start_date', '')} ～ {session_info.get('end_date', '未定')}"
        ws["A4"] = "ステータス:"
        ws["B4"] = session_info.get("status", "")
        ws["A5"] = "作成者:"
        ws["B5"] = session_info.get("creator_name", "-")
        
        for r in range(3, 6):
            ws.cell(row=r, column=1).font = Font(name="Noto Sans JP", bold=True, size=10)
            ws.cell(row=r, column=2).font = data_font
        
        row_offset = 7
    
    # サマリー
    if summary:
        ws.cell(row=row_offset, column=1).value = "【サマリー】"
        ws.cell(row=row_offset, column=1).font = Font(name="Noto Sans JP", bold=True, size=11)
        row_offset += 1
        
        summary_items = [
            ("対象品目", summary.get("total_items", 0)),
            ("未入力", summary.get("pending_count", 0)),
            ("入力済", summary.get("counted_count", 0)),
            ("確認済", summary.get("verified_count", 0)),
            ("承認済", summary.get("approved_count", 0)),
            ("反映済", summary.get("applied_count", 0)),
            ("差異あり", summary.get("diff_count", 0)),
            ("過剰合計", summary.get("total_surplus", 0)),
            ("不足合計", summary.get("total_shortage", 0)),
        ]
        for i, (label, value) in enumerate(summary_items):
            col = (i % 3) * 2 + 1
            row = row_offset + (i // 3)
            ws.cell(row=row, column=col).value = f"{label}:"
            ws.cell(row=row, column=col).font = Font(name="Noto Sans JP", bold=True, size=10)
            ws.cell(row=row, column=col + 1).value = value
            ws.cell(row=row, column=col + 1).font = data_font
        
        row_offset += 4
    
    # データヘッダー
    if data_rows:
        headers = list(data_rows[0].keys())
    else:
        headers = ["品番", "物品名", "カテゴリ", "部署", "保管場所",
                    "システム数量", "実数量", "差異", "差異金額", "状態",
                    "入力者", "入力日時", "確認者", "承認者", "備考"]
    
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=row_offset, column=col_idx)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border
    
    # データ行
    for row_idx, row_data in enumerate(data_rows, row_offset + 1):
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            value = row_data.get(header, "")
            cell.value = value
            cell.border = border
            
            # 差異列のスタイリング
            if header == "差異" and isinstance(value, (int, float)):
                if value > 0:
                    cell.font = surplus_font
                elif value < 0:
                    cell.font = shortage_font
                else:
                    cell.font = data_font
            elif header in ("システム数量", "実数量", "差異", "差異金額"):
                cell.alignment = Alignment(horizontal="right")
                cell.font = data_font
            else:
                cell.font = data_font
    
    # 列幅自動調整
    col_widths = {
        "品番": 12, "物品名": 25, "カテゴリ": 12, "部署": 12, "保管場所": 15,
        "システム数量": 12, "実数量": 10, "差異": 8, "差異金額": 12, "状態": 10,
        "入力者": 10, "入力日時": 18, "確認者": 10, "承認者": 10, "備考": 20,
    }
    for col_idx, header in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(header, 12)
    
    # --- シート2: 差異一覧 ---
    ws2 = wb.create_sheet("差異一覧")
    diff_rows = [r for r in data_rows if r.get("差異") and r.get("差異") != 0 and r.get("差異") != ""]
    
    ws2.merge_cells("A1:J1")
    ws2["A1"].value = "差異一覧"
    ws2["A1"].font = Font(name="Noto Sans JP", bold=True, size=14)
    ws2["A1"].alignment = Alignment(horizontal="center")
    
    diff_headers = ["品番", "物品名", "カテゴリ", "システム数量", "実数量", "差異", "差異金額", "状態", "入力者", "備考"]
    for col_idx, header in enumerate(diff_headers, 1):
        cell = ws2.cell(row=3, column=col_idx)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border
    
    for row_idx, row_data in enumerate(diff_rows, 4):
        for col_idx, header in enumerate(diff_headers, 1):
            cell = ws2.cell(row=row_idx, column=col_idx)
            value = row_data.get(header, "")
            cell.value = value
            cell.border = border
            if header == "差異" and isinstance(value, (int, float)):
                cell.font = surplus_font if value > 0 else shortage_font if value < 0 else data_font
            else:
                cell.font = data_font
    
    for col_idx, header in enumerate(diff_headers, 1):
        ws2.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(header, 12)
    
    # バイト列として出力
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

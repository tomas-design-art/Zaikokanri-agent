"""\u68da\u5378\u3057\u7d50\u679c Excel \u30ec\u30f3\u30c0\u30e9\u30fc (pure openpyxl)\u3002"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


def render_stocktake_excel(
    rows: list[dict[str, Any]],
    session_info: dict[str, Any],
    summary: dict[str, Any],
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "\u68da\u5378\u3057\u7d50\u679c"

    header_fill = PatternFill("solid", fgColor="1565C0")
    header_font = Font(bold=True, color="FFFFFF")
    surplus_font = Font(color="2E7D32", bold=True)
    shortage_font = Font(color="C62828", bold=True)

    ws["A1"] = "\u68da\u5378\u3057\u7d50\u679c\u30ec\u30dd\u30fc\u30c8"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:G1")
    ws["A1"].alignment = Alignment(horizontal="center")

    ws["A3"], ws["B3"] = "\u30bb\u30c3\u30b7\u30e7\u30f3\u540d:", session_info.get("name", "")
    ws["A4"], ws["B4"] = "\u72b6\u614b:", session_info.get("status", "")
    ws["A5"], ws["B5"] = "\u958b\u59cb\u65e5\u6642:", str(session_info.get("started_at", ""))

    headers = ["\u54c1\u76ee\u540d", "\u30b7\u30b9\u30c6\u30e0\u6570\u91cf", "\u5b9f\u6570", "\u5dee\u7570", "\u30b9\u30c6\u30fc\u30bf\u30b9", "\u30e1\u30e2"]
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=7, column=col, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    r = 8
    for row in rows:
        ws.cell(row=r, column=1, value=row.get("item_name", ""))
        ws.cell(row=r, column=2, value=row.get("system_qty", 0))
        ws.cell(row=r, column=3, value=row.get("actual_qty"))
        diff_cell = ws.cell(row=r, column=4, value=row.get("diff_qty"))
        if isinstance(row.get("diff_qty"), (int, float)):
            if row["diff_qty"] > 0:
                diff_cell.font = surplus_font
            elif row["diff_qty"] < 0:
                diff_cell.font = shortage_font
        ws.cell(row=r, column=5, value=row.get("status", ""))
        ws.cell(row=r, column=6, value=row.get("note", ""))
        r += 1

    for col, w in enumerate([28, 12, 10, 10, 14, 30], 1):
        ws.column_dimensions[chr(64 + col)].width = w

    ws2 = wb.create_sheet("\u30b5\u30de\u30ea\u30fc")
    ws2["A1"] = "\u30b5\u30de\u30ea\u30fc"
    ws2["A1"].font = Font(bold=True, size=14)
    rows_summary = [
        ("\u5bfe\u8c61\u54c1\u76ee\u6570", summary.get("total_items", 0)),
        ("\u30ab\u30a6\u30f3\u30c8\u6e08\u307f", summary.get("counted", 0)),
        ("\u672a\u30ab\u30a6\u30f3\u30c8", summary.get("uncounted", 0)),
        ("\u4e00\u81f4", summary.get("match", 0)),
        ("\u4f59\u5270", summary.get("surplus", 0)),
        ("\u4e0d\u8db3", summary.get("shortage", 0)),
    ]
    for i, (label, val) in enumerate(rows_summary, 3):
        ws2.cell(row=i, column=1, value=label).font = Font(bold=True)
        ws2.cell(row=i, column=2, value=val)

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()

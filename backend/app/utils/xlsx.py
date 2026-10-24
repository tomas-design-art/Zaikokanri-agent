"""openpyxl でセルを書く共通処理。"""
from __future__ import annotations

from typing import Any

from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet


def write_cell(ws: Worksheet, row: int, column: int, value: Any) -> Cell:
    """文字列は必ず「文字」として書く（"=..." でも数式にしない：G-01）。"""
    cell = ws.cell(row=row, column=column, value=value)
    if isinstance(value, str):
        cell.data_type = "s"
    return cell

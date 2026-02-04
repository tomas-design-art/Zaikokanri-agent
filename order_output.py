"""
発注書出力モジュール（メール文面・PDF・Excel）
全ての出力はpayload（正本JSON）から生成
"""
from datetime import datetime
from io import BytesIO
import pandas as pd
from typing import List, Dict, Any


def build_purchase_order_payloads(selected_requests: List[Dict]) -> List[Dict]:
    """
    承認済み申請リストから vendor別の発注書payload（正本JSON）を生成
    
    Args:
        selected_requests: 承認済み申請のリスト
    
    Returns:
        List[Dict]: vendor別のpayload配列
    """
    from collections import defaultdict
    
    vendor_groups = defaultdict(list)
    for req in selected_requests:
        vendor = req.get('vendor_name') or "不明業者"
        vendor_groups[vendor].append(req)
    
    payloads = []
    
    for vendor, reqs in vendor_groups.items():
        items = []
        total_amount = 0.0
        has_unpriced_items = False
        
        # 発注元情報（最初の申請から取得）
        department = reqs[0].get('requested_by_department', '') if reqs else ''
        requester_name = reqs[0].get('requester_name', '') if reqs else ''
        
        for req in reqs:
            unit_price = req.get('unit_price', 0)
            quantity = req.get('requested_qty', 0)
            
            # unit_priceを数値として扱う
            if unit_price and unit_price > 0:
                unit_price_num = float(unit_price)
                subtotal = unit_price_num * quantity
                total_amount += subtotal
            else:
                unit_price_num = 0.0
                subtotal = None
                has_unpriced_items = True
            
            item = {
                "item_name": req.get('item_name', ''),
                "item_code": req.get('item_code', ''),
                "vendor_part_no": req.get('vendor_part_no', ''),
                "quantity": quantity,
                "unit_price": unit_price_num,
                "subtotal": subtotal,
                "notes": req.get('note', '')
            }
            items.append(item)
        
        payload = {
            "vendor": vendor,
            "subject": "発注書",
            "to": f"{vendor} 御中",
            "ordered_at": datetime.now().strftime("%Y-%m-%d"),
            "requester": {
                "department": department,
                "name": requester_name
            },
            "items": items,
            "total": total_amount if not has_unpriced_items else None,
            "has_unpriced_items": has_unpriced_items
        }
        
        payloads.append(payload)
    
    return payloads


def generate_email_text(payload: Dict, draft_text: str = "") -> str:
    """
    payloadからメール文面を生成
    
    Args:
        payload: 発注書payload（正本JSON）
        draft_text: AI/テンプレート生成済みの文案（任意）
    
    Returns:
        str: メール本文
    """
    vendor = payload.get("vendor", "")
    items = payload.get("items", [])
    ordered_at = payload.get("ordered_at", "")
    requester = payload.get("requester", {})
    department = requester.get("department", "")
    requester_name = requester.get("name", "")
    has_unpriced = payload.get("has_unpriced_items", False)
    total = payload.get("total")
    
    today = datetime.strptime(ordered_at, "%Y-%m-%d").strftime("%Y年%m月%d日") if ordered_at else datetime.now().strftime("%Y年%m月%d日")
    
    # 明細テーブルを作成
    detail_lines = []
    
    for idx, item in enumerate(items, 1):
        name = item.get("item_name", "品目名不明")
        code = item.get("item_code", "")
        qty = item.get("quantity", 0)
        unit_price = item.get("unit_price", 0)
        
        if unit_price > 0:
            subtotal = item.get("subtotal", unit_price * qty)
            detail_lines.append(f"{idx}. {name}（{code}）× {qty}個 @ ¥{unit_price:,.0f} = ¥{subtotal:,.0f}")
        else:
            detail_lines.append(f"{idx}. {name}（{code}）× {qty}個 @ 単価未設定 = 要確認")
    
    details_text = "\n".join(detail_lines)
    
    # 合計金額
    if has_unpriced:
        if total and total > 0:
            total_text = f"¥{total:,.0f} ※一部単価要確認"
        else:
            total_text = "要確認"
    else:
        total_text = f"¥{total:,.0f}" if total else "¥0"
    
    requester_info = f"{department} {requester_name}".strip() or "担当者"
    
    email_body = f"""件名: 【発注】物品発注のお願い

{vendor} 御中

お世話になっております。
{requester_info}です。

下記の通り発注いたしますので、納品のほどよろしくお願い申し上げます。

━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 発注日: {today}
■ 発注明細:

{details_text}

■ 合計金額: {total_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━

【文案（参考）】
{draft_text if draft_text else '（文案なし）'}

━━━━━━━━━━━━━━━━━━━━━━━━━━
【納品先】
{department or "（部署名）"}

【お問い合わせ先】
{requester_info}
Email: （メールアドレス）
Tel: （電話番号）

━━━━━━━━━━━━━━━━━━━━━━━━━━
CC: （関係者）
署名: {requester_info}
━━━━━━━━━━━━━━━━━━━━━━━━━━

以上、よろしくお願いいたします。
"""
    
    return email_body


def render_pdf(payload: Dict) -> bytes:
    """
    payloadからPDF発注書を生成
    
    Args:
        payload: 発注書payload（正本JSON）
    
    Returns:
        bytes: PDFバイナリデータ
    """
    from fpdf import FPDF
    
    vendor = payload.get("vendor", "")
    items = payload.get("items", [])
    ordered_at = payload.get("ordered_at", "")
    requester = payload.get("requester", {})
    department = requester.get("department", "")
    requester_name = requester.get("name", "")
    has_unpriced = payload.get("has_unpriced_items", False)
    total = payload.get("total")
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    
    # タイトル
    pdf.cell(0, 10, 'Purchase Order', 0, 1, 'C')
    pdf.ln(3)
    
    pdf.set_font('Arial', '', 10)
    
    # 日本語を含む文字列をASCII範囲に変換
    def to_romaji_or_code(text, code=""):
        """日本語を含む場合はコード or プレースホルダーを返す"""
        if not text:
            return ""
        if any(ord(c) > 127 for c in text):
            return code if code else "[Japanese text - see email]"
        return text
    
    vendor_display = to_romaji_or_code(vendor)
    department_display = to_romaji_or_code(department)
    requester_display = to_romaji_or_code(requester_name)
    
    # ヘッダー情報
    pdf.cell(0, 6, f'Order Date: {ordered_at}', 0, 1)
    pdf.cell(0, 6, f'To (Vendor): {vendor_display}', 0, 1)
    pdf.cell(0, 6, f'From: {department_display} / {requester_display}', 0, 1)
    pdf.ln(5)
    
    # 明細テーブルヘッダー
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(85, 8, 'Item Name (Code)', 1, 0, 'C')
    pdf.cell(25, 8, 'Qty', 1, 0, 'C')
    pdf.cell(35, 8, 'Unit Price', 1, 0, 'C')
    pdf.cell(35, 8, 'Subtotal', 1, 0, 'C')
    pdf.ln()
    
    pdf.set_font('Arial', '', 8)
    
    for item in items:
        # 品目名を取得
        item_name = item.get("item_name", "")
        item_code = item.get("item_code", "")
        
        # 表示用品目名を作成
        if any(ord(c) > 127 for c in item_name):
            # 日本語を含む場合はコードのみ
            display_name = f"[{item_code}]" if item_code else "[No code]"
        else:
            # 英数字のみの場合は品目名(コード)形式
            if item_code:
                display_name = f"{item_name} ({item_code})"
            else:
                display_name = item_name
        
        display_name = display_name[:40]
        
        qty = item.get("quantity", 0)
        unit_price = item.get("unit_price", 0)
        subtotal = item.get("subtotal")
        
        # 品目名
        pdf.cell(85, 8, display_name, 1)
        pdf.cell(25, 8, str(qty), 1, 0, 'C')
        
        if unit_price > 0 and subtotal is not None:
            pdf.cell(35, 8, f'JPY {unit_price:,.0f}', 1, 0, 'R')
            pdf.cell(35, 8, f'JPY {subtotal:,.0f}', 1, 0, 'R')
        else:
            # 単価未設定
            pdf.cell(35, 8, 'TBD', 1, 0, 'C')
            pdf.cell(35, 8, 'TBD', 1, 0, 'C')
        
        pdf.ln()
    
    # 合計行
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(110, 8, '', 0)
    pdf.cell(35, 8, 'Total:', 1, 0, 'C')
    
    if has_unpriced:
        pdf.cell(35, 8, 'TBD (Confirm)', 1, 0, 'C')
    else:
        pdf.cell(35, 8, f'JPY {total:,.0f}' if total else 'JPY 0', 1, 0, 'R')
    
    pdf.ln(10)
    
    # 注記
    pdf.set_font('Arial', '', 8)
    if has_unpriced:
        pdf.multi_cell(0, 5, 'Note: Some unit prices are TBD. Please confirm total amount via email.')
    else:
        pdf.multi_cell(0, 5, 'Note: Please refer to the email for detailed information.')
    
    return bytes(pdf.output())


def render_excel(payloads: List[Dict]) -> bytes:
    """
    payloadリストからExcel発注書を生成（業者別シート）
    
    Args:
        payloads: 発注書payload配列（業者ごと）
    
    Returns:
        bytes: Excelバイナリデータ
    """
    import pandas as pd
    from io import BytesIO
    
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for payload in payloads:
            vendor = payload.get("vendor", "不明業者")
            items = payload.get("items", [])
            ordered_at = payload.get("ordered_at", "")
            requester = payload.get("requester", {})
            department = requester.get("department", "")
            requester_name = requester.get("name", "")
            has_unpriced = payload.get("has_unpriced_items", False)
            total = payload.get("total")
            
            # シート名（業者名の先頭15文字）
            sheet_name = vendor[:15] if vendor else "Unknown"
            
            # DataFrame作成
            rows = []
            for item in items:
                row = {
                    "品目名": item.get("item_name", ""),
                    "品目コード": item.get("item_code", ""),
                    "業者品番": item.get("vendor_part_no", ""),
                    "数量": item.get("quantity", 0),
                    "単価": item.get("unit_price") if item.get("unit_price", 0) > 0 else "",
                    "金額": item.get("subtotal") if item.get("subtotal") is not None else "",
                    "備考": item.get("notes", "")
                }
                rows.append(row)
            
            df = pd.DataFrame(rows)
            
            # ヘッダー行を追加
            header_df = pd.DataFrame([
                {"品目名": "発注日:", "品目コード": ordered_at, "業者品番": "", "数量": "", "単価": "", "金額": "", "備考": ""},
                {"品目名": "業者:", "品目コード": vendor, "業者品番": "", "数量": "", "単価": "", "金額": "", "備考": ""},
                {"品目名": "部署:", "品目コード": department, "業者品番": "", "数量": "", "単価": "", "金額": "", "備考": ""},
                {"品目名": "発注者:", "品目コード": requester_name, "業者品番": "", "数量": "", "単価": "", "金額": "", "備考": ""},
                {"品目名": "", "品目コード": "", "業者品番": "", "数量": "", "単価": "", "金額": "", "備考": ""},
            ])
            
            final_df = pd.concat([header_df, df], ignore_index=True)
            
            # 合計行
            if has_unpriced:
                total_row = {"品目名": "", "品目コード": "", "業者品番": "", "数量": "", "単価": "合計:", "金額": "要確認", "備考": ""}
            else:
                total_row = {"品目名": "", "品目コード": "", "業者品番": "", "数量": "", "単価": "合計:", "金額": total if total else 0, "備考": ""}
            
            final_df = pd.concat([final_df, pd.DataFrame([total_row])], ignore_index=True)
            
            # シートに書き込み
            final_df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    output.seek(0)
    return output.read()
    """
    Excel発注書を生成（複数vendorを複数シートで）
    
    Args:
        vendor_groups: {vendor_name: [items...]} の辞書
    
    Returns:
        bytes: Excelバイナリデータ
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    
    wb = Workbook()
    wb.remove(wb.active)  # デフォルトシートを削除
    
    for vendor, items in vendor_groups.items():
        # シート名を作成（無効文字を除去）
        sheet_name = vendor.replace("/", "_").replace("\\", "_").replace("?", "")[:31]
        ws = wb.create_sheet(title=sheet_name)
        
        # ヘッダー
        ws['A1'] = f'発注書 - {vendor}'
        ws['A1'].font = Font(size=14, bold=True)
        ws['A2'] = f'発注日: {datetime.now().strftime("%Y年%m月%d日")}'
        
        # 明細テーブルヘッダー
        headers = ['品目名', '品目コード', '業者品番', '数量', '単価', '小計', '備考']
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
            cell.alignment = Alignment(horizontal='center')
        
        # データ行
        row_idx = 5
        total_amount = 0
        has_unconfirmed_price = False
        
        for item in items:
            ws.cell(row=row_idx, column=1, value=item.get("item_name", ""))
            ws.cell(row=row_idx, column=2, value=item.get("item_code", ""))
            ws.cell(row=row_idx, column=3, value=item.get("vendor_part_no", ""))
            ws.cell(row=row_idx, column=4, value=item.get("requested_qty", 0))
            
            unit_price = item.get("unit_price", 0)
            if unit_price and unit_price > 0:
                ws.cell(row=row_idx, column=5, value=unit_price)
                subtotal = unit_price * item.get("requested_qty", 0)
                ws.cell(row=row_idx, column=6, value=subtotal)
                total_amount += subtotal
            else:
                # 単価未設定
                has_unconfirmed_price = True
                ws.cell(row=row_idx, column=5, value="未設定")
                ws.cell(row=row_idx, column=6, value="要確認")
            
            ws.cell(row=row_idx, column=7, value=item.get("note", ""))
            row_idx += 1
        
        # 合計行
        ws.cell(row=row_idx, column=5, value="合計")
        ws.cell(row=row_idx, column=5).font = Font(bold=True)
        
        if has_unconfirmed_price:
            # 単価未設定がある場合は「要確認」または注記付き
            if total_amount > 0:
                ws.cell(row=row_idx, column=6, value=f"{total_amount:,} (一部未設定)")
            else:
                ws.cell(row=row_idx, column=6, value="要確認")
        else:
            # 全て単価設定済み
            ws.cell(row=row_idx, column=6, value=total_amount)
        
        ws.cell(row=row_idx, column=6).font = Font(bold=True)
        
        # 列幅調整
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 10
        ws.column_dimensions['E'].width = 12
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 30
    
    # バイト列として返す
    output = BytesIO()
    wb.save(output)
    return output.getvalue()

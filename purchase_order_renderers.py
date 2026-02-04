"""
発注書レンダラーモジュール
payload（正本JSON）からメール/PDF/Excelを生成
"""
from datetime import datetime
from io import BytesIO
import pandas as pd


def format_currency(yen: float | None) -> str:
    """
    金額をフォーマット（Noneなら「要確認」）
    
    Args:
        yen: 金額（円）
    
    Returns:
        str: フォーマットされた金額文字列
    """
    if yen is None:
        return "要確認"
    return f"¥{yen:,.0f}"


def generate_email_text(payload: dict, use_ai: bool = False) -> str:
    """
    payloadからメール文面を生成
    
    Args:
        payload: 発注書payload（正本JSON）
        use_ai: AIを使用するかどうか
    
    Returns:
        str: メール本文
    """
    # AI使用時の処理
    if use_ai:
        try:
            import os
            if os.getenv("OPENAI_API_KEY"):
                from ai import generate_purchase_order_text
                return generate_purchase_order_text(payload)
        except Exception:
            pass  # AI失敗時はテンプレートにフォールバック
    
    # テンプレート生成
    vendor = payload.get("vendor", "")
    items = payload.get("items", [])
    ordered_at = payload.get("ordered_at", "")
    requester = payload.get("requester", {})
    department = requester.get("department", "")
    requester_name = requester.get("name", "")
    has_unpriced = payload.get("has_unpriced_items", False)
    total = payload.get("total")
    
    # 日付フォーマット
    try:
        date_obj = datetime.strptime(ordered_at, "%Y-%m-%d")
        today = date_obj.strftime("%Y年%m月%d日")
    except:
        today = datetime.now().strftime("%Y年%m月%d日")
    
    # 明細テーブル
    detail_lines = []
    for idx, item in enumerate(items, 1):
        name = item.get("item_name", "品目名不明")
        code = item.get("item_code", "")
        qty = item.get("quantity", 0)
        unit_price = item.get("unit_price")
        subtotal = item.get("subtotal")
        
        if unit_price is not None and subtotal is not None:
            detail_lines.append(
                f"{idx}. {name}（{code}）× {qty}個 @ {format_currency(unit_price)} = {format_currency(subtotal)}"
            )
        else:
            detail_lines.append(
                f"{idx}. {name}（{code}）× {qty}個 @ 単価未設定 = 要確認"
            )
    
    details_text = "\n".join(detail_lines)
    
    # 合計金額
    total_text = format_currency(total)
    if has_unpriced and total is not None:
        total_text += " ※一部単価要確認"
    
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

【納品先】
{department or "（部署名）"}

【お問い合わせ先】
{requester_info}
Email: （メールアドレス）
Tel: （電話番号）

━━━━━━━━━━━━━━━━━━━━━━━━━━

以上、よろしくお願いいたします。
"""
    
    return email_body


def render_pdf(payload: dict) -> bytes:
    """
    payloadからPDF発注書を生成
    
    Args:
        payload: 発注書payload（正本JSON）
    
    Returns:
        bytes: PDFバイナリデータ
    """
    from fpdf import FPDF
    import os

    # ---------------------------------------------------------
    # 日本語フォント設定 (NotoSansJP-Regular.ttf)
    # ---------------------------------------------------------
    # ユーザー指定により、MS Gothic等のシステムフォントへのフォールバックは廃止。
    # 必ず fonts/NotoSansJP-Regular.ttf を使用する。
    
    FONT_NAME = "NotoSansJP"
    FONT_PATH = "fonts/NotoSansJP-Regular.ttf"
    
    if not os.path.exists(FONT_PATH):
        raise FileNotFoundError(
            f"日本語フォントファイルが見つかりません: {FONT_PATH}\n"
            "fontsフォルダに NotoSansJP-Regular.ttf を配置してください。"
        )

    pdf = FPDF()
    # fpdf2 compatible add_font
    pdf.add_font(FONT_NAME, "", FONT_PATH)
    pdf.add_page()
    
    # タイトル
    pdf.set_font(FONT_NAME, '', 16)
    pdf.cell(0, 10, '発注書', 0, 1, 'C')
    pdf.ln(3)

    vendor = payload.get("vendor", "")
    items = payload.get("items", [])
    ordered_at = payload.get("ordered_at", "")
    requester = payload.get("requester", {})
    requester_name = requester.get("name", "")
    department = requester.get("department", "")
    has_unpriced = payload.get("has_unpriced_items", False)
    total = payload.get("total")
    
    pdf.set_font(FONT_NAME, '', 10)
    
    # ヘッダー情報
    pdf.cell(0, 6, f'発注日: {ordered_at}', 0, 1)
    pdf.cell(0, 6, f'発注先: {vendor}', 0, 1)
    pdf.cell(0, 6, f'発注元: {department} / {requester_name}', 0, 1)
    pdf.ln(5)
    
    # 明細テーブルヘッダー
    pdf.set_font(FONT_NAME, '', 9)
    # 幅調整: 合計190くらいに収める (A4 width ~210 - margins)
    # ItemName(85), Qty(25), UnitPrice(35), Subtotal(35) = 180 -> OK
    pdf.cell(85, 8, '品目名（コード）', 1, 0, 'C')
    pdf.cell(25, 8, '数量', 1, 0, 'C')
    pdf.cell(35, 8, '単価', 1, 0, 'C')
    pdf.cell(35, 8, '金額', 1, 0, 'C')
    pdf.ln()
    
    pdf.set_font(FONT_NAME, '', 8)
    
    # 明細行
    for item in items:
        item_name = item.get("item_name", "")
        item_code = item.get("item_code", "")
        
        if item_code:
            display_name = f"{item_name} ({item_code})"
        else:
            display_name = item_name
            
        display_name = display_name[:40]
        
        qty = item.get("quantity", 0)
        unit_price = item.get("unit_price")
        subtotal = item.get("subtotal")
        
        # 品目名
        pdf.cell(85, 8, display_name, 1)
        pdf.cell(25, 8, str(qty), 1, 0, 'C')
        
        if unit_price is not None and subtotal is not None:
            pdf.cell(35, 8, f'¥ {unit_price:,.0f}', 1, 0, 'R')
            pdf.cell(35, 8, f'¥ {subtotal:,.0f}', 1, 0, 'R')
        else:
            # 単価未設定
            pdf.cell(35, 8, '要見積', 1, 0, 'C')
            pdf.cell(35, 8, '-', 1, 0, 'C')
        
        pdf.ln()
    
    # 合計行
    pdf.set_font(FONT_NAME, '', 9)
    pdf.cell(110, 8, '', 0)
    pdf.cell(35, 8, '合計:', 1, 0, 'C')
    
    if total is None:
        pdf.cell(35, 8, '要見積', 1, 0, 'C')
    else:
        pdf.cell(35, 8, f'¥ {total:,.0f}', 1, 0, 'R')
    
    pdf.ln(10)
    
    # 注記
    pdf.set_font(FONT_NAME, '', 8)
    if has_unpriced:
        pdf.multi_cell(0, 5, '備考: 単価未設定の品目が含まれています。正式な金額はメール等をご確認ください。')
    else:
        pdf.multi_cell(0, 5, '備考: 詳細は送信メールをご確認ください。')
    
    return bytes(pdf.output())


def render_excel(payloads: list) -> bytes:
    """
    payloadリストからExcel発注書を生成（業者別シート）
    
    Args:
        payloads: 発注書payload配列（業者ごと）
    
    Returns:
        bytes: Excelバイナリデータ
    """
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
                unit_price = item.get("unit_price")
                subtotal = item.get("subtotal")
                
                row = {
                    "品目名": item.get("item_name", ""),
                    "品目コード": item.get("item_code", ""),
                    "業者品番": item.get("vendor_part_no", ""),
                    "数量": item.get("quantity", 0),
                    "単価": unit_price if unit_price is not None else "",
                    "金額": subtotal if subtotal is not None else "",
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
            if total is None:
                total_row = {"品目名": "", "品目コード": "", "業者品番": "", "数量": "", "単価": "合計:", "金額": "要確認", "備考": ""}
            else:
                total_row = {"品目名": "", "品目コード": "", "業者品番": "", "数量": "", "単価": "合計:", "金額": total, "備考": ""}
            
            final_df = pd.concat([final_df, pd.DataFrame([total_row])], ignore_index=True)
            
            # シートに書き込み
            final_df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    output.seek(0)
    return output.read()

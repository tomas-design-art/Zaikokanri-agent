"""
発注書payload生成モジュール
承認済み申請からvendor別の正本JSONを生成
"""
from datetime import datetime
from collections import defaultdict


def build_purchase_order_payloads(selected_request_ids: list, db) -> list:
    """
    承認済み申請IDリストからvendor別のpayload（正本JSON）を生成
    
    Args:
        selected_request_ids: 承認済み申請のIDリスト
        db: データベース接続
    
    Returns:
        list[dict]: vendor別のpayload配列
    """
    if not selected_request_ids:
        return []
    
    # DBから一度だけデータを取得
    placeholders = ','.join('?' * len(selected_request_ids))
    query = f"""
        SELECT 
            pr.id,
            pr.item_id,
            pr.requested_qty,
            pr.note,
            pr.requested_by_department,
            u.display_name as requester_name,
            i.item_name,
            i.item_code,
            i.vendor_name,
            i.unit_price
        FROM purchase_requests pr
        INNER JOIN items i ON pr.item_id = i.id
        LEFT JOIN users u ON pr.requested_by_user_id = u.id
        WHERE pr.id IN ({placeholders})
          AND pr.status = 'APPROVED'
          AND pr.deleted_at IS NULL
        ORDER BY i.vendor_name, i.item_name
    """
    
    cursor = db.execute(query, selected_request_ids)
    rows = cursor.fetchall()
    
    if not rows:
        return []
    
    # vendor別にグループ化
    vendor_groups = defaultdict(list)
    
    for row in rows:
        vendor = row[8] if row[8] else "不明業者"
        
        # unit_price の扱い: None or 0 → 未設定
        unit_price_raw = row[9]
        if unit_price_raw is None or unit_price_raw == 0:
            unit_price = None
            subtotal = None
        else:
            unit_price = float(unit_price_raw)
            quantity = row[2]
            subtotal = unit_price * quantity
        
        item_data = {
            "request_id": row[0],
            "item_name": row[6] if row[6] else "品目名不明",
            "item_code": row[7] if row[7] else "",
            "vendor_part_no": "",  # このスキーマには存在しない
            "quantity": row[2],
            "unit_price": unit_price,
            "subtotal": subtotal,
            "notes": row[3] if row[3] else "",
            "department": row[4] if row[4] else "",
            "requester_name": row[5] if row[5] else ""
        }
        
        vendor_groups[vendor].append(item_data)
    
    # payload配列を生成
    payloads = []
    ordered_at = datetime.now().strftime("%Y-%m-%d")
    
    for vendor, items in vendor_groups.items():
        # 発注元情報（最初のアイテムから取得）
        department = items[0]["department"]
        requester_name = items[0]["requester_name"]
        
        # 合計金額と未設定フラグを計算
        total_amount = 0.0
        has_unpriced_items = False
        
        for item in items:
            if item["subtotal"] is None:
                has_unpriced_items = True
            else:
                total_amount += item["subtotal"]
        
        # payload構造
        payload = {
            "vendor": vendor,
            "subject": "発注書",
            "to": f"{vendor} 御中",
            "ordered_at": ordered_at,
            "requester": {
                "department": department,
                "name": requester_name
            },
            "items": [
                {
                    "item_name": item["item_name"],
                    "item_code": item["item_code"],
                    "vendor_part_no": item["vendor_part_no"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                    "subtotal": item["subtotal"],
                    "notes": item["notes"]
                }
                for item in items
            ],
            "total": None if has_unpriced_items else total_amount,
            "has_unpriced_items": has_unpriced_items
        }
        
        payloads.append(payload)
    
    return payloads

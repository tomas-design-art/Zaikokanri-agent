"""
CSV取り込みヘルパー関数
物品マスターの一括登録機能
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple
import io


def generate_sample_csv() -> str:
    """
    サンプルCSVを生成（UTF-8）
    
    Returns:
        CSV文字列
    """
    sample_data = """item_name,category_name,vendor_name,unit_price,item_code,vendor_part_no,department_tags,reorder_point,expiry_date,is_active,notes
ボールペン（黒）,文房具,株式会社文具センター,100,P001,BP-BLK-001,総務部,50,,1,日常使用品
A4コピー用紙,文房具,株式会社文具センター,500,P002,COPY-A4-500,総務部,20,,1,高品質コピー用紙
USBメモリ 32GB,電子機器,電子部品商事,1500,E001,USB32GB-001,情報システム部,10,,1,データ保存用
デスク,家具,オフィス家具プロ,55000,F002,DESK-STD-001,総務部,0,,1,標準オフィスデスク
造影剤 イオメロン300,薬品,医療機器商社,8000,M001,IOPAMIRO-300,医療部,5,2025-12-31,1,有効期限管理必須"""
    
    return sample_data


def validate_csv_row(row: dict, row_number: int, existing_categories: set, existing_vendors: set) -> Tuple[str, List[str], List[str]]:
    """
    CSV行のバリデーション（エラー入力対策強化版）
    
    Args:
        row: CSV行データ（dict）
        row_number: 行番号
        existing_categories: 既存のカテゴリ名セット
        existing_vendors: 既存の業者名セット
    
    Returns:
        (status, errors, warnings)
        status: 'ok', 'error', 'warning'
        errors: エラーメッセージリスト（ハードエラー）
        warnings: 警告メッセージリスト（ソフトエラー）
    """
    from utils.validation import to_float_safe, to_int_safe, validate_date_string, normalize_number_str
    
    errors = []
    warnings = []
    
    # 🔴 ハードエラーチェック
    # item_name が空
    if not row.get('item_name') or str(row.get('item_name')).strip() == '':
        errors.append(f"行{row_number}: 物品名(item_name)が空です")
    
    # unit_price が数値でない（全角数字・カンマ区切り対応）
    unit_price_str = row.get('unit_price', 0)
    # ¥や円を除去
    if isinstance(unit_price_str, str):
        unit_price_str = unit_price_str.replace('¥', '').replace('円', '').strip()
    
    ok, validated_price, error_msg = to_float_safe(unit_price_str, "単価", min_value=0, allow_zero=True)
    if not ok:
        errors.append(f"行{row_number}: {error_msg}")
    elif validated_price < 0:
        errors.append(f"行{row_number}: 単価は0以上で入力してください")
    
    # reorder_point（発注点）のバリデーション
    if row.get('reorder_point'):
        reorder_str = row.get('reorder_point')
        ok_reorder, validated_reorder, error_msg_reorder = to_int_safe(reorder_str, "発注点", min_value=0, allow_zero=True)
        if not ok_reorder:
            warnings.append(f"行{row_number}: {error_msg_reorder} → 0に設定します")
    
    # expiry_date が日付形式でない（入っている場合のみ）
    if row.get('expiry_date') and str(row.get('expiry_date')).strip():
        expiry_str = str(row.get('expiry_date')).strip()
        ok_date, validated_date, error_msg_date = validate_date_string(expiry_str, "期限日", required=False)
        if not ok_date:
            errors.append(f"行{row_number}: {error_msg_date}")
    
    # 🟡 ソフトエラー（警告）チェック
    # category_name が空
    if not row.get('category_name') or str(row.get('category_name')).strip() == '':
        warnings.append(f"行{row_number}: カテゴリ名(category_name)が空です → 「未分類」を自動作成します")
    elif row.get('category_name') not in existing_categories:
        warnings.append(f"行{row_number}: カテゴリ「{row.get('category_name')}」が存在しません → 自動作成します")
    
    # vendor_name が空
    if not row.get('vendor_name') or str(row.get('vendor_name')).strip() == '':
        warnings.append(f"行{row_number}: 業者名(vendor_name)が空です → 「不明業者」を自動作成します")
    elif row.get('vendor_name') not in existing_vendors:
        warnings.append(f"行{row_number}: 業者「{row.get('vendor_name')}」が存在しません → 自動作成します")
    
    # department_tags が未知（部署マスタに存在しない場合は警告のみ）
    if row.get('department_tags') and str(row.get('department_tags')).strip():
        # ここでは警告のみ（空扱い）
        pass
    
    # ステータス判定
    if errors:
        return 'error', errors, warnings
    elif warnings:
        return 'warning', errors, warnings
    else:
        return 'ok', errors, warnings


def check_duplicate(row: dict, existing_items: List[dict]) -> Tuple[bool, dict]:
    """
    重複チェック
    
    Args:
        row: CSV行データ
        existing_items: 既存物品リスト
    
    Returns:
        (is_duplicate, existing_item)
        is_duplicate: 重複しているか
        existing_item: 重複している物品情報（重複していない場合はNone）
    """
    item_code = str(row.get('item_code', '')).strip() if row.get('item_code') else None
    vendor_name = str(row.get('vendor_name', '')).strip() if row.get('vendor_name') else None
    vendor_part_no = str(row.get('vendor_part_no', '')).strip() if row.get('vendor_part_no') else None
    
    for existing in existing_items:
        # item_code があればそれをキーに判定
        if item_code and existing.get('item_code') == item_code:
            return True, existing
        
        # なければ vendor_name + vendor_part_no の組み合わせで判定
        if (not item_code and 
            vendor_name and vendor_part_no and
            existing.get('vendor_name') == vendor_name and 
            existing.get('vendor_item_code') == vendor_part_no):
            return True, existing
    
    return False, None


def prepare_import_data(row: dict) -> dict:
    """
    CSV行データを物品登録用に変換（エラー入力対策強化版）
    
    Args:
        row: CSV行データ
    
    Returns:
        物品登録用データ（dict）
    """
    from utils.validation import to_float_safe, to_int_safe, validate_date_string, normalize_number_str
    
    # 基本データ
    item_name = str(row.get('item_name', '')).strip()
    category = str(row.get('category_name', '未分類')).strip() or '未分類'
    vendor_name = str(row.get('vendor_name', '不明業者')).strip() or '不明業者'
    
    # 単価（全角数字・カンマ・¥・円の除去）
    unit_price_str = row.get('unit_price', 0)
    if isinstance(unit_price_str, str):
        unit_price_str = unit_price_str.replace('¥', '').replace('円', '').strip()
    
    ok, validated_price, _ = to_float_safe(unit_price_str, "単価", min_value=0, allow_zero=True)
    unit_price = validated_price if ok else 0
    
    # 資産区分を自動設定（50,000円以上なら資産）
    is_asset = 1 if unit_price >= 50000 else 0
    
    # オプショナル項目
    item_code = str(row.get('item_code', '')).strip() if row.get('item_code') else None
    vendor_part_no = str(row.get('vendor_part_no', '')).strip() if row.get('vendor_part_no') else None
    department_tags = str(row.get('department_tags', '')).strip() if row.get('department_tags') else None
    
    # 発注点（全角数字対応）
    reorder_str = row.get('reorder_point', 0)
    ok_reorder, validated_reorder, _ = to_int_safe(reorder_str, "発注点", min_value=0, allow_zero=True)
    reorder_point = validated_reorder if ok_reorder else 0
    
    # 期限日（日付バリデーション）
    expiry_date = None
    if row.get('expiry_date') and str(row.get('expiry_date')).strip():
        expiry_str = str(row.get('expiry_date')).strip()
        ok_date, validated_date, _ = validate_date_string(expiry_str, "期限日", required=False)
        if ok_date:
            expiry_date = validated_date
    
    # 有効フラグ
    is_active = 1
    if row.get('is_active') is not None:
        try:
            is_active = int(row.get('is_active'))
        except (ValueError, TypeError):
            is_active = 1
    
    # 備考
    notes = str(row.get('notes', '')).strip() if row.get('notes') else None
    
    return {
        'item_name': item_name,
        'category': category,
        'vendor_name': vendor_name,
        'unit_price': unit_price,
        'is_asset': is_asset,
        'item_code': item_code,
        'vendor_item_code': vendor_part_no,
        'department_tags': department_tags,
        'reorder_point': reorder_point,
        'expiry_date': expiry_date,
        'is_active': is_active,
        'notes': notes
    }

"""
バリデーション関数のテスト
全角数字、カンマ区切り、空白、マイナス、文字列などの入力パターンをテスト
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.validation import (
    to_int_safe, to_float_safe, normalize_number_str, 
    validate_required_text, validate_date_string,
    needs_correction_warning
)


def test_to_int_safe():
    """to_int_safe のテスト"""
    print("=" * 60)
    print("to_int_safe のテスト")
    print("=" * 60)
    
    test_cases = [
        # (入力値, min_value, allow_zero, 期待結果, 説明)
        ("10", 0, True, True, "通常の半角数字"),
        ("１０", 0, True, True, "全角数字"),
        ("1,000", 0, True, True, "カンマ区切り"),
        ("  5  ", 0, True, True, "前後に空白"),
        ("　５　", 0, True, True, "全角スペース付き全角数字"),
        ("abc", 0, True, False, "文字列"),
        ("-5", 0, True, False, "マイナス値（min_value=0）"),
        ("0", 0, True, True, "ゼロ（allow_zero=True）"),
        ("0", 0, False, False, "ゼロ（allow_zero=False）"),
        ("", 0, True, False, "空文字列"),
        ("10.5", 0, True, False, "小数（整数で要求）"),
        ("¥1200", 0, True, False, "¥記号付き（整数では不可）"),
    ]
    
    for value, min_val, allow_zero, expected_ok, description in test_cases:
        ok, result, msg = to_int_safe(value, "テスト数値", min_value=min_val, allow_zero=allow_zero)
        status = "✅" if ok == expected_ok else "❌"
        print(f"{status} 入力: '{value}' | 期待: {'OK' if expected_ok else 'NG'} | 実際: {'OK' if ok else 'NG'} | 結果: {result} | 説明: {description}")
        if not ok:
            print(f"   エラーメッセージ: {msg}")
    print()


def test_to_float_safe():
    """to_float_safe のテスト"""
    print("=" * 60)
    print("to_float_safe のテスト")
    print("=" * 60)
    
    test_cases = [
        # (入力値, min_value, allow_zero, 期待結果, 説明)
        ("10.5", 0.0, True, True, "通常の小数"),
        ("１０．５", 0.0, True, True, "全角数字の小数"),
        ("1,000.50", 0.0, True, True, "カンマ区切りの小数"),
        ("  5.5  ", 0.0, True, True, "前後に空白"),
        ("　５．５　", 0.0, True, True, "全角スペース付き全角数字"),
        ("1200", 0.0, True, True, "整数（小数でも可）"),
        ("¥1200", 0.0, True, False, "¥記号付き（変換試みるが失敗）"),
        ("abc", 0.0, True, False, "文字列"),
        ("-5.5", 0.0, True, False, "マイナス値（min_value=0）"),
        ("0.0", 0.0, True, True, "ゼロ（allow_zero=True）"),
        ("0.0", 0.0, False, False, "ゼロ（allow_zero=False）"),
        ("", 0.0, True, False, "空文字列"),
    ]
    
    for value, min_val, allow_zero, expected_ok, description in test_cases:
        ok, result, msg = to_float_safe(value, "テスト単価", min_value=min_val, allow_zero=allow_zero)
        status = "✅" if ok == expected_ok else "❌"
        print(f"{status} 入力: '{value}' | 期待: {'OK' if expected_ok else 'NG'} | 実際: {'OK' if ok else 'NG'} | 結果: {result} | 説明: {description}")
        if not ok:
            print(f"   エラーメッセージ: {msg}")
    print()


def test_normalize_number_str():
    """normalize_number_str のテスト"""
    print("=" * 60)
    print("normalize_number_str のテスト")
    print("=" * 60)
    
    test_cases = [
        ("１０", "10", "全角数字→半角"),
        ("1,000", "1000", "カンマ除去"),
        ("  5  ", "5", "前後の空白除去"),
        ("　５　", "5", "全角スペース除去＋全角数字→半角"),
        ("１，０００", "1000", "全角カンマ＋全角数字→半角"),
        ("abc", "abc", "文字列はそのまま"),
    ]
    
    for input_val, expected, description in test_cases:
        result = normalize_number_str(input_val)
        status = "✅" if result == expected else "❌"
        print(f"{status} 入力: '{input_val}' | 期待: '{expected}' | 実際: '{result}' | 説明: {description}")
    print()


def test_validate_required_text():
    """validate_required_text のテスト"""
    print("=" * 60)
    print("validate_required_text のテスト")
    print("=" * 60)
    
    test_cases = [
        ("物品名", None, True, "通常のテキスト"),
        ("   物品名   ", None, True, "前後に空白"),
        ("", None, False, "空文字列"),
        ("   ", None, False, "空白のみ"),
        ("あ" * 101, 100, False, "最大文字数超過（101文字）"),
        ("あ" * 100, 100, True, "最大文字数ちょうど（100文字）"),
    ]
    
    for value, max_len, expected_ok, description in test_cases:
        ok, result, msg = validate_required_text(value, "テスト項目", max_len=max_len)
        status = "✅" if ok == expected_ok else "❌"
        print(f"{status} 入力長: {len(value)} | 期待: {'OK' if expected_ok else 'NG'} | 実際: {'OK' if ok else 'NG'} | 説明: {description}")
        if not ok:
            print(f"   エラーメッセージ: {msg}")
    print()


def test_validate_date_string():
    """validate_date_string のテスト"""
    print("=" * 60)
    print("validate_date_string のテスト")
    print("=" * 60)
    
    test_cases = [
        ("2026-02-01", True, True, "正しい日付形式"),
        ("2026/02/01", True, True, "スラッシュ区切り（自動変換）"),
        ("２０２６－０２－０１", True, True, "全角数字＋全角ハイフン（自動変換）"),
        ("２０２６ー０２ー０１", True, True, "全角数字＋長音記号（自動変換）"),
        ("2026-2-1", True, True, "ゼロ埋めなし（自動補完）"),
        ("2026-13-01", False, False, "存在しない月"),
        ("2026-02-30", False, False, "存在しない日"),
        ("abc", False, False, "文字列"),
        ("", False, True, "空文字列（任意項目）"),
        ("2026-02", False, False, "年月のみ"),
    ]
    
    for value, required, expected_ok, description in test_cases:
        ok, result, msg = validate_date_string(value, "テスト日付", required=required)
        status = "✅" if ok == expected_ok else "❌"
        print(f"{status} 入力: '{value}' | 期待: {'OK' if expected_ok else 'NG'} | 実際: {'OK' if ok else 'NG'} | 結果: {result} | 説明: {description}")
        if not ok:
            print(f"   エラーメッセージ: {msg}")
    print()


def test_csv_special_cases():
    """CSV取り込みでよく見られる特殊ケースのテスト"""
    print("=" * 60)
    print("CSV取り込み特殊ケースのテスト")
    print("=" * 60)
    
    test_cases = [
        # (入力値, 処理関数, 期待結果, 説明)
        ("¥1,200", "単価", True, "円マーク＋カンマ区切り"),
        ("1200円", "単価", True, "円が後ろにある（自動除去）"),
        ("１，２００", "数量", True, "全角カンマ＋全角数字"),
        ("　１０　", "数量", True, "全角スペース＋全角数字"),
        ("10.0", "数量", False, "整数項目に小数"),
        ("", "数量", False, "空欄"),
    ]
    
    for value, field, expected_ok, description in test_cases:
        if field == "単価":
            # ¥と円を除去して変換を試みる
            ok, result, msg = to_float_safe(value, "単価", min_value=0, allow_zero=True)
        elif field == "数量":
            ok, result, msg = to_int_safe(value, "数量", min_value=1, allow_zero=False)
        else:
            ok, result, msg = False, None, "Unknown field"
        
        status = "✅" if ok == expected_ok else "❌"
        print(f"{status} 入力: '{value}' | フィールド: {field} | 期待: {'OK' if expected_ok else 'NG'} | 実際: {'OK' if ok else 'NG'} | 説明: {description}")
        if not ok and msg:
            print(f"   エラーメッセージ: {msg}")
    print()


def test_correction_warnings():
    """補正検出のテスト"""
    print("=" * 60)
    print("補正検出テスト（警告メッセージ生成）")
    print("=" * 60)
    
    test_cases = [
        # (入力値, フィールドタイプ, 期待される補正検出, 説明)
        ("¥1,200", "currency", True, "通貨記号＋カンマ"),
        ("1200円", "currency", True, "円記号"),
        ("１，２００", "number", True, "全角数字＋全角カンマ"),
        ("1200", "currency", False, "補正不要"),
        ("2026/02/01", "date", True, "スラッシュ区切り"),
        ("２０２６－０２－０１", "date", True, "全角ハイフン＋全角数字"),
        ("2026-02-01", "date", False, "補正不要"),
    ]
    
    for value, field_type, expected_needs_warn, description in test_cases:
        needs_warn, warn_msg = needs_correction_warning(value, field_type)
        status = "✅" if needs_warn == expected_needs_warn else "❌"
        print(f"{status} 入力: '{value}' | タイプ: {field_type} | 補正検出: {'あり' if needs_warn else 'なし'} | 説明: {description}")
        if needs_warn:
            print(f"   警告メッセージ: {warn_msg}")
    print()


def main():
    """全テストを実行"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "バリデーションテスト実行" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    test_to_int_safe()
    test_to_float_safe()
    test_normalize_number_str()
    test_validate_required_text()
    test_validate_date_string()
    test_csv_special_cases()
    test_correction_warnings()
    
    print("=" * 60)
    print("✅ 全テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    main()

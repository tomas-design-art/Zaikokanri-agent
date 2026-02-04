"""
入力バリデーション共通モジュール
- 全角→半角変換
- 数値フィールド検証
- 空欄/None統一処理
- 現場向け日本語エラーメッセージ
"""

from typing import Optional, Tuple, Any, List


# =============================================================================
# 全角→半角変換
# =============================================================================

# 全角英数字・記号→半角の変換テーブル
_ZEN_TO_HAN_DIGIT = str.maketrans('０１２３４５６７８９', '0123456789')
_ZEN_TO_HAN_ALPHA = str.maketrans(
    'ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ',
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
)
_ZEN_TO_HAN_SYMBOL = str.maketrans('，、．。　', ',,.  ')


def normalize_to_halfwidth(value: str) -> str:
    """
    全角英数字・記号を半角に変換する
    
    Args:
        value: 入力文字列
    
    Returns:
        半角に正規化された文字列
    """
    if value is None:
        return ""
    result = str(value)
    result = result.translate(_ZEN_TO_HAN_DIGIT)
    result = result.translate(_ZEN_TO_HAN_ALPHA)
    result = result.translate(_ZEN_TO_HAN_SYMBOL)
    return result


def normalize_number_string(value: str) -> str:
    """
    数値文字列を正規化（全角→半角、カンマ除去）
    
    Args:
        value: 入力文字列
    
    Returns:
        半角数字のみの文字列（小数点含む場合あり）
    """
    if value is None:
        return ""
    result = normalize_to_halfwidth(str(value))
    # カンマ除去
    result = result.replace(',', '')
    return result.strip()


# =============================================================================
# 空欄/None統一処理
# =============================================================================

def clean_string(value: Any, default: str = "") -> str:
    """
    None/空白を統一処理してトリムした文字列を返す
    
    Args:
        value: 入力値（任意の型）
        default: None/空の場合のデフォルト値
    
    Returns:
        トリム済み文字列、またはデフォルト値
    """
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def is_empty(value: Any) -> bool:
    """
    値が空（None, "", 空白のみ）かを判定
    
    Args:
        value: 入力値
    
    Returns:
        空ならTrue
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


# =============================================================================
# 数値バリデーション
# =============================================================================

def validate_integer(
    value: Any,
    field_name: str = "数値",
    required: bool = True,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    整数値のバリデーション
    
    Args:
        value: 入力値（文字列または数値）
        field_name: フィールド名（エラーメッセージ用）
        required: 必須かどうか
        min_value: 最小値（None=チェックなし）
        max_value: 最大値（None=チェックなし）
    
    Returns:
        (成功フラグ, 変換後の整数またはNone, エラーメッセージまたはNone)
    """
    # 空欄チェック
    if is_empty(value):
        if required:
            return False, None, f"{field_name}を入力してください"
        return True, None, None
    
    # 正規化
    normalized = normalize_number_string(str(value))
    
    # 空になった場合
    if not normalized:
        if required:
            return False, None, f"{field_name}を入力してください"
        return True, None, None
    
    # 整数変換
    try:
        int_value = int(normalized)
    except ValueError:
        return False, None, f"{field_name}は整数で入力してください（例: 10）"
    
    # 範囲チェック
    if min_value is not None and int_value < min_value:
        return False, None, f"{field_name}は{min_value}以上で入力してください"
    
    if max_value is not None and int_value > max_value:
        return False, None, f"{field_name}は{max_value}以下で入力してください"
    
    return True, int_value, None


def validate_positive_integer(
    value: Any,
    field_name: str = "数量",
    required: bool = True,
    max_value: Optional[int] = None
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    正の整数（1以上）のバリデーション
    
    Args:
        value: 入力値
        field_name: フィールド名
        required: 必須かどうか
        max_value: 最大値
    
    Returns:
        (成功フラグ, 変換後の整数またはNone, エラーメッセージまたはNone)
    """
    return validate_integer(
        value=value,
        field_name=field_name,
        required=required,
        min_value=1,
        max_value=max_value
    )


def validate_non_negative_integer(
    value: Any,
    field_name: str = "数量",
    required: bool = True,
    max_value: Optional[int] = None
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    0以上の整数のバリデーション
    
    Args:
        value: 入力値
        field_name: フィールド名
        required: 必須かどうか
        max_value: 最大値
    
    Returns:
        (成功フラグ, 変換後の整数またはNone, エラーメッセージまたはNone)
    """
    return validate_integer(
        value=value,
        field_name=field_name,
        required=required,
        min_value=0,
        max_value=max_value
    )


def validate_float(
    value: Any,
    field_name: str = "数値",
    required: bool = True,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None
) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    小数値のバリデーション
    通貨記号（¥、円）を自動除去して変換
    
    Args:
        value: 入力値
        field_name: フィールド名
        required: 必須かどうか
        min_value: 最小値
        max_value: 最大値
    
    Returns:
        (成功フラグ, 変換後の小数またはNone, エラーメッセージまたはNone)
    """
    if is_empty(value):
        if required:
            return False, None, f"{field_name}を入力してください"
        return True, None, None
    
    # 文字列化してから通貨記号を除去
    str_value = str(value)
    if '¥' in str_value or '円' in str_value:
        str_value = str_value.replace('¥', '').replace('円', '').strip()
    
    normalized = normalize_number_string(str_value)
    
    if not normalized:
        if required:
            return False, None, f"{field_name}を入力してください"
        return True, None, None
    
    try:
        float_value = float(normalized)
    except ValueError:
        return False, None, f"{field_name}は数値で入力してください（例: 1000.5）"
    
    if min_value is not None and float_value < min_value:
        return False, None, f"{field_name}は{min_value}以上で入力してください"
    
    if max_value is not None and float_value > max_value:
        return False, None, f"{field_name}は{max_value}以下で入力してください"
    
    return True, float_value, None


# =============================================================================
# 文字列バリデーション
# =============================================================================

def validate_required_string(
    value: Any,
    field_name: str = "項目",
    min_length: int = 1,
    max_length: Optional[int] = None,
    normalize: bool = True
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    必須文字列のバリデーション
    
    Args:
        value: 入力値
        field_name: フィールド名
        min_length: 最小文字数
        max_length: 最大文字数
        normalize: 半角変換するか
    
    Returns:
        (成功フラグ, 正規化後の文字列またはNone, エラーメッセージまたはNone)
    """
    if is_empty(value):
        return False, None, f"{field_name}を入力してください"
    
    s = str(value).strip()
    if normalize:
        s = normalize_to_halfwidth(s)
    
    if len(s) < min_length:
        return False, None, f"{field_name}は{min_length}文字以上で入力してください"
    
    if max_length is not None and len(s) > max_length:
        return False, None, f"{field_name}は{max_length}文字以下で入力してください"
    
    return True, s, None


def validate_optional_string(
    value: Any,
    field_name: str = "項目",
    max_length: Optional[int] = None,
    normalize: bool = True
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    任意文字列のバリデーション
    
    Args:
        value: 入力値
        field_name: フィールド名
        max_length: 最大文字数
        normalize: 半角変換するか
    
    Returns:
        (成功フラグ, 正規化後の文字列またはNone（空なら空文字列）, エラーメッセージまたはNone)
    """
    if is_empty(value):
        return True, "", None
    
    s = str(value).strip()
    if normalize:
        s = normalize_to_halfwidth(s)
    
    if max_length is not None and len(s) > max_length:
        return False, None, f"{field_name}は{max_length}文字以下で入力してください"
    
    return True, s, None


def validate_alphanumeric(
    value: Any,
    field_name: str = "項目",
    required: bool = True,
    max_length: Optional[int] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    英数字のみのバリデーション（ユーザーIDなど）
    
    Args:
        value: 入力値
        field_name: フィールド名
        required: 必須かどうか
        max_length: 最大文字数
    
    Returns:
        (成功フラグ, 正規化後の文字列またはNone, エラーメッセージまたはNone)
    """
    if is_empty(value):
        if required:
            return False, None, f"{field_name}を入力してください"
        return True, "", None
    
    s = normalize_to_halfwidth(str(value).strip())
    
    if not s.isalnum():
        return False, None, f"{field_name}は英数字のみ使用できます"
    
    if max_length is not None and len(s) > max_length:
        return False, None, f"{field_name}は{max_length}文字以下で入力してください"
    
    return True, s, None


# =============================================================================
# 日付バリデーション
# =============================================================================

def validate_date_string(
    value: Any,
    field_name: str = "日付",
    required: bool = False
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    日付文字列（YYYY-MM-DD形式）のバリデーション
    全角数字、全角ハイフン、スラッシュなど入力揺れを自動補正
    
    Args:
        value: 入力値
        field_name: フィールド名
        required: 必須かどうか
    
    Returns:
        (成功フラグ, 正規化後の日付文字列またはNone, エラーメッセージまたはNone)
    """
    import re
    from datetime import datetime
    
    if is_empty(value):
        if required:
            return False, None, f"{field_name}を入力してください"
        return True, None, None
    
    s = normalize_to_halfwidth(str(value).strip())
    
    # スラッシュをハイフンに変換
    s = s.replace('/', '-')
    
    # 全角ハイフン（－、ー、−）を半角ハイフンに変換
    # IMEやスマホで入力されやすい全角ハイフンを吸収
    s = s.replace('－', '-')  # 全角ハイフン
    s = s.replace('ー', '-')  # 長音記号（カタカナ）
    s = s.replace('−', '-')  # マイナス記号
    s = s.replace('‐', '-')  # ハイフン（U+2010）
    s = s.replace('‑', '-')  # ノンブレーキングハイフン（U+2011）
    s = s.replace('–', '-')  # エヌダッシュ（U+2013）
    s = s.replace('—', '-')  # エムダッシュ（U+2014）
    
    # 形式チェック
    pattern = r'^\d{4}-\d{1,2}-\d{1,2}$'
    if not re.match(pattern, s):
        return False, None, f"{field_name}はYYYY-MM-DD形式で入力してください（例: 2024-01-15）"
    
    # 日付として妥当か
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        # 正規化（2024-1-5 → 2024-01-05）
        normalized_date = dt.strftime("%Y-%m-%d")
        return True, normalized_date, None
    except ValueError:
        return False, None, f"{field_name}は正しい日付を入力してください"


# =============================================================================
# 複合バリデーション（フォーム全体用）
# =============================================================================

class ValidationResult:
    """バリデーション結果を格納するクラス"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.values: dict = {}
    
    def add_error(self, message: str):
        """エラーメッセージを追加"""
        self.errors.append(message)
    
    def set_value(self, key: str, value: Any):
        """正規化後の値をセット"""
        self.values[key] = value
    
    def is_valid(self) -> bool:
        """すべてのバリデーションが成功したか"""
        return len(self.errors) == 0
    
    def get_errors(self) -> List[str]:
        """エラーメッセージ一覧を取得"""
        return self.errors
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """正規化後の値を取得"""
        return self.values.get(key, default)


def create_validation_result() -> ValidationResult:
    """新しいバリデーション結果オブジェクトを作成"""
    return ValidationResult()


# =============================================================================
# Streamlit用ヘルパー
# =============================================================================

def show_validation_errors(errors: List[str]):
    """
    Streamlitでバリデーションエラーを表示
    
    Args:
        errors: エラーメッセージのリスト
    """
    import streamlit as st
    for error in errors:
        st.error(f"❌ {error}")


def validate_form_and_show_errors(result: ValidationResult) -> bool:
    """
    バリデーション結果をチェックし、エラーがあれば表示
    
    Args:
        result: ValidationResultオブジェクト
    
    Returns:
        バリデーション成功ならTrue
    """
    if not result.is_valid():
        show_validation_errors(result.get_errors())
        return False
    return True


# =============================================================================
# 補正検出ヘルパー（警告表示用）
# =============================================================================

def has_currency_symbols(value: Any) -> bool:
    """
    入力値に通貨記号が含まれているか判定
    
    Args:
        value: 入力値
    
    Returns:
        通貨記号（¥、円）が含まれている場合True
    """
    if value is None:
        return False
    str_value = str(value)
    return '¥' in str_value or '円' in str_value


def has_fullwidth_chars(value: Any) -> bool:
    """
    入力値に全角文字が含まれているか判定
    
    Args:
        value: 入力値
    
    Returns:
        全角文字が含まれている場合True
    """
    if value is None:
        return False
    str_value = str(value)
    # 全角数字をチェック
    for c in '０１２３４５６７８９':
        if c in str_value:
            return True
    # 全角カンマ、全角スペースをチェック
    if '，' in str_value or '　' in str_value or '．' in str_value:
        return True
    return False


def needs_correction_warning(original_value: Any, field_type: str = "number") -> Tuple[bool, str]:
    """
    入力値が補正を必要とするか判定し、警告メッセージを生成
    
    Args:
        original_value: 元の入力値
        field_type: フィールドタイプ（"number", "currency", "date"）
    
    Returns:
        (補正が必要か, 警告メッセージ)
    """
    if original_value is None:
        return False, ""
    
    str_value = str(original_value).strip()
    warnings = []
    
    if field_type == "currency":
        if has_currency_symbols(str_value):
            warnings.append("通貨記号を自動で除去しました")
    
    if has_fullwidth_chars(str_value):
        warnings.append("全角文字を半角に変換しました")
    
    if ',' in str_value or '，' in str_value:
        warnings.append("カンマ区切りを除去しました")
    
    if field_type == "date":
        # 全角ハイフンのチェック
        if '－' in str_value or 'ー' in str_value or '−' in str_value:
            warnings.append("全角ハイフンを半角に変換しました")
        if '/' in str_value:
            warnings.append("スラッシュをハイフンに変換しました")
    
    if warnings:
        return True, " / ".join(warnings)
    return False, ""


# =============================================================================
# エイリアス関数（現場向けシンプルAPI）
# =============================================================================

def to_int_safe(
    value: Any,
    field_name: str = "数値",
    min_value: int = 0,
    allow_zero: bool = True
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    安全に整数に変換（現場向けシンプルAPI）
    
    Args:
        value: 入力値
        field_name: フィールド名
        min_value: 最小値（デフォルト: 0）
        allow_zero: ゼロを許可するか（Falseなら1以上）
    
    Returns:
        (ok, int_value, error_message)
    """
    actual_min = min_value if allow_zero else max(min_value, 1)
    return validate_integer(
        value=value,
        field_name=field_name,
        required=True,
        min_value=actual_min
    )


def to_float_safe(
    value: Any,
    field_name: str = "数値",
    min_value: float = 0.0,
    allow_zero: bool = True
) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    安全に小数に変換（現場向けシンプルAPI）
    通貨記号を自動除去して変換
    
    Args:
        value: 入力値
        field_name: フィールド名
        min_value: 最小値（デフォルト: 0.0）
        allow_zero: ゼロを許可するか（Falseなら最小値より大きい）
    
    Returns:
        (ok, float_value, error_message)
        
    Note:
        入力例として「¥1200」や「1200円」などを自動補正します。
        補正が必要な場合は、呼び出し元で警告表示を推奨。
    """
    actual_min = min_value if allow_zero else (min_value if min_value > 0 else 0.01)
    return validate_float(
        value=value,
        field_name=field_name,
        required=True,
        min_value=actual_min
    )


def normalize_number_str(s: Any) -> str:
    """
    数値文字列の正規化（エイリアス）
    
    Args:
        s: 入力文字列
    
    Returns:
        正規化された文字列
    """
    return normalize_number_string(s)


def validate_required_text(
    value: Any,
    field_name: str = "項目",
    max_len: Optional[int] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    必須テキストの検証（エイリアス）
    
    Args:
        value: 入力値
        field_name: フィールド名
        max_len: 最大文字数
    
    Returns:
        (ok, normalized_value, error_message)
    """
    return validate_required_string(
        value=value,
        field_name=field_name,
        max_length=max_len
    )

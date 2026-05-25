"""
アプリケーション共通カスタム例外

サービス層・リポジトリ層で発生するビジネスロジックエラーを
型安全に扱うための例外クラス定義。

使用例:
    from utils.exceptions import ValidationError, NotFoundError

    raise ValidationError("数量は1以上を入力してください")

    try:
        ...
    except InventoryError as e:
        return {"success": False, "message": str(e)}
"""


class InventoryError(Exception):
    """在庫管理システムの基底例外クラス"""
    pass


class ValidationError(InventoryError):
    """入力値バリデーションエラー（数量不正、必須項目欠落など）"""
    pass


class NotFoundError(InventoryError):
    """対象リソースが見つからない（物品ID不存在など）"""
    pass


class InsufficientStockError(InventoryError):
    """在庫不足エラー（出庫数 > 在庫数）"""
    pass


class DuplicateError(InventoryError):
    """重複登録エラー（品目コード重複など）"""
    pass


class PermissionError(InventoryError):
    """権限エラー（承認権限なしなど）"""
    pass


class BusinessRuleError(InventoryError):
    """業務ルール違反（既にクローズ済みセッション、取消期限超過など）"""
    pass


def result_from_exception(e: Exception) -> dict:
    """
    例外を {"success": False, "message": str} 形式の辞書に変換。

    既存の db.py スタイルの戻り値と互換性を保つためのヘルパー。
    """
    return {"success": False, "message": str(e)}


def ok(message: str = "✅ 成功しました", **kwargs) -> dict:
    """成功レスポンス辞書を生成するヘルパー。"""
    return {"success": True, "message": message, **kwargs}


def ng(message: str, **kwargs) -> dict:
    """失敗レスポンス辞書を生成するヘルパー。"""
    return {"success": False, "message": message, **kwargs}

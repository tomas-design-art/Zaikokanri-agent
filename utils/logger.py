"""
ロギング設定モジュール
- ファイル出力とコンソール出力を設定
- 操作ログ（入出庫、承認など）の記録
- エラー・警告の記録
"""

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional


# =============================================================================
# ログ設定
# =============================================================================

# ログファイルのディレクトリ
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

# ログレベル
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _ensure_log_dir():
    """ログディレクトリを作成"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)


def get_logger(name: str = "zaiko") -> logging.Logger:
    """
    アプリケーション用ロガーを取得
    
    Args:
        name: ロガー名
    
    Returns:
        設定済みロガー
    """
    logger = logging.getLogger(name)
    
    # 既に設定済みならそのまま返す
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    
    # フォーマッター
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # ファイルハンドラー（オプション）
    try:
        _ensure_log_dir()
        today = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"app_{today}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # ファイル出力に失敗してもコンソール出力は継続
        pass
    
    return logger


# デフォルトロガー
_default_logger: Optional[logging.Logger] = None


def _get_default_logger() -> logging.Logger:
    """デフォルトロガーを取得（シングルトン）"""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger("zaiko")
    return _default_logger


# =============================================================================
# 便利関数
# =============================================================================

def log_info(message: str, **kwargs):
    """
    情報ログを出力
    
    Args:
        message: ログメッセージ
        **kwargs: 追加情報（key=value形式）
    """
    logger = _get_default_logger()
    if kwargs:
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        message = f"{message} | {extra_info}"
    logger.info(message)


def log_warning(message: str, **kwargs):
    """
    警告ログを出力
    
    Args:
        message: ログメッセージ
        **kwargs: 追加情報
    """
    logger = _get_default_logger()
    if kwargs:
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        message = f"{message} | {extra_info}"
    logger.warning(message)


def log_error(message: str, exc: Optional[Exception] = None, **kwargs):
    """
    エラーログを出力
    
    Args:
        message: ログメッセージ
        exc: 例外オブジェクト（あれば）
        **kwargs: 追加情報
    """
    logger = _get_default_logger()
    if kwargs:
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        message = f"{message} | {extra_info}"
    if exc:
        logger.error(message, exc_info=exc)
    else:
        logger.error(message)


def log_debug(message: str, **kwargs):
    """
    デバッグログを出力
    
    Args:
        message: ログメッセージ
        **kwargs: 追加情報
    """
    logger = _get_default_logger()
    if kwargs:
        extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        message = f"{message} | {extra_info}"
    logger.debug(message)


# =============================================================================
# 操作ログ用関数
# =============================================================================

def log_operation(
    operation: str,
    user_name: str,
    target: str,
    details: Optional[str] = None,
    success: bool = True
):
    """
    操作ログを記録
    
    Args:
        operation: 操作種別（IN/OUT/ADJUST/APPROVE/REJECT等）
        user_name: 実行ユーザー名
        target: 操作対象（物品名など）
        details: 詳細情報
        success: 成功/失敗
    """
    logger = _get_default_logger()
    status = "SUCCESS" if success else "FAILED"
    message = f"[{operation}] user={user_name} target={target} status={status}"
    if details:
        message += f" details={details}"
    
    if success:
        logger.info(message)
    else:
        logger.warning(message)


def log_inbound(user_name: str, item_name: str, quantity: int, success: bool = True):
    """入庫操作ログ"""
    log_operation("IN", user_name, item_name, f"qty={quantity}", success)


def log_outbound(user_name: str, item_name: str, quantity: int, success: bool = True):
    """出庫操作ログ"""
    log_operation("OUT", user_name, item_name, f"qty={quantity}", success)


def log_adjust(user_name: str, item_name: str, old_qty: int, new_qty: int, reason: str, success: bool = True):
    """調整操作ログ"""
    log_operation("ADJUST", user_name, item_name, f"old={old_qty} new={new_qty} reason={reason}", success)


def log_approve(user_name: str, target_id: int, target_type: str, success: bool = True):
    """承認操作ログ"""
    log_operation("APPROVE", user_name, f"{target_type}#{target_id}", None, success)


def log_reject(user_name: str, target_id: int, target_type: str, reason: str, success: bool = True):
    """却下操作ログ"""
    log_operation("REJECT", user_name, f"{target_type}#{target_id}", f"reason={reason}", success)


def log_login(user_name: str, success: bool = True):
    """ログイン操作ログ"""
    log_operation("LOGIN", user_name, "system", None, success)


def log_auth_failure(username: str, reason: str = "認証失敗"):
    """認証失敗ログ"""
    log_warning(f"認証失敗: {reason}", username=username)

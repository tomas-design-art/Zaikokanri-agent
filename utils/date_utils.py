"""
日時ユーティリティ

JST変換・フォーマットの一元管理。
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def get_jst_now_str() -> str:
    """現在の日時（JST）を文字列 'YYYY-MM-DD HH:MM:SS' で取得"""
    return datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')


def parse_db_ts_to_jst(ts: str) -> datetime:
    """
    DBからの日時文字列をJSTのdatetimeオブジェクトに変換する。

    フォーマット: "%Y-%m-%d %H:%M:%S"

    仕様:
    - OFFSET-UNAWARE (タイムゾーン情報なし) の場合:
      DBには基本的にUTCで保存されている（またはそうみなす）ため、
      UTCとしてロードしてからJST ('Asia/Tokyo') に変換する。
    """
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(JST)
        return dt
    except ValueError:
        print(f"Warning: Failed to parse timestamp '{ts}'")
        return datetime.now(JST)

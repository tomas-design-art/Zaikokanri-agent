"""
utils/date_utils のユニットテスト

pytest で実行: pytest tests/test_unit_date_utils.py -v
"""

import sys
import os
import pytest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.date_utils import JST, get_jst_now_str


class TestJST:
    def test_jst_is_utc_plus9(self):
        """JST が UTC+9 のタイムゾーンであることを確認"""
        from datetime import timezone, timedelta
        now = datetime.now(JST)
        utc_now = datetime.now(timezone.utc)
        diff = now.utcoffset().total_seconds()
        assert diff == 9 * 3600, f"JST offset should be +9h, got {diff}s"

    def test_get_jst_now_str_format(self):
        """get_jst_now_str が正しいフォーマットを返すことを確認"""
        result = get_jst_now_str()
        assert isinstance(result, str)
        # YYYY-MM-DD HH:MM:SS 形式であることを確認
        datetime.strptime(result, "%Y-%m-%d %H:%M:%S")

    def test_get_jst_now_str_is_jst(self):
        """get_jst_now_str が現在の JST 時刻に近い値を返すことを確認"""
        before = datetime.now(JST)
        result = get_jst_now_str()
        after = datetime.now(JST)

        parsed = datetime.strptime(result, "%Y-%m-%d %H:%M:%S")
        before_naive = before.replace(tzinfo=None)
        after_naive = after.replace(tzinfo=None)

        assert before_naive <= parsed <= after_naive

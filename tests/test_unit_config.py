"""
config/settings.py のユニットテスト

pytest で実行: pytest tests/test_unit_config.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigSettings:
    """config/settings.py の設定値をテスト"""

    def test_import_settings(self):
        """settings がインポートできることを確認"""
        import config.settings as settings
        assert settings is not None

    def test_db_path_is_string(self):
        """DB_PATH が文字列であることを確認"""
        from config.settings import DB_PATH
        assert isinstance(DB_PATH, str)

    def test_db_path_ends_with_db(self):
        """DB_PATH が .db で終わることを確認"""
        from config.settings import DB_PATH
        assert DB_PATH.endswith(".db"), f"DB_PATH should end with .db, got: {DB_PATH}"

    def test_ai_enabled_is_bool(self):
        """AI_ENABLED がブール値であることを確認"""
        from config.settings import AI_ENABLED
        assert isinstance(AI_ENABLED, bool)

    def test_warning_threshold_is_positive(self):
        """WARNING_THRESHOLD が正の数であることを確認"""
        from config.settings import WARNING_THRESHOLD
        assert isinstance(WARNING_THRESHOLD, (int, float))
        assert WARNING_THRESHOLD > 0

    def test_outbound_max_is_positive_int(self):
        """OUTBOUND_MAX が正の整数であることを確認"""
        from config.settings import OUTBOUND_MAX
        assert isinstance(OUTBOUND_MAX, int)
        assert OUTBOUND_MAX > 0

    def test_inbound_max_is_positive_int(self):
        """INBOUND_MAX が正の整数であることを確認"""
        from config.settings import INBOUND_MAX
        assert isinstance(INBOUND_MAX, int)
        assert INBOUND_MAX > 0

    def test_undo_minutes_is_positive_int(self):
        """UNDO_MINUTES が正の整数であることを確認"""
        from config.settings import UNDO_MINUTES
        assert isinstance(UNDO_MINUTES, int)
        assert UNDO_MINUTES > 0

    def test_log_level_is_valid(self):
        """LOG_LEVEL が有効な値であることを確認"""
        from config.settings import LOG_LEVEL
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        assert LOG_LEVEL in valid_levels, f"LOG_LEVEL '{LOG_LEVEL}' is not valid"

    def test_demo_mode_is_bool(self):
        """DEMO_MODE がブール値であることを確認"""
        from config.settings import DEMO_MODE
        assert isinstance(DEMO_MODE, bool)

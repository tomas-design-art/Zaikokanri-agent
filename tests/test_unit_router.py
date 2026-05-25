"""
ui/router.py のユニットテスト

pytest で実行: pytest tests/test_unit_router.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPageRegistry:
    """PAGE_REGISTRY の静的構造をテスト（Streamlit不要）"""

    def test_registry_import(self):
        """PAGE_REGISTRY がインポートできることを確認"""
        from ui.router import PAGE_REGISTRY
        assert isinstance(PAGE_REGISTRY, dict)

    def test_registry_not_empty(self):
        """PAGE_REGISTRY にエントリが存在することを確認"""
        from ui.router import PAGE_REGISTRY
        assert len(PAGE_REGISTRY) > 0

    def test_registry_values_are_tuples(self):
        """全エントリが (module_path, function_name) タプルであることを確認"""
        from ui.router import PAGE_REGISTRY
        for key, value in PAGE_REGISTRY.items():
            assert isinstance(value, tuple), f"Key '{key}' value is not a tuple"
            assert len(value) == 2, f"Key '{key}' tuple should have 2 elements"
            module_path, func_name = value
            assert isinstance(module_path, str), f"Key '{key}' module_path should be str"
            assert isinstance(func_name, str), f"Key '{key}' func_name should be str"

    def test_registry_keys_are_strings(self):
        """全エントリのキーが文字列であることを確認"""
        from ui.router import PAGE_REGISTRY
        for key in PAGE_REGISTRY:
            assert isinstance(key, str), f"Key should be str, got {type(key)}"

    def test_expected_pages_in_registry(self):
        """基本的なページが登録されていることを確認"""
        from ui.router import PAGE_REGISTRY
        expected_keys = ["inventory", "demo", "settings"]
        for key in expected_keys:
            assert key in PAGE_REGISTRY, f"Expected page '{key}' not in PAGE_REGISTRY"

    def test_module_paths_are_dot_separated(self):
        """モジュールパスがドット区切りのPythonモジュール形式であることを確認"""
        from ui.router import PAGE_REGISTRY
        for key, (module_path, _) in PAGE_REGISTRY.items():
            assert "." in module_path, f"Key '{key}' module_path '{module_path}' should contain dots"
            assert not module_path.startswith("."), f"Key '{key}' module_path should be absolute"

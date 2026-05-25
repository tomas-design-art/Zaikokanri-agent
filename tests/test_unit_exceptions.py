"""
utils/exceptions のユニットテスト

pytest で実行: pytest tests/test_unit_exceptions.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.exceptions import (
    InventoryError,
    ValidationError,
    NotFoundError,
    InsufficientStockError,
    DuplicateError,
    BusinessRuleError,
    result_from_exception,
    ok,
    ng,
)


class TestExceptionHierarchy:
    def test_validation_error_is_inventory_error(self):
        assert issubclass(ValidationError, InventoryError)

    def test_not_found_error_is_inventory_error(self):
        assert issubclass(NotFoundError, InventoryError)

    def test_insufficient_stock_is_inventory_error(self):
        assert issubclass(InsufficientStockError, InventoryError)

    def test_duplicate_error_is_inventory_error(self):
        assert issubclass(DuplicateError, InventoryError)

    def test_business_rule_error_is_inventory_error(self):
        assert issubclass(BusinessRuleError, InventoryError)

    def test_inventory_error_is_exception(self):
        assert issubclass(InventoryError, Exception)


class TestExceptionMessages:
    def test_validation_error_message(self):
        e = ValidationError("数量は1以上を入力してください")
        assert str(e) == "数量は1以上を入力してください"

    def test_not_found_error_message(self):
        e = NotFoundError("物品ID 999 が見つかりません")
        assert "999" in str(e)

    def test_raise_and_catch_as_inventory_error(self):
        with pytest.raises(InventoryError):
            raise ValidationError("test")

    def test_raise_and_catch_specific(self):
        with pytest.raises(ValidationError):
            raise ValidationError("test")


class TestHelperFunctions:
    def test_result_from_exception(self):
        e = ValidationError("入力エラー")
        result = result_from_exception(e)
        assert result["success"] is False
        assert result["message"] == "入力エラー"

    def test_ok_helper_default_message(self):
        result = ok()
        assert result["success"] is True
        assert "message" in result

    def test_ok_helper_custom_message(self):
        result = ok("保存しました")
        assert result["success"] is True
        assert result["message"] == "保存しました"

    def test_ok_helper_extra_kwargs(self):
        result = ok("done", item_id=42, count=5)
        assert result["success"] is True
        assert result["item_id"] == 42
        assert result["count"] == 5

    def test_ng_helper(self):
        result = ng("エラーが発生しました")
        assert result["success"] is False
        assert result["message"] == "エラーが発生しました"

    def test_ng_helper_extra_kwargs(self):
        result = ng("失敗", error_code="E001")
        assert result["success"] is False
        assert result["error_code"] == "E001"

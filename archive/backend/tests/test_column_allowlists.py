import pytest

from src.db.supabase import (
    _validate_columns,
    _ITEM_ALLOWED_COLUMNS,
    _PROFILE_ALLOWED_COLUMNS,
    _SUBSCRIPTION_ALLOWED_COLUMNS,
)


class TestColumnAllowlists:
    def test_valid_item_columns(self) -> None:
        fields = {"status": "done", "urgency_score": 0.5}
        _validate_columns(fields, _ITEM_ALLOWED_COLUMNS, "test")

    def test_invalid_item_column_raises(self) -> None:
        fields = {"status": "done", "malicious_column": "drop table"}
        with pytest.raises(ValueError, match="Disallowed columns"):
            _validate_columns(fields, _ITEM_ALLOWED_COLUMNS, "test")

    def test_valid_profile_columns(self) -> None:
        fields = {"timezone": "US/Eastern", "notification_sent_today": True}
        _validate_columns(fields, _PROFILE_ALLOWED_COLUMNS, "test")

    def test_invalid_profile_column_raises(self) -> None:
        fields = {"timezone": "US/Eastern", "id": "hacked"}
        with pytest.raises(ValueError, match="Disallowed columns"):
            _validate_columns(fields, _PROFILE_ALLOWED_COLUMNS, "test")

    def test_valid_subscription_columns(self) -> None:
        fields = {"tier": "paid", "status": "active"}
        _validate_columns(fields, _SUBSCRIPTION_ALLOWED_COLUMNS, "test")

    def test_sql_injection_column_name_blocked(self) -> None:
        fields = {"status = 'done'; DROP TABLE items; --": "x"}
        with pytest.raises(ValueError, match="Disallowed columns"):
            _validate_columns(fields, _ITEM_ALLOWED_COLUMNS, "test")

    def test_all_item_columns_accepted(self) -> None:
        fields = {col: "test" for col in _ITEM_ALLOWED_COLUMNS}
        _validate_columns(fields, _ITEM_ALLOWED_COLUMNS, "test")

    def test_all_profile_columns_accepted(self) -> None:
        fields = {col: "test" for col in _PROFILE_ALLOWED_COLUMNS}
        _validate_columns(fields, _PROFILE_ALLOWED_COLUMNS, "test")

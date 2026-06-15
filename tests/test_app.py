"""Tests for app.py — DataSelect utility methods."""

import pytest
from pathlib import Path

from autoplot.app import DataSelect


class TestDateLabel:
    def test_roundtrip(self):
        date = (2026, 6, 15)
        label = DataSelect.date2label(date)
        parsed = DataSelect.label2date(label)
        assert parsed == date

    def test_label_format(self):
        assert DataSelect.date2label((2024, 1, 5)) == "2024-1-5"


class TestGroupData:
    def test_empty_input(self):
        result = DataSelect.group_data({})
        assert result == {}


class TestDotKeysToNested:
    def test_simple(self):
        result = DataSelect._dot_keys_to_nested({"a.b": 1})
        assert result == {"a": {"b": 1}}

    def test_mixed(self):
        result = DataSelect._dot_keys_to_nested({"a.b.c": 1, "x": 2})
        assert result == {"a": {"b": {"c": 1}}, "x": 2}

    def test_conflict_skips_nesting(self):
        result = DataSelect._dot_keys_to_nested({"a.b": 1, "a": "flat"})
        assert result == {"a": "flat"}


class TestPruneJson:
    def test_empty_term_returns_all(self):
        data = {"a": 1, "b": 2}
        assert DataSelect._prune_json(data, "") == data

    def test_filters_keys(self):
        data = {"alpha": 1, "beta": 2}
        result = DataSelect._prune_json(data, "alp")
        assert "alpha" in result
        assert "beta" not in result

    def test_recursive(self):
        data = {"outer": {"inner": 1, "other": 2}}
        result = DataSelect._prune_json(data, "inner")
        assert result == {"outer": {"inner": 1}}

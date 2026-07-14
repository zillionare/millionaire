"""B08-strategy-helpers: Test small utility functions in strategy.py."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from quantide.web.pages import strategy as strategy_mod
from quantide.web.pages.strategy import (
    _format_date,
    _format_number,
    _format_percent,
    _format_range,
    _metric_value,
    _normalize_backtest_tab,
    _normalize_stats,
    _params_to_text,
    _parse_checkbox,
    _to_number,
)


# ---------------------------------------------------------------------------
# _parse_checkbox
# ---------------------------------------------------------------------------


def test_parse_checkbox_various():
    assert _parse_checkbox("1") is True
    assert _parse_checkbox("true") is True
    assert _parse_checkbox("on") is True
    assert _parse_checkbox("yes") is True
    assert _parse_checkbox("YES") is True
    assert _parse_checkbox("off") is False
    assert _parse_checkbox("0") is False
    assert _parse_checkbox("") is False
    assert _parse_checkbox(None) is False


# ---------------------------------------------------------------------------
# _normalize_backtest_tab
# ---------------------------------------------------------------------------


def test_normalize_backtest_tab_overview_default():
    assert _normalize_backtest_tab(None) == "overview"


def test_normalize_backtest_tab_valid():
    assert _normalize_backtest_tab("positions") == "positions"


def test_normalize_backtest_tab_uppercase():
    assert _normalize_backtest_tab("POSITIONS") == "positions"


def test_normalize_backtest_tab_unknown():
    """Unknown tab falls back to overview."""
    assert _normalize_backtest_tab("garbage") == "overview"


# ---------------------------------------------------------------------------
# _normalize_stats
# ---------------------------------------------------------------------------


def test_normalize_stats_none():
    assert _normalize_stats(None) == {}


def test_normalize_stats_empty():
    assert _normalize_stats(pd.DataFrame()) == {}


def test_normalize_stats_normalizes_keys():
    """Spaces in keys are replaced by underscores."""
    df = pd.DataFrame({"col": [1.0]}, index=["Sharpe Ratio"])
    got = _normalize_stats(df)
    assert "sharpe_ratio" in got


def test_normalize_stats_strips_special_chars():
    df = pd.DataFrame({"col": [42.0]}, index=["P&L (%)"])
    got = _normalize_stats(df)
    assert "p_l" in got


# ---------------------------------------------------------------------------
# _to_number
# ---------------------------------------------------------------------------


def test_to_number_none():
    assert _to_number(None) is None


def test_to_number_empty_string():
    assert _to_number("") is None


def test_to_number_nan_string():
    assert _to_number("nan") is None
    assert _to_number("N/A") is None
    assert _to_number("na") is None


def test_to_number_simple_float():
    assert _to_number(0.5) == 0.5


def test_to_number_string_float():
    assert _to_number("0.5") == 0.5


def test_to_number_percent_string():
    """'50%' parses to 0.5."""
    assert _to_number("50%") == 0.5


def test_to_number_invalid_string_returns_none():
    assert _to_number("not-a-number") is None


# ---------------------------------------------------------------------------
# _metric_value
# ---------------------------------------------------------------------------


def test_metric_value_present_returns_value():
    got = _metric_value({"sharpe": 1.5}, "sharpe")
    assert got == 1.5


def test_metric_value_first_match_wins():
    got = _metric_value({"a": 1, "b": 2}, "b", "a")
    assert got == 2


def test_metric_value_missing_returns_none():
    assert _metric_value({}, "x", "y") is None


def test_metric_value_unparseable_returns_none():
    got = _metric_value({"x": "garbage"}, "x")
    assert got is None


# ---------------------------------------------------------------------------
# _format_date
# ---------------------------------------------------------------------------


def test_format_date_none():
    assert _format_date(None) == "--"


def test_format_date_date_obj():
    assert _format_date(datetime.date(2024, 6, 15)) == "2024-06-15"


def test_format_date_datetime_obj():
    assert _format_date(datetime.datetime(2024, 6, 15, 10, 30)) == "2024-06-15"


def test_format_date_string():
    assert _format_date("2024-06-15") == "2024-06-15"


def test_format_date_int_returns_str():
    # Falls through to str(value)
    out = _format_date(20240101)
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# _format_range
# ---------------------------------------------------------------------------


def test_format_range_both_none():
    assert _format_range(None, None) == "--"


def test_format_range_with_dates():
    out = _format_range(datetime.date(2024, 1, 1), datetime.date(2024, 6, 30))
    assert "2024-01-01" in out
    assert "2024-06-30" in out
    assert "~" in out


def test_format_range_partial():
    """start=None, end=date — exercises fallback."""
    out = _format_range(None, datetime.date(2024, 6, 30))
    assert "2024-06-30" in out


# ---------------------------------------------------------------------------
# _format_percent
# ---------------------------------------------------------------------------


def test_format_percent_invalid():
    assert _format_percent("not-a-number") == "--"


def test_format_percent_none():
    assert _format_percent(None) == "--"


def test_format_percent_decimal():
    assert _format_percent(0.5) == "50.0%"


def test_format_percent_zero():
    assert _format_percent(0) == "0.0%"


def test_format_percent_string_number():
    assert _format_percent("0.123") == "12.3%"


# ---------------------------------------------------------------------------
# _format_number
# ---------------------------------------------------------------------------


def test_format_number_invalid():
    assert _format_number("x") == "--"


def test_format_number_none():
    assert _format_number(None) == "--"


def test_format_number_decimal():
    assert _format_number(3.14) == "3.14"


def test_format_number_string():
    assert _format_number("10.5") == "10.50"


# ---------------------------------------------------------------------------
# _params_to_text
# ---------------------------------------------------------------------------


def test_params_to_text_empty():
    assert _params_to_text({}) == "--"


def test_params_to_text_simple():
    out = _params_to_text({"x": 1, "y": "abc"})
    assert "x=1" in out
    assert "y=abc" in out


def test_params_to_text_dict_value():
    """Dict values are unwrapped to .get('default')."""
    out = _params_to_text({"x": {"default": "val1"}})
    assert "x=val1" in out


def test_params_to_text_dict_no_default():
    out = _params_to_text({"x": {"other": "v"}})
    assert "x=" in out



# ---------------------------------------------------------------------------
# _format_number + _params_to_text
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _format_number, _params_to_text


def test_format_number_invalid():
    assert _format_number("not-a-number") == "--"


def test_format_number_none():
    assert _format_number(None) == "--"


def test_format_number_decimal():
    assert _format_number(3.14) == "3.14"


def test_format_number_int():
    assert _format_number(42) == "42.00"


def test_format_number_string_int():
    assert _format_number("10") == "10.00"


def test_params_to_text_empty():
    assert _params_to_text({}) == "--"


def test_params_to_text_simple():
    out = _params_to_text({"x": 1, "y": "abc"})
    assert "x=1" in out
    assert "y=abc" in out


def test_params_to_text_dict_value():
    out = _params_to_text({"x": {"default": "val"}})
    assert "x=val" in out


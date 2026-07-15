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



# ---------------------------------------------------------------------------
# _extract_params_from_info / _strategy_version
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _extract_params_from_info, _strategy_version


def test_extract_params_from_info_none():
    assert _extract_params_from_info(None) == {}
    assert _extract_params_from_info("") == {}


def test_extract_params_from_info_dict():
    assert _extract_params_from_info({"k": "v"}) == {"k": "v"}


def test_extract_params_from_info_str_with_config():
    info = '{"config": {"alpha": 1, "beta": 2}}'
    out = _extract_params_from_info(info)
    assert out == {"alpha": 1, "beta": 2}


def test_extract_params_from_info_str_with_payload():
    info = '{"x": 1, "y": 2}'
    out = _extract_params_from_info(info)
    assert out == {"x": 1, "y": 2}


def test_extract_params_from_info_invalid_json():
    out = _extract_params_from_info("not json")
    assert out == {}


def test_extract_params_from_info_str_non_dict_payload():
    out = _extract_params_from_info('"just a string"')
    assert out == {}


def test_extract_params_from_info_int():
    """Non-dict/str returns {}."""
    out = _extract_params_from_info(42)
    assert out == {}


def test_strategy_version_none():
    assert _strategy_version(None) == "v1.0.0"


def test_strategy_version_with_VERSION():
    class FakeStrategy:
        VERSION = "v2.5"
    assert _strategy_version(FakeStrategy) == "v2.5"


def test_strategy_version_with_dunder_version():
    class FakeStrategy:
        __version__ = "v3.0"
    assert _strategy_version(FakeStrategy) == "v3.0"


def test_strategy_version_no_attrs():
    class FakeStrategy:
        pass
    assert _strategy_version(FakeStrategy) == "v1.0.0"


# ---------------------------------------------------------------------------
# Format / parse helpers
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _format_percent,
    _format_number,
    _format_date,
    _format_range,
    _parse_checkbox,
    _normalize_backtest_tab,
    _to_number,
    _metric_value,
    _params_to_text,
)


def test_format_percent_none():
    out = _format_percent(None)
    assert out == "--"


def test_format_percent_zero():
    out = _format_percent(0)
    assert "%" in out


def test_format_percent_positive():
    out = _format_percent(0.1234)
    assert "%" in out
    assert "12.3" in out


def test_format_percent_negative():
    out = _format_percent(-0.05)
    assert "%" in out


def test_format_number_none():
    out = _format_number(None)
    assert out == "--"


def test_format_number_normal():
    out = _format_number(1234.567)
    assert out  # returns formatted string


def test_format_number_thousands():
    out = _format_number(12345.6789)
    assert "12" in out


def test_format_date_none():
    out = _format_date(None)
    assert out == "--"


def test_format_date_date():
    import datetime as dt
    out = _format_date(dt.date(2024, 6, 15))
    assert "2024-06-15" in out


def test_format_date_datetime():
    import datetime as dt
    out = _format_date(dt.datetime(2024, 6, 15, 12, 30))
    assert "2024-06-15" in out


def test_format_range_none():
    out = _format_range(None, None)
    assert "--" in out


def test_format_range_dates():
    import datetime as dt
    out = _format_range(dt.date(2024, 1, 1), dt.date(2024, 12, 31))
    assert "2024-01-01" in out
    assert "2024-12-31" in out


def test_parse_checkbox_trues():
    assert _parse_checkbox("on") is True
    assert _parse_checkbox("true") is True
    assert _parse_checkbox("1") is True
    assert _parse_checkbox("yes") is True


def test_parse_checkbox_falses():
    assert _parse_checkbox("off") is False
    assert _parse_checkbox("false") is False
    assert _parse_checkbox("0") is False
    assert _parse_checkbox("") is False
    assert _parse_checkbox(None) is False


def test_normalize_backtest_tab_valid():
    out = _normalize_backtest_tab("overview")
    assert out == "overview"


def test_normalize_backtest_tab_invalid():
    out = _normalize_backtest_tab("nonexistent")
    assert out == "overview"  # default


def test_normalize_backtest_tab_none():
    out = _normalize_backtest_tab(None)
    assert out == "overview"


def test_normalize_backtest_tab_trades():
    out = _normalize_backtest_tab("trades")
    assert out == "trades"


def test_to_number_valid():
    out = _to_number("1.5")
    assert out == 1.5


def test_to_number_int():
    out = _to_number(42)
    assert out == 42.0


def test_to_number_invalid():
    out = _to_number("not a number")
    assert out is None


def test_to_number_none():
    out = _to_number(None)
    assert out is None


def test_metric_value_first_key():
    stats = {"alpha": 0.5, "sharpe": 1.2}
    out = _metric_value(stats, "alpha")
    assert out == 0.5


def test_metric_value_fallback_key():
    stats = {"sharpe": 1.2}
    out = _metric_value(stats, "alpha", "sharpe")
    assert out == 1.2


def test_metric_value_no_match():
    stats = {"x": 1}
    out = _metric_value(stats, "missing")
    assert out is None


def test_params_to_text_empty():
    out = _params_to_text({})
    assert out == "--"


def test_params_to_text_with_data():
    out = _params_to_text({"period": 14, "threshold": 0.05})
    assert "period" in out
    assert "14" in out
    assert "threshold" in out


# ---------------------------------------------------------------------------
# trade_main helper tests
# ---------------------------------------------------------------------------


import pytest
from quantide.web.pages.trade_main import (
    _normalize_positions_tab,
    _format_trade_metric,
    _trade_result_has_order,
)


def test_normalize_positions_tab_valid():
    assert _normalize_positions_tab("positions") == "positions"
    assert _normalize_positions_tab("orders") == "orders"


def test_normalize_positions_tab_invalid():
    assert _normalize_positions_tab("unknown") == "positions"


def test_normalize_positions_tab_none():
    assert _normalize_positions_tab(None) == "positions"


def test_format_trade_metric_negative():
    out = _format_trade_metric(-0.5)
    assert out == "-0.50"


def test_format_trade_metric_positive():
    out = _format_trade_metric(0.05)
    assert out == "0.05"


def test_format_trade_metric_none():
    out = _format_trade_metric(None)
    assert out == ""


def test_trade_result_has_order_with_order():
    """When result has qt_oid attr, returns True."""
    res = MagicMock()
    res.qt_oid = 42
    assert _trade_result_has_order(res) is True


def test_trade_result_has_order_no_order():
    res = MagicMock()
    res.qt_oid = None
    assert _trade_result_has_order(res) is False


def test_trade_result_has_order_none():
    assert _trade_result_has_order(None) is False


# ---------------------------------------------------------------------------
# gateway_broker helpers (skip — class not importable)
# ---------------------------------------------------------------------------


def test_empty_history_frame():
    """Skip — GatewayBroker not importable without live app context."""
    pass


def test_gateway_broker_basic():
    """Skip — GatewayBroker not importable without live app context."""
    pass


# ---------------------------------------------------------------------------
# system/jobs helpers
# ---------------------------------------------------------------------------


from quantide.web.pages.system.jobs import (
    JobHistoryRecord,
    _format_cron,
    _build_status_dot,
    _build_job_status_badge,
)


def test_job_history_record_from_dict_defaults():
    rec = JobHistoryRecord.from_dict({})
    assert rec.id is not None
    assert rec.job_id == ""
    assert rec.status == "success"


def test_job_history_record_from_dict_full():
    rec = JobHistoryRecord.from_dict({
        "id": "abc",
        "job_id": "j1",
        "job_name": "Job 1",
        "executed_at": "2024-06-15T10:00:00",
        "status": "error",
        "message": "boom",
        "duration_ms": 100,
    })
    assert rec.id == "abc"
    assert rec.job_id == "j1"
    assert rec.status == "error"


def test_job_history_record_to_dict():
    rec = JobHistoryRecord()
    d = rec.to_dict()
    assert "id" in d
    assert "job_id" in d
    assert "executed_at" in d


def test_format_cron_weekday():
    out = _format_cron("0 9 * * 1-5")
    assert "周一" in out


def test_format_cron_daily():
    out = _format_cron("30 8 * * *")
    assert "每天" in out


def test_format_cron_monday_only():
    out = _format_cron("0 9 * * 1")
    assert "周一" in out


def test_format_cron_every_n_min():
    """When cron has */5 — falls through to dow=='*' branch."""
    out = _format_cron("*/5 * * * *")
    # "*/5 *" matches dow=='*' first
    assert "每天" in out


def test_format_cron_invalid():
    out = _format_cron("not_a_cron")
    assert out == "not_a_cron"


def test_build_status_dot_enabled():
    out = _build_status_dot(True)
    assert "🟢" in out


def test_build_status_dot_disabled():
    out = _build_status_dot(False)
    assert "🔴" in out


def test_build_job_status_badge_enabled():
    out = _build_job_status_badge(True)
    assert "运行" in str(out) or "Running" in str(out)


def test_build_job_status_badge_disabled():
    out = _build_job_status_badge(False)
    assert "停止" in str(out) or "Stopped" in str(out)

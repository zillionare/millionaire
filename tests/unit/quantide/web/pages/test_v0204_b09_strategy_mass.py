"""[AC-NFR1101-01] B09-strategy-mass: cover strategy.py small helpers.

Targets pure utility helpers and strategy_runtime manager helpers that
remain under-covered after B08 (87 missing lines in strategy.py, many of
which sit inside helpers like _format_log_lines / _build_log_meta /
_account_key / _runtime_to_row / _extract_params_from_info).
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from quantide.service.strategy_runtime import (
    StrategyRuntime,
    StrategyRuntimeManager,
)
from quantide.web.pages import strategy as strategy_mod
from quantide.web.pages.strategy import (
    _build_log_meta,
    _extract_params_from_info,
    _format_date,
    _format_log_lines,
    _format_number,
    _format_percent,
    _format_range,
    _strategy_version,
)


# ---------------------------------------------------------------------------
# _format_number / _format_percent - exact-value contracts
# ---------------------------------------------------------------------------


def test_format_number_rounds_to_two_decimals():
    """[AC-NFR1101-01] _format_number rounds 1234.5678 to '1234.57'."""
    assert _format_number(1234.5678) == "1234.57"


def test_format_percent_decimal_to_percent_string():
    """[AC-NFR1101-01] _format_percent converts 0.1234 to '12.3%'."""
    assert _format_percent(0.1234) == "12.3%"


# ---------------------------------------------------------------------------
# _format_date / _format_range - exact contracts
# ---------------------------------------------------------------------------


def test_format_date_string_passthrough():
    """[AC-NFR1101-01] _format_date returns ISO string unchanged."""
    assert _format_date("2024-06-15") == "2024-06-15"


def test_format_range_both_dates_with_separator():
    """[AC-NFR1101-01] _format_range joins dates with ' ~ '."""
    out = _format_range("2024-01-01", "2024-12-31")
    assert out == "2024-01-01 ~ 2024-12-31"


# ---------------------------------------------------------------------------
# _extract_params_from_info - various dict shapes
# ---------------------------------------------------------------------------


def test_extract_params_from_info_dict_passthrough():
    """[AC-NFR1101-01] dict input is returned as-is."""
    payload = {"alpha": 1, "beta": 2}
    assert _extract_params_from_info(payload) == payload


def test_extract_params_from_info_str_with_config_key():
    """[AC-NFR1101-01] JSON string with 'config' key returns nested config."""
    out = _extract_params_from_info('{"config": {"a": 1}}')
    assert out == {"a": 1}


# ---------------------------------------------------------------------------
# _strategy_version
# ---------------------------------------------------------------------------


def test_strategy_version_class_with_version_attr():
    """[AC-NFR1101-01] Class with VERSION attr returns that version."""

    class FakeStrategy:
        VERSION = "v9"

    assert _strategy_version(FakeStrategy) == "v9"


# ---------------------------------------------------------------------------
# _format_log_lines
# ---------------------------------------------------------------------------


def test_format_log_lines_appends_extra_when_present():
    """[AC-NFR1101-01] When extra field present, appended after ' | '."""
    out = _format_log_lines([
        {
            "dt": "2024-01-01",
            "level": "WARN",
            "source": "broker",
            "message": "warn msg",
            "extra": "detail",
        },
    ])
    assert out == ["2024-01-01 | WARN | broker | warn msg | detail"]


# ---------------------------------------------------------------------------
# _build_log_meta - mocked strategy_runtime_manager + saved_backtest_log_*
# ---------------------------------------------------------------------------


def test_build_log_meta_returns_save_metadata_when_run_present():
    """[AC-NFR1101-01] _build_log_meta surfaces save_requested + saved path."""
    fake_run = SimpleNamespace(save_logs=True)
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "saved_backtest_log_exists", return_value=True), \
         patch.object(strategy_mod, "saved_backtest_log_path", return_value="/tmp/x.log"):
        mock_mgr.get_backtest_run = MagicMock(return_value=fake_run)
        out = _build_log_meta("p1")
    assert out["save_requested"] is True
    assert out["saved"] is True
    assert out["saved_path"] == "/tmp/x.log"

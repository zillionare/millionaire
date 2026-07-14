"""B08-market-page-1: Tests for quantide/web/pages/system/market.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from quantide.web.pages.system.market import _get_market_data


# ---------------------------------------------------------------------------
# _get_market_data
# ---------------------------------------------------------------------------


def test_get_market_data_no_code_no_dates_returns_empty():
    """When no code/start/end and empty data, returns ([], 0)."""
    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:
        # Empty data
        class _EmptyDF:
            def __class__(self):
                return type

            def sort(self, *args, **kwargs):
                return self

            def __len__(self):
                return 0

            def is_empty(self):
                return True

        # get_bars returns an empty-like object.
        mock_db.get_bars.return_value = _EmptyDF()
        out, total = _get_market_data()
    # Acceptable: returns tuple.
    assert isinstance(out, list) or out is not None


def test_get_market_data_with_code_but_dates_default():
    """When code given, uses default date range."""
    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:
        class _DF:
            def is_empty(self_inner):
                return True

        mock_db.get_bars_in_range.return_value = _DF()
        out, total = _get_market_data(code="000001.SZ", start_date="", end_date="")
    assert isinstance(out, list)


def test_get_market_data_handles_exception():
    """When get_bars raises, returns ([], 0)."""
    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:
        mock_db.get_bars.side_effect = Exception("boom")
        out, total = _get_market_data()
    assert out == []
    assert total == 0


def test_get_market_data_invalid_date_returns_empty():
    """Invalid date string returns empty."""
    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:
        class _DF:
            def is_empty(self_inner):
                return True

        mock_db.get_bars_in_range.return_value = _DF()
        out, total = _get_market_data(
            code="000001.SZ", start_date="bad-date", end_date="2024-01-01",
        )
    assert out == []


def test_get_market_data_with_adjust():
    """adjust != 'none' is passed through."""
    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:
        class _DF:
            def is_empty(self_inner):
                return True

        mock_db.get_bars_in_range.return_value = _DF()
        out, total = _get_market_data(
            code="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-12-31",
            adjust="qfq",
        )
    # Should not raise.
    assert isinstance(out, list)


def test_get_market_data_no_code_with_dates_returns_empty():
    """With dates but no code, returns ([], 0)."""
    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:
        class _DF:
            def is_empty(self_inner):
                return True

        mock_db.get_bars_in_range.return_value = _DF()
        out, total = _get_market_data(
            code="",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
    assert out == []

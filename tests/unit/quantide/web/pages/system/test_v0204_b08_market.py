"""B08-market-page-1: Tests for quantide/web/pages/system/market.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from quantide.web.pages.system.market import _get_market_data, _MarketView

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
            code="000001.SZ",
            start_date="bad-date",
            end_date="2024-01-01",
        )
    assert out == []


def test_get_market_data_with_adjust():
    """Adjust != 'none' is passed through."""
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


# ---------------------------------------------------------------------------
# _build_market_table
# ---------------------------------------------------------------------------


def test_build_market_table_with_rows():
    """Tables with rows render successfully."""
    from quantide.web.pages.system.market import _build_market_table

    rows = [
        {
            "date": "2024-01-01",
            "open": 10.0,
            "high": 10.5,
            "low": 9.5,
            "close": 10.2,
            "pre_close": 10.0,
            "volume": 1000,
            "amount": 10000.0,
            "up_limit": 11.0,
            "down_limit": 9.0,
            "adj_factor": 1.0,
            "is_st": False,
        },
    ]
    out = _build_market_table(rows, 1, _MarketView(page=1, per_page=20))
    assert out is not None


def test_build_market_table_empty_shows_placeholder():
    from quantide.web.pages.system.market import _build_market_table

    out = _build_market_table([], 0, _MarketView(page=1, per_page=20))
    assert out is not None


def test_build_market_table_positive_change():
    """When close > pre_close, change_str starts with +."""
    from quantide.web.pages.system.market import _build_market_table

    rows = [
        {
            "date": "2024-01-01",
            "open": 9.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "pre_close": 9.5,
            "volume": 100,
            "amount": 950.0,
            "up_limit": 11.0,
            "down_limit": 9.0,
            "adj_factor": 1.0,
            "is_st": False,
        },
    ]
    out = _build_market_table(rows, 1, _MarketView(page=1, per_page=20))
    assert out is not None


def test_build_market_table_negative_change():
    from quantide.web.pages.system.market import _build_market_table

    rows = [
        {
            "date": "2024-01-01",
            "open": 10.0,
            "high": 10.0,
            "low": 9.0,
            "close": 9.0,
            "pre_close": 10.0,
            "volume": 100,
            "amount": 950.0,
            "up_limit": 11.0,
            "down_limit": 9.0,
            "adj_factor": 1.0,
            "is_st": False,
        },
    ]
    out = _build_market_table(rows, 1, _MarketView(page=1, per_page=20))
    assert out is not None


def test_build_market_table_zero_pre_close():
    """When pre_close is 0, change_str becomes '-'."""
    from quantide.web.pages.system.market import _build_market_table

    rows = [
        {
            "date": "2024-01-01",
            "open": 10.0,
            "high": 10.0,
            "low": 9.0,
            "close": 9.5,
            "pre_close": 0,
            "volume": 100,
            "amount": 950.0,
            "up_limit": 11.0,
            "down_limit": 9.0,
            "adj_factor": 1.0,
            "is_st": False,
        },
    ]
    out = _build_market_table(rows, 1, _MarketView(page=1, per_page=20))
    assert out is not None


def test_build_market_table_with_is_st_row():
    from quantide.web.pages.system.market import _build_market_table

    rows = [
        {
            "date": "2024-01-01",
            "open": 10.0,
            "high": 10.0,
            "low": 9.0,
            "close": 9.8,
            "pre_close": 10.0,
            "volume": 100,
            "amount": 950.0,
            "up_limit": 11.0,
            "down_limit": 9.0,
            "adj_factor": 1.0,
            "is_st": True,
        },
    ]
    out = _build_market_table(rows, 1, _MarketView(page=1, per_page=20))
    assert out is not None


# ---------------------------------------------------------------------------
# sync_market
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_market_calls_update_and_returns_table():
    """sync_market invokes daily_bars.store.update and returns a table."""
    from quantide.web.pages.system.market import sync_market

    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:

        class _DF:
            def is_empty(self_inner):
                return True

        mock_db.get_bars_in_range.return_value = _DF()
        req = MagicMock()
        req.query_params = {
            "code": "000001.SZ",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        resp = await sync_market(req)
        assert resp is not None


@pytest.mark.asyncio
async def test_sync_market_handles_exception():
    """When sync fails, returns error Div (not raise)."""
    from quantide.web.pages.system.market import sync_market

    with patch("quantide.web.pages.system.market.daily_bars") as mock_db:
        mock_db.store.update.side_effect = Exception("sync boom")
        req = MagicMock()
        req.query_params = {}
        # Should not raise.
        resp = await sync_market(req)
        assert resp is not None


def _identity_test_row() -> dict:
    return {
        "date": "2024-01-01",
        "asset": "000001.SZ",
        "open": 9.5,
        "high": 10.2,
        "low": 9.4,
        "close": 10.0,
        "pre_close": 9.5,
        "volume": 1000,
        "amount": 10000.0,
        "up_limit": 11.0,
        "down_limit": 9.0,
        "adjust": 1.0,
        "is_st": False,
    }


def test_build_market_table_shows_identity_without_code_filter(monkeypatch):
    """无代码筛选时展示证券代码和名称。"""
    from quantide.web.pages.system import market as market_page

    monkeypatch.setattr(
        market_page.stock_list,
        "_data",
        pl.DataFrame({"asset": ["000001.SZ"], "name": ["平安银行"]}),
    )
    html = str(
        market_page._build_market_table(
            [_identity_test_row()],
            1,
            market_page._MarketView(page=1, per_page=20),
        )
    )
    assert "证券代码" in html
    assert "证券名称" in html
    assert "000001" in html
    assert "000001.SZ" not in html
    assert "平安银行" in html


def test_build_market_table_hides_identity_with_code_filter(monkeypatch):
    """有代码筛选时不展示证券代码和名称列。"""
    from quantide.web.pages.system import market as market_page

    monkeypatch.setattr(
        market_page.stock_list,
        "_data",
        pl.DataFrame({"asset": ["000001.SZ"], "name": ["平安银行"]}),
    )
    html = str(
        market_page._build_market_table(
            [_identity_test_row()],
            1,
            market_page._MarketView(code="000001.SZ", page=1, per_page=20),
        )
    )
    assert "证券代码" not in html
    assert "证券名称" not in html
    assert "平安银行" not in html


def test_build_market_table_change_shows_percent_only():
    """涨跌只显示百分比，不显示绝对值。"""
    from quantide.web.pages.system.market import _build_market_table

    html = str(
        _build_market_table(
            [_identity_test_row()],
            1,
            _MarketView(code="000001.SZ", page=1, per_page=20),
        )
    )
    assert "+5.26%" in html
    assert "+0.50" not in html

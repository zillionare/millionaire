"""B08-strategy-build-helpers: Test _build_date_axis and _build_series_payload with mocks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from quantide.web.pages import strategy as strategy_mod
from quantide.web.pages.strategy import (
    _build_date_axis,
    _build_series_payload,
)


def test_build_date_axis_with_portfolio():
    """When portfolio exists, returns list from calendar.get_frames."""
    fake_portfolio = MagicMock()
    fake_portfolio.start = __import__("datetime").date(2024, 1, 1)
    fake_portfolio.end = __import__("datetime").date(2024, 6, 30)

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        with patch.object(strategy_mod, "calendar") as mock_cal:
            mock_cal.get_frames = MagicMock(return_value=[
                __import__("datetime").date(2024, 1, 1),
                __import__("datetime").date(2024, 1, 2),
            ])
            out = _build_date_axis("p1")
    assert out == ["2024-01-01", "2024-01-02"]


def test_build_date_axis_no_portfolio_no_end():
    """When portfolio has no end, uses start as end."""
    fake_portfolio = MagicMock()
    fake_portfolio.start = __import__("datetime").date(2024, 1, 1)
    fake_portfolio.end = None

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        with patch.object(strategy_mod, "calendar") as mock_cal:
            mock_cal.get_frames = MagicMock(return_value=[
                __import__("datetime").date(2024, 1, 1),
            ])
            _build_date_axis("p1")
    mock_cal.get_frames.assert_called_once()


def test_build_date_axis_no_portfolio_use_assets():
    """When no portfolio but assets exist, derives from first/last row."""
    fake_assets = pl.DataFrame({
        "dt": [
            __import__("datetime").date(2024, 1, 1),
            __import__("datetime").date(2024, 1, 3),
            __import__("datetime").date(2024, 1, 5),
        ]
    })

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=None)
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "calendar") as mock_cal:
            mock_cal.get_frames = MagicMock(return_value=[
                __import__("datetime").date(2024, 1, 1),
                __import__("datetime").date(2024, 1, 5),
            ])
            _build_date_axis("p1")


def test_build_date_axis_no_portfolio_no_assets():
    """Returns empty list when no portfolio and no assets."""
    fake_assets = pl.DataFrame()  # empty

    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.get_portfolio = MagicMock(return_value=None)
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        _build_date_axis("p1")


# ---------------------------------------------------------------------------
# _build_series_payload
# ---------------------------------------------------------------------------


def test_build_series_payload_no_assets():
    """When no assets, returns placeholder payload."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=pl.DataFrame())
        out = _build_series_payload("p1", date_axis=["2024-01-01"])
    assert out["total"] == [None]
    assert out["trade_count"] == [0]


def test_build_series_payload_no_date_axis():
    """When no date_axis, returns empty placeholder."""
    fake_assets = pl.DataFrame({"dt": [__import__("datetime").date(2024, 1, 1)]})
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        out = _build_series_payload("p1", date_axis=[])
    assert out["total"] == []
    assert out["trade_count"] == []


def test_build_series_payload_with_assets():
    """With assets, populates series."""
    fake_assets = pl.DataFrame({
        "dt": [
            __import__("datetime").date(2024, 1, 1),
            __import__("datetime").date(2024, 1, 2),
        ],
        "total": [100.0, 110.0],
        "benchmark_total": [100.0, 105.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        out = _build_series_payload("p1", date_axis=["2024-01-01", "2024-01-02"])
    assert "total" in out
    assert "benchmark" in out


# ---------------------------------------------------------------------------
# _build_benchmark_returns
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _build_benchmark_returns


def test_build_benchmark_returns_no_assets():
    """When no assets, returns None."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=pl.DataFrame())
        out = _build_benchmark_returns("p1")
    assert out is None


def test_build_benchmark_returns_daily_bars_exception():
    """When daily_bars.get_bars_in_range raises, returns None."""
    fake_assets = pl.DataFrame({"dt": [__import__("datetime").date(2024, 1, 1)]})
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "daily_bars") as mock_dbars:
            mock_dbars.get_bars_in_range = MagicMock(side_effect=Exception("boom"))
            out = _build_benchmark_returns("p1")
    assert out is None


def test_build_benchmark_returns_empty_dataframe():
    """When daily_bars returns empty df, returns None."""
    import datetime
    fake_assets = pl.DataFrame({"dt": [datetime.date(2024, 1, 1)]})
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "daily_bars") as mock_dbars:
            mock_dbars.get_bars_in_range = MagicMock(return_value=pl.DataFrame())
            out = _build_benchmark_returns("p1")
    assert out is None


def test_build_benchmark_returns_with_data():
    """With proper data, returns percent-change df."""
    import datetime
    fake_assets = pl.DataFrame({
        "dt": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ]
    })
    fake_bars = pl.DataFrame({
        "date": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ],
        "close": [100.0, 110.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.query_assets = MagicMock(return_value=fake_assets)
        with patch.object(strategy_mod, "daily_bars") as mock_dbars:
            mock_dbars.get_bars_in_range = MagicMock(return_value=fake_bars)
            out = _build_benchmark_returns("p1")
    assert out is not None


# ---------------------------------------------------------------------------
# _build_metrics_payload — uses metrics(...) which is heavy; mock it
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import _build_metrics_payload, BENCHMARK_ASSET


def test_build_metrics_payload_with_stats():
    """Build metrics from a normal stats DataFrame."""
    import pandas as pd
    fake_df = pd.DataFrame({"v": [1.0]}, index=["Sharpe Ratio"])
    with patch.object(strategy_mod, "metrics") as mock_metrics, \
         patch.object(strategy_mod, "_build_benchmark_returns", return_value=None):
        mock_metrics.return_value = fake_df
        out = _build_metrics_payload("p1")
    assert "annual_return" in out
    assert "sharpe" in out
    assert "max_drawdown" in out


# ---------------------------------------------------------------------------
# _resolve_backtest_status + _build_trade_rows + _build_daily_positions + ...
# ---------------------------------------------------------------------------


from quantide.web.pages.strategy import (
    _build_daily_positions,
    _build_daily_summary,
    _build_log_rows,
    _build_trade_rows,
    _resolve_backtest_status,
)


def test_resolve_backtest_status_no_run_no_portfolio():
    """No run, no portfolio → ('missing', '未找到回测记录。')."""
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=None)
        mock_db.get_portfolio = MagicMock(return_value=None)
        status, err = _resolve_backtest_status("p1")
    assert status == "missing"
    assert "未找到" in err


def test_resolve_backtest_status_running():
    """When portfolio.status is True, status='running'."""
    fake_portfolio = MagicMock()
    fake_portfolio.status = True
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=None)
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        status, err = _resolve_backtest_status("p1")
    assert status == "running"
    assert err == ""


def test_resolve_backtest_status_finished():
    """When portfolio.status is False, status='finished'."""
    fake_portfolio = MagicMock()
    fake_portfolio.status = False
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=None)
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        status, err = _resolve_backtest_status("p1")
    assert status == "finished"


def test_resolve_backtest_status_run_running():
    """When run.status='running', return running."""
    fake_run = MagicMock()
    fake_run.status = "running"
    fake_run.error = None
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr:
        mock_mgr.get_backtest_run = MagicMock(return_value=fake_run)
        status, err = _resolve_backtest_status("p1")
    assert status == "running"


def test_resolve_backtest_status_run_unknown():
    """When run.status is unknown, falls through to portfolio check."""
    fake_run = MagicMock()
    fake_run.status = "weird"
    fake_run.error = "x"
    fake_portfolio = MagicMock()
    fake_portfolio.status = False
    with patch.object(strategy_mod, "strategy_runtime_manager") as mock_mgr, \
         patch.object(strategy_mod, "db") as mock_db:
        mock_mgr.get_backtest_run = MagicMock(return_value=fake_run)
        mock_db.get_portfolio = MagicMock(return_value=fake_portfolio)
        status, err = _resolve_backtest_status("p1")
    assert status == "finished"


# ---------------------------------------------------------------------------
# _build_trade_rows
# ---------------------------------------------------------------------------


def test_build_trade_rows_empty():
    """When db.trades_all is empty, returns []."""
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=pl.DataFrame())
        out = _build_trade_rows("p1")
    assert out == []


def test_build_trade_rows_with_data():
    """With trade rows, formats them."""
    import datetime
    from quantide.core.enums import OrderSide
    fake_trades = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "side": [OrderSide.BUY],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
        "fee": [1.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=fake_trades)
        out = _build_trade_rows("p1")
    assert len(out) == 1
    assert out[0]["asset"] == "000001.SZ"


def test_build_trade_rows_side_int():
    """When side is int (not enum), parsed."""
    import datetime
    fake_trades = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "side": [1],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
        "fee": [1.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=fake_trades)
        out = _build_trade_rows("p1")
    assert out[0]["side_value"] == 1
    assert out[0]["side"] == "买入"


def test_build_trade_rows_side_sell():
    """When side=-1 (sell), formatted correctly."""
    import datetime
    fake_trades = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "side": [-1],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
        "fee": [1.0],
    })
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.trades_all = MagicMock(return_value=fake_trades)
        out = _build_trade_rows("p1")
    assert out[0]["side"] == "卖出"


# ---------------------------------------------------------------------------
# _build_daily_positions + _build_daily_summary
# ---------------------------------------------------------------------------


def test_build_daily_positions_empty():
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.snapshot_all = MagicMock(return_value=pl.DataFrame())
        out = _build_daily_positions("p1")
    assert isinstance(out, list)


def test_build_daily_summary_empty():
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.snapshot_all = MagicMock(return_value=pl.DataFrame())
        out = _build_daily_summary("p1")
    assert isinstance(out, list)


# ---------------------------------------------------------------------------
# _build_log_rows
# ---------------------------------------------------------------------------


def test_build_log_rows_empty():
    with patch.object(strategy_mod, "db") as mock_db:
        mock_db.backtest_logs = MagicMock(return_value=pl.DataFrame())
        out = _build_log_rows("p1")
    assert isinstance(out, list)

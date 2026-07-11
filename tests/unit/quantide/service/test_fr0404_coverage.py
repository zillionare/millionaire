"""FR-0404 coverage tests for service helpers with deterministic local inputs."""

import datetime

import pandas as pd
import pytest

import quantide.service.grid_search as grid_search_module
from quantide.data.models import BacktestLogEntry
from quantide.service.backtest_logs import _entry_to_row
from quantide.service.grid_search import GridSearch
from quantide.service.metrics import _calculate_metrics
from quantide.service.trade_lightning import compute_cached_price
from quantide.service.triple_barrier import BarrierHit, evaluate_day


class _CompletedFuture:
    """FR-0404 executor double that returns a prepared backtest result."""

    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result


class _Executor:
    """FR-0404 process-pool double recording submitted parameter combinations."""

    submitted = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def submit(self, _function, *_args, **_kwargs):
        config = _args[1]
        self.submitted.append(config)
        return _CompletedFuture({"portfolio_id": config["alpha"], "metrics": {"score": 1}})


def test_backtest_log_row_preserves_required_display_fields() -> None:
    """FR-0404 AC-1: a log entry retains time, level, message, and extra fields for display."""
    entry = BacktestLogEntry(
        event_id="event-1",
        portfolio_id="portfolio-1",
        dt=datetime.datetime(2024, 1, 2, 9, 30),
        level="info",
        source="runner",
        message="started",
        extra='{"step": 1}',
    )

    assert _entry_to_row(entry) == {
        "dt": "2024-01-02 09:30:00",
        "level": "INFO",
        "source": "runner",
        "message": "started",
        "extra": '{"step": 1}',
    }


def test_grid_search_submits_each_parameter_combination_once(monkeypatch) -> None:
    """FR-0404 AC-2: GridSearch evaluates the full Cartesian parameter grid exactly once."""
    _Executor.submitted = []
    monkeypatch.setattr(grid_search_module, "ProcessPoolExecutor", _Executor)
    monkeypatch.setattr(grid_search_module, "as_completed", lambda futures: futures)
    search = GridSearch(
        strategy_cls=object,
        base_config={"fixed": True},
        param_grid={"alpha": [1, 2], "beta": ["x", "y"]},
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 2),
    )

    result = search.run()

    assert {(row["alpha"], row["beta"]) for row in _Executor.submitted} == {
        (1, "x"), (1, "y"), (2, "x"), (2, "y"),
    }
    assert result.shape[0] == 4


def test_metrics_formats_fixed_return_series_without_database() -> None:
    """FR-0404 AC-4: fixed returns yield independently checkable return and drawdown metrics."""
    returns = pd.Series(
        [0.10, -0.10], index=pd.to_datetime(["2024-01-02", "2024-01-03"])
    )

    stats = _calculate_metrics(returns)

    assert stats.loc["Total Return", "Value"] == "-1.00%"
    assert stats.loc["Max Drawdown", "Value"] == "-10.00%"
    assert stats.loc["Win Rate (Daily)", "Value"] == "50.00%"


def test_trade_lightning_current_and_unknown_references_need_no_market_call() -> None:
    """FR-0404 AC-5: current and unknown price references have deterministic empty cached prices."""
    assert compute_cached_price("000001.SZ", "current") == 0.0
    assert compute_cached_price("000001.SZ", "unknown") == 0.0


def test_triple_barrier_equal_distance_prefers_conservative_down_barrier() -> None:
    """FR-0404 AC-6: equal same-day barrier distances choose the documented conservative down result."""
    evaluation = evaluate_day(10.6, 9.4, 10.0, 10.0, 10.0, 5.0, 5.0)

    assert evaluation.barrier_hit is BarrierHit.DOWN
    assert evaluation.excess_return == pytest.approx(0.05)

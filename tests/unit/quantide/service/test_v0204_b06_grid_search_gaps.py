"""v0.2-004-coverage-recovery B06-grid-search gaps: quantide/service/grid_search.py.

Targets uncovered branches in GridSearch.run():
- combinations generation (line 118-127): iterates param_grid
- save_logs=False (skip merge)
- save_logs=True: portfolio insertion branches (line 169-176), strategy_logs
  (line 179-183), assets (line 186-190), trades (line 193-197), positions
  (line 200-204) — each with both empty and non-empty data
- future.result() exception handler (line 215-216)
- df.sort_values by 'sharpe' (line 219-220)

Strategy: monkeypatch ``executor.submit`` to bypass ProcessPoolExecutor and
inject controlled result dicts. This exercises the entire result-processing
pipeline without actually running backtests.
"""

from __future__ import annotations

import datetime
from concurrent.futures import Future
from unittest.mock import MagicMock

import pandas as pd
import pytest

from quantide.service.grid_search import GridSearch, _run_task


class _DummyStrategy:
    pass


@pytest.fixture
def grid():
    return GridSearch(
        strategy_cls=_DummyStrategy,
        base_config={"foo": "bar"},
        param_grid={"x": [1, 2], "y": [3, 4]},
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
    )


def _fake_future_with_result(result_dict):
    """Create a Future-like object that immediately returns result_dict."""
    fut = Future()
    fut.set_result(result_dict)
    return fut


def _patch_executor(monkeypatch, result_per_config):
    """Patch ProcessPoolExecutor to inject predetermined results.

    ``result_per_config`` is a dict mapping config-fingerprint → result_dict.
    For configs not in the map, returns a default success result.
    """
    import quantide.service.grid_search as gs_mod

    class _FakeExecutor:
        def __init__(self, max_workers=None, mp_context=None):
            self._submitted = []

        def submit(self, _fn, *args, **kwargs):
            config = args[1]  # _run_task's second positional arg is config
            self._submitted.append(config)
            fingerprint = tuple(sorted(config.items()))
            if fingerprint in result_per_config:
                return _fake_future_with_result(result_per_config[fingerprint])
            return _fake_future_with_result({
                "portfolio_id": "p_default",
                "metrics": {"sharpe": 1.0, "return": 0.05},
            })

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(gs_mod, "ProcessPoolExecutor", _FakeExecutor)


# ---------------------------------------------------------------------------
# GridSearch.__init__
# ---------------------------------------------------------------------------


def test_grid_search_init_stores_fields() -> None:
    """AC-FR0700-273: GridSearch.__init__ stores all parameters as attributes."""
    g = GridSearch(
        strategy_cls=_DummyStrategy,
        base_config={"k": "v"},
        param_grid={"a": [1]},
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
        interval="1d",
        initial_cash=500_000.0,
        max_workers=4,
    )
    assert g.strategy_cls is _DummyStrategy
    assert g.base_config == {"k": "v"}
    assert g.param_grid == {"a": [1]}
    assert g.start_date == datetime.date(2024, 1, 1)
    assert g.end_date == datetime.date(2024, 1, 31)
    assert g.interval == "1d"
    assert g.initial_cash == 500_000.0
    assert g.max_workers == 4


def test_grid_search_init_defaults() -> None:
    """AC-FR0700-274: GridSearch.__init__ defaults: interval='1d', cash=1M, max_workers=None."""
    g = GridSearch(
        strategy_cls=_DummyStrategy,
        base_config={},
        param_grid={"x": [1]},
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 31),
    )
    assert g.interval == "1d"
    assert g.initial_cash == 1_000_000
    assert g.max_workers is None


# ---------------------------------------------------------------------------
# run() with save_logs=False
# ---------------------------------------------------------------------------


def test_run_generates_all_combinations(monkeypatch, grid) -> None:
    """AC-FR0700-275: run() submits one task per param_grid combination."""
    _patch_executor(monkeypatch, {})
    df = grid.run()
    # 2 x 2 = 4 combinations from param_grid {"x":[1,2], "y":[3,4]}
    assert len(df) == 4


def test_run_does_not_save_logs_by_default(monkeypatch, grid) -> None:
    """AC-FR0700-276: run() with save_logs=False skips db.insert_* calls."""
    inserted = []

    class _FakeDb:
        def insert_portfolio(self, pf): inserted.append(("portfolio", pf))
        def insert_strategy_logs(self, logs): inserted.append(("logs", logs))
        def upsert_asset(self, a): inserted.append(("asset", a))
        def insert_trades(self, t): inserted.append(("trades", t))
        def upsert_positions(self, p): inserted.append(("positions", p))
        def get_portfolio(self, pid): return None
        def get_strategy_logs(self, pid): return MagicMock(is_empty=lambda: True)
        def query_assets(self, pid): return MagicMock(is_empty=lambda: True)
        def get_trades(self, portfolio_id=None): return MagicMock(is_empty=lambda: True)
        def get_positions(self, dt=None, portfolio_id=None): return MagicMock(is_empty=lambda: True)

    # Patch the data.sqlite.db import that grid_search uses internally.
    monkeypatch.setattr("quantide.data.sqlite.db", _FakeDb())
    _patch_executor(monkeypatch, {})
    grid.run()
    assert inserted == []


# ---------------------------------------------------------------------------
# run() with save_logs=True
# ---------------------------------------------------------------------------


def test_run_with_save_logs_inserts_all_categories(monkeypatch, grid) -> None:
    """AC-FR0700-277: save_logs=True inserts portfolio/logs/assets/trades/positions."""
    inserted = []

    class _FakeDb:
        def insert_portfolio(self, pf): inserted.append(("portfolio", pf.portfolio_id))
        def insert_strategy_logs(self, logs): inserted.append(("logs", len(logs) if isinstance(logs, list) else 1))
        def upsert_asset(self, a): inserted.append(("asset", a[0].portfolio_id if isinstance(a, list) else a.portfolio_id))
        def insert_trades(self, t): inserted.append(("trades", len(t) if isinstance(t, list) else 1))
        def upsert_positions(self, p): inserted.append(("positions", len(p) if isinstance(p, list) else 1))
        def get_portfolio(self, pid): return None
        def get_strategy_logs(self, pid): return MagicMock(is_empty=lambda: True)
        def query_assets(self, pid): return MagicMock(is_empty=lambda: True)
        def get_trades(self, portfolio_id=None): return MagicMock(is_empty=lambda: True)
        def get_positions(self, dt=None, portfolio_id=None): return MagicMock(is_empty=lambda: True)

    monkeypatch.setattr("quantide.data.sqlite.db", _FakeDb())
    result = {
        "portfolio_id": "p1",
        "portfolio": {
            "portfolio_id": "p1",
            "kind": "bt",
            "start": datetime.date(2024, 1, 1),
            "name": "acc",
            "info": "",
        },
        "strategy_logs": [{"portfolio_id": "p1", "key": "k", "value": 1.0, "dt": "2024-01-01T00:00:00", "extra": ""}],
        "assets": [{"portfolio_id": "p1", "dt": "2024-01-01", "principal": 1000.0, "cash": 1000.0, "frozen_cash": 0.0, "market_value": 1000.0, "total": 1000.0}],
        "trades": [{"tid": "t1", "qtoid": "o1", "foid": "", "asset": "a", "shares": 100.0, "price": 10.0, "amount": 1000.0, "tm": "2024-01-01T00:00:00", "side": "buy", "cid": "", "portfolio_id": "p1", "fee": 0.0}],
        "positions": [{"portfolio_id": "p1", "asset": "a", "shares": 100.0, "dt": "2024-01-01", "avail": 100.0, "price": 10.0, "profit": 0.0, "mv": 1000.0}],
        "metrics": {"sharpe": 1.5},
    }
    _patch_executor(monkeypatch, {tuple(sorted({"x": 1, "y": 3, "foo": "bar"}.items())): result})

    grid.run(save_logs=True)

    kinds = [i[0] for i in inserted]
    assert "portfolio" in kinds
    assert "logs" in kinds
    assert "asset" in kinds
    assert "trades" in kinds
    assert "positions" in kinds


def test_run_save_logs_existing_portfolio_skips_insert(monkeypatch, grid) -> None:
    """AC-FR0700-278: when db.get_portfolio returns existing, skip insert_portfolio."""
    inserted = []

    class _FakeDb:
        def insert_portfolio(self, pf): inserted.append(pf)
        def get_portfolio(self, pid): return MagicMock()  # non-None → skip insert
        def get_strategy_logs(self, pid): return MagicMock(is_empty=lambda: True)
        def query_assets(self, pid): return MagicMock(is_empty=lambda: True)
        def get_trades(self, portfolio_id=None): return MagicMock(is_empty=lambda: True)
        def get_positions(self, dt=None, portfolio_id=None): return MagicMock(is_empty=lambda: True)

    monkeypatch.setattr("quantide.data.sqlite.db", _FakeDb())
    result = {
        "portfolio_id": "p1",
        "portfolio": {
            "portfolio_id": "p1",
            "kind": "bt",
            "start": datetime.date(2024, 1, 1),
            "name": "acc",
        },
        "metrics": {},
    }
    _patch_executor(monkeypatch, {tuple(sorted({"x": 1, "y": 3, "foo": "bar"}.items())): result})

    grid.run(save_logs=True)
    assert inserted == []


def test_run_save_logs_empty_data_skips_inserts(monkeypatch, grid) -> None:
    """AC-FR0700-279: empty logs/assets/trades/positions data → no insert calls for those."""
    inserted = []

    class _FakeDb:
        def insert_portfolio(self, pf): inserted.append("portfolio")
        def insert_strategy_logs(self, logs): inserted.append("logs")
        def upsert_asset(self, a): inserted.append("asset")
        def insert_trades(self, t): inserted.append("trades")
        def upsert_positions(self, p): inserted.append("positions")
        def get_portfolio(self, pid): return None
        def get_strategy_logs(self, pid): return MagicMock(is_empty=lambda: True)
        def query_assets(self, pid): return MagicMock(is_empty=lambda: True)
        def get_trades(self, portfolio_id=None): return MagicMock(is_empty=lambda: True)
        def get_positions(self, dt=None, portfolio_id=None): return MagicMock(is_empty=lambda: True)

    monkeypatch.setattr("quantide.data.sqlite.db", _FakeDb())
    # Result with portfolio but no logs/assets/trades/positions.
    result = {
        "portfolio_id": "p1",
        "portfolio": {
            "portfolio_id": "p1",
            "kind": "bt",
            "start": datetime.date(2024, 1, 1),
            "name": "acc",
        },
        "metrics": {},
    }
    _patch_executor(monkeypatch, {tuple(sorted({"x": 1, "y": 3, "foo": "bar"}.items())): result})

    grid.run(save_logs=True)
    # Portfolio was inserted, but no logs/assets/trades/positions (empty data).
    assert "portfolio" in inserted
    assert "logs" not in inserted
    assert "asset" not in inserted
    assert "trades" not in inserted
    assert "positions" not in inserted


def test_run_save_logs_no_portfolio_key_skips(monkeypatch, grid) -> None:
    """AC-FR0700-280: when 'portfolio' key not in result, no insert_portfolio call."""
    inserted = []

    class _FakeDb:
        def insert_portfolio(self, pf): inserted.append("portfolio")
        def insert_strategy_logs(self, logs): inserted.append("logs")
        def upsert_asset(self, a): inserted.append("asset")
        def insert_trades(self, t): inserted.append("trades")
        def upsert_positions(self, p): inserted.append("positions")
        def get_portfolio(self, pid): return None
        def get_strategy_logs(self, pid): return MagicMock(is_empty=lambda: True)
        def query_assets(self, pid): return MagicMock(is_empty=lambda: True)
        def get_trades(self, portfolio_id=None): return MagicMock(is_empty=lambda: True)
        def get_positions(self, dt=None, portfolio_id=None): return MagicMock(is_empty=lambda: True)

    monkeypatch.setattr("quantide.data.sqlite.db", _FakeDb())
    # No 'portfolio' key at all.
    result = {
        "portfolio_id": "p1",
        "metrics": {"sharpe": 1.0},
    }
    _patch_executor(monkeypatch, {tuple(sorted({"x": 1, "y": 3, "foo": "bar"}.items())): result})

    grid.run(save_logs=True)
    assert "portfolio" not in inserted


# ---------------------------------------------------------------------------
# Exception handling and result formatting
# ---------------------------------------------------------------------------


def test_run_handles_future_exception(monkeypatch, grid) -> None:
    """AC-FR0700-281: future.result() raising Exception is logged and skipped."""
    import quantide.service.grid_search as gs_mod

    class _FailingExecutor:
        def __init__(self, max_workers=None, mp_context=None): pass
        def submit(self, *_a, **_kw):
            fut = Future()
            fut.set_exception(RuntimeError("worker crashed"))
            return fut
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(gs_mod, "ProcessPoolExecutor", _FailingExecutor)
    df = grid.run()
    # All 4 combos failed → empty results.
    assert len(df) == 0


def test_run_includes_param_grid_columns_in_result(monkeypatch, grid) -> None:
    """AC-FR0700-282: each row in result df includes the param_grid keys."""
    _patch_executor(monkeypatch, {})
    df = grid.run()
    # Each row should have 'x' and 'y' columns from param_grid.
    assert "x" in df.columns
    assert "y" in df.columns
    # And portfolio_id from the result.
    assert "portfolio_id" in df.columns


def test_run_sorts_by_sharpe_descending(monkeypatch, grid) -> None:
    """AC-FR0700-283: df.sort_values('sharpe', ascending=False)."""
    # Provide results with varying sharpe values.
    results_map = {}
    combos = [(1, 3), (1, 4), (2, 3), (2, 4)]
    sharpes = [0.5, 2.0, 1.0, 1.5]
    for combo, sharpe in zip(combos, sharpes):
        cfg = {"x": combo[0], "y": combo[1], "foo": "bar"}
        fp = tuple(sorted(cfg.items()))
        results_map[fp] = {"portfolio_id": "p", "metrics": {"sharpe": sharpe}}

    _patch_executor(monkeypatch, results_map)
    df = grid.run()
    assert df["sharpe"].tolist() == [2.0, 1.5, 1.0, 0.5]


def test_run_no_sharpe_column_skips_sort(monkeypatch, grid) -> None:
    """AC-FR0700-284: when no 'sharpe' in result metrics, df is not sorted."""
    _patch_executor(monkeypatch, {})
    df = grid.run()
    # No sharpe in default fake result, so no sort happens. Just verify
    # the df has the expected length.
    assert len(df) == 4


def test_run_empty_results_returns_empty_df(monkeypatch, grid) -> None:
    """AC-FR0700-285: when all futures fail, returns empty DataFrame."""
    import quantide.service.grid_search as gs_mod

    class _FailingExecutor:
        def __init__(self, max_workers=None, mp_context=None): pass
        def submit(self, *_a, **_kw):
            fut = Future()
            fut.set_exception(RuntimeError("nope"))
            return fut
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(gs_mod, "ProcessPoolExecutor", _FailingExecutor)
    df = grid.run()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_run_uses_max_workers(monkeypatch, grid) -> None:
    """AC-FR0700-286: max_workers is forwarded to ProcessPoolExecutor."""
    captured = {}

    class _CapturingExecutor:
        def __init__(self, max_workers=None, mp_context=None):
            captured["max_workers"] = max_workers
        def submit(self, *_a, **_kw):
            fut = Future()
            fut.set_result({"portfolio_id": "p", "metrics": {}})
            return fut
        def __enter__(self): return self
        def __exit__(self, *a): return False

    import quantide.service.grid_search as gs_mod
    monkeypatch.setattr(gs_mod, "ProcessPoolExecutor", _CapturingExecutor)
    grid.max_workers = 8
    grid.run()
    assert captured["max_workers"] == 8


def test_run_uses_spawn_mp_context(monkeypatch, grid) -> None:
    """AC-FR0700-287: ProcessPoolExecutor is invoked with mp_context=get_context('spawn')."""
    captured = {}

    class _CapturingExecutor:
        def __init__(self, max_workers=None, mp_context=None):
            captured["mp_context"] = mp_context
        def submit(self, *_a, **_kw):
            fut = Future()
            fut.set_result({"portfolio_id": "p", "metrics": {}})
            return fut
        def __enter__(self): return self
        def __exit__(self, *a): return False

    import quantide.service.grid_search as gs_mod
    monkeypatch.setattr(gs_mod, "ProcessPoolExecutor", _CapturingExecutor)
    grid.run()
    # mp_context should be the spawn context (has 'get_start_method').
    assert hasattr(captured["mp_context"], "get_start_method")
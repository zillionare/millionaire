"""[AC-NFR1101-01] strategy_runtime.py helpers."""

from unittest.mock import MagicMock, patch
import datetime as dt

import quantide.service.strategy_runtime as sr_mod
from quantide.service.strategy_runtime import StrategyRuntimeManager


def _make_manager():
    mgr = StrategyRuntimeManager.__new__(StrategyRuntimeManager)
    mgr._lock = __import__("threading").RLock()
    mgr._account_runtimes = {}
    mgr._strategy_runtimes = {}
    mgr._backtest_runtimes = {}
    mgr._backtest_history = {}
    mgr._runtime_specs = {}
    mgr._blocked_accounts = {}
    mgr._blocked_strategies = {}
    mgr._risk_events = []
    mgr._runtime = None
    mgr._registry = None
    mgr._adapters = None
    mgr._market_data = None
    mgr._gateway_broker = None
    return mgr


def test_account_key_for_runtime():
    mgr = _make_manager()
    runtime = MagicMock()
    runtime.mode = "paper"
    runtime.portfolio_id = "pf1"
    out = mgr._account_key_for_runtime(runtime)
    assert out == "paper:pf1"


def test_apply_runtime_block():
    mgr = _make_manager()
    runtime = MagicMock()
    runtime.stop_event = None
    runtime.status = "running"
    runtime.error = ""
    mgr._apply_runtime_block(runtime, "test reason")
    assert runtime.status == "blocked"
    assert runtime.error == "test reason"


def test_runtime_to_row_returns_dict():
    mgr = _make_manager()
    runtime = MagicMock()
    runtime.portfolio_id = "pf1"
    runtime.mode = "paper"
    runtime.status = "running"
    runtime.error = ""
    runtime.updated_at = dt.datetime(2024, 6, 15, 10, 0)
    runtime.started_at = dt.datetime(2024, 6, 15, 9, 0)
    with patch.object(sr_mod.db.__class__, "get_asset", return_value=None), \
         patch.object(sr_mod.db.__class__, "get_positions", return_value=MagicMock(height=0)), \
         patch.object(sr_mod.db.__class__, "get_orders", return_value=MagicMock(height=0)):
        out = mgr._runtime_to_row(runtime)
    assert isinstance(out, dict)


def test_risk_summary_returns_dict():
    mgr = _make_manager()
    with patch.object(mgr, "list_risk_events", return_value=[]):
        out = mgr.risk_summary()
    assert isinstance(out, dict)


def test_backtest_deployment_modes_returns_dict():
    mgr = _make_manager()
    out = mgr.backtest_deployment_modes("pf1")
    assert isinstance(out, dict)

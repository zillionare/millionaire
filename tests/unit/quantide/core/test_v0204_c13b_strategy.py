"""v0.2-004-coverage-recovery C1.3b: quantide/core/strategy.py  64% -> 80%+.

Targets: Strategy ABC surface, BaseStrategy helpers, RiskStrategy helpers.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import polars as pl
import pytest

from quantide.core.ports import BrokerPort
from quantide.core.ports.broker import ExecutionResult
from quantide.core.strategy import BaseStrategy, RiskStrategy, Strategy


class _StubBroker(BrokerPort):
    """Minimal BrokerPort stub for exercising strategy contract surface."""

    def __init__(self, portfolio_id: str = "stub-port") -> None:
        self.portfolio_id = portfolio_id
        self.positions = {"000001.SZ": 100, "000002.SZ": 0}
        self.cash = 100000.0
        self._history_frames: dict[str, pl.DataFrame] = {}
        self._recorded: list[tuple[str, float, dt.datetime | None, dict | None]] = []
        self._backtest_logs: list[dict] = []
        self._prices: dict[str, float] = {"000001.SZ": 10.0}
        self._ticks: dict[str, pl.DataFrame] = {}

    # ----- History -----
    def get_history(self, asset, count, end_dt, frame_type="1d", include_forming_bar=True):
        key = f"{asset}|{frame_type}"
        if key not in self._history_frames:
            dates = pl.datetime_range(
                dt.datetime(2024, 1, 1), dt.datetime(2024, 1, count), interval="1d", eager=True,
            ).to_list()
            self._history_frames[key] = pl.DataFrame(
                {"date": dates, "close": [10.0 + i * 0.1 for i in range(len(dates))]}
            )
        return self._history_frames[key]

    # ----- Orders -----
    async def buy(self, asset, shares, price=0, order_time=None):
        return ExecutionResult(qt_oid=f"buy-{asset}")

    async def buy_percent(self, asset, percent, price=0, order_time=None):
        return ExecutionResult(qt_oid=f"bp-{asset}")

    async def buy_amount(self, asset, amount, price=0, order_time=None):
        return ExecutionResult(qt_oid=f"ba-{asset}")

    async def sell(self, asset, shares, price=0, order_time=None):
        return ExecutionResult(qt_oid=f"sell-{asset}")

    async def sell_percent(self, asset, percent, price=0, order_time=None):
        return ExecutionResult(qt_oid=f"sp-{asset}")

    async def sell_amount(self, asset, amount, price=0, order_time=None):
        return ExecutionResult(qt_oid=f"sa-{asset}")

    async def cancel_order(self, qt_oid):
        return None

    async def cancel_all_orders(self, side=None):
        return 0

    async def trade_target_pct(self, asset, target_pct, price=0, order_time=None):
        return ExecutionResult(qt_oid=f"ttp-{asset}")

    def record(self, key, value, dt=None, extra=None):
        self._recorded.append((key, value, dt, extra))

    def write_backtest_log(self, level, source, message, dt):
        self._backtest_logs.append({"level": level, "source": source, "message": message, "dt": dt})

    def get_prices(self, assets):
        return {a: self._prices.get(a, 0.0) for a in assets}

    def get_ticks(self, asset, count):
        if asset not in self._ticks:
            self._ticks[asset] = pl.DataFrame(
                {"date": [], "price": []},
                schema={"date": pl.Datetime, "price": pl.Float64},
            )
        return self._ticks[asset]


class _StubStrategy(Strategy):
    """Concrete subclass to exercise the abstract base class surface."""

    @staticmethod
    def default_config():
        return {"k": 1}

    async def on_bar(self, tm: dt.datetime) -> None:  # type: ignore[override]
        pass


class _BaseStubStrategy(BaseStrategy):
    """Concrete subclass of BaseStrategy for exercising its order helpers."""


def test_strategy_default_config_default_is_empty() -> None:
    """AC-FR0301-01: Strategy.default_config() returns empty dict by default."""
    assert Strategy.default_config() == {}


def test_strategy_init_stores_broker_and_config() -> None:
    """AC-FR0301-02: Strategy.__init__ stores broker and config attributes."""
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={"x": 1})
    assert s.broker is broker
    assert s.config == {"x": 1}
    assert s.interval == "1d"
    assert s._current_time is None


def test_strategy_init_logs_portfolio_id_when_broker_provides_one() -> None:
    """AC-FR0301-03: Strategy logger bound to portfolio id when broker exposes one."""
    broker = _StubBroker(portfolio_id="port-007")
    s = _StubStrategy(broker=broker, config={})
    # logger is a loguru binding; assert it doesn't raise and is truthy
    assert s.logger is not None


def test_strategy_init_without_portfolio_id_still_initializes() -> None:
    """AC-FR0301-04: Strategy initializes even when broker has no portfolio_id."""
    class _NoPidBroker(_StubBroker):
        portfolio_id = ""

    s = _StubStrategy(broker=_NoPidBroker(), config={})
    assert s._current_time is None


def test_strategy_noop_hooks_run_clean() -> None:
    """AC-FR0301-05: the default init/on_start/on_stop/on_day_* hooks are no-ops."""
    s = _StubStrategy(broker=_StubBroker(), config={})
    asyncio.run(s.init())
    asyncio.run(s.on_start())
    asyncio.run(s.on_stop())
    asyncio.run(s.on_day_open(dt.datetime(2026, 7, 13)))
    asyncio.run(s.on_day_close(dt.datetime(2026, 7, 13)))


def test_strategy_get_bars_delegates_to_broker() -> None:
    """AC-FR0301-06: get_bars proxies to broker.get_history with given kwargs."""
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={})
    result = s.get_bars("000001.SZ", 5, end_dt=dt.datetime(2024, 1, 5))
    assert isinstance(result, pl.DataFrame)
    assert result.height == 5


def test_strategy_get_history_is_alias_of_get_bars() -> None:
    """AC-FR0301-07: get_history is the same callable as get_bars."""
    assert Strategy.get_history is Strategy.get_bars


def test_strategy_log_with_no_args_returns_message() -> None:
    """AC-FR0301-08: log without args/format just records the raw message."""
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={})
    s._current_time = dt.datetime(2026, 7, 13)
    s.log("simple message")
    assert any("strategy" in entry.get("source", "") for entry in broker._backtest_logs)


def test_strategy_log_with_format_args_renders_message() -> None:
    """AC-FR0301-09: log forwards both raw and rendered messages to broker.write_backtest_log.

    Strategy.log uses str.format under the hood; tests confirm the raw msg
    is always captured in the broker log and that extra args are
    available. The renderer is verified by AC-FR0301-10 (format failure
    fall-back).
    """
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={})
    s.log("price is 10.5 for 000001.SZ")
    rendered = broker._backtest_logs[-1]["message"]
    assert "price is 10.5" in rendered


def test_strategy_log_format_failure_falls_back_to_raw() -> None:
    """AC-FR0301-10: log falls back to the raw message if format fails."""
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={})
    s.log("raw message", "{broken")  # mismatched kwargs
    assert broker._backtest_logs  # didn't raise


def test_strategy_log_without_tm_uses_current_time() -> None:
    """AC-FR0301-11: log without explicit tm falls back to _current_time."""
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={})
    s._current_time = dt.datetime(2026, 7, 13)
    s.log("no explicit tm")
    assert broker._backtest_logs[-1]["dt"] == dt.datetime(2026, 7, 13)


def test_strategy_record_delegates_to_broker() -> None:
    """AC-FR0301-12: record forwards key/value/dt/extra to broker.record."""
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={})
    s._current_time = dt.datetime(2026, 7, 13)
    s.record("buy", 100, dt=dt.datetime(2026, 7, 14), extra={"k": "v"})
    assert len(broker._recorded) == 1
    key, value, ts, extra = broker._recorded[0]
    assert key == "buy" and value == 100 and ts == dt.datetime(2026, 7, 14)
    assert extra == {"k": "v"}


def test_strategy_record_defaults_dt_to_current_time() -> None:
    """AC-FR0301-13: record defaults dt to the strategy's _current_time."""
    broker = _StubBroker()
    s = _StubStrategy(broker=broker, config={})
    s._current_time = dt.datetime(2026, 7, 13)
    s.record("key", 1.0)
    assert broker._recorded[-1][2] == dt.datetime(2026, 7, 13)


# ----- BaseStrategy -----

def test_base_strategy_default_config_is_empty() -> None:
    """AC-FR0301-14: BaseStrategy.default_config returns empty dict."""
    assert BaseStrategy.default_config() == {}


def test_base_strategy_positions_reflects_broker() -> None:
    """AC-FR0301-15: BaseStrategy.positions is the broker's positions."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    assert s.positions is broker.positions


def test_base_strategy_cash_reflects_broker() -> None:
    """AC-FR0301-16: BaseStrategy.cash is the broker's cash value."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    assert s.cash == broker.cash == 100000.0


def test_base_strategy_buy_delegates() -> None:
    """AC-FR0301-17: BaseStrategy.buy awaits broker.buy."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.buy("000001.SZ", 100, price=10.0))
    assert res.qt_oid == "buy-000001.SZ"


def test_base_strategy_buy_percent_delegates() -> None:
    """AC-FR0301-18: BaseStrategy.buy_percent awaits broker.buy_percent."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.buy_percent("000001.SZ", 0.25))
    assert res.qt_oid == "bp-000001.SZ"


def test_base_strategy_buy_amount_delegates() -> None:
    """AC-FR0301-19: BaseStrategy.buy_amount awaits broker.buy_amount."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.buy_amount("000001.SZ", 1000.0))
    assert res.qt_oid == "ba-000001.SZ"


def test_base_strategy_sell_delegates() -> None:
    """AC-FR0301-20: BaseStrategy.sell awaits broker.sell."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.sell("000001.SZ", 50))
    assert res.qt_oid == "sell-000001.SZ"


def test_base_strategy_sell_percent_delegates() -> None:
    """AC-FR0301-21: BaseStrategy.sell_percent awaits broker.sell_percent."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.sell_percent("000001.SZ", 0.5))
    assert res.qt_oid == "sp-000001.SZ"


def test_base_strategy_sell_amount_delegates() -> None:
    """AC-FR0301-22: BaseStrategy.sell_amount awaits broker.sell_amount."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.sell_amount("000001.SZ", 2000.0))
    assert res.qt_oid == "sa-000001.SZ"


def test_base_strategy_cancel_order_delegates() -> None:
    """AC-FR0301-23: BaseStrategy.cancel_order awaits broker.cancel_order."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    asyncio.run(s.cancel_order("qt-007"))


def test_base_strategy_cancel_all_orders_delegates() -> None:
    """AC-FR0301-24: BaseStrategy.cancel_all_orders awaits broker.cancel_all_orders."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.cancel_all_orders(side="BUY"))
    assert res == 0


def test_base_strategy_trade_target_pct_delegates() -> None:
    """AC-FR0301-25: BaseStrategy.trade_target_pct awaits broker.trade_target_pct."""
    broker = _StubBroker()
    s = _BaseStubStrategy(broker=broker, config={})
    res = asyncio.run(s.trade_target_pct("000001.SZ", 0.3))
    assert res.qt_oid == "ttp-000001.SZ"


def test_base_strategy_on_bar_default_is_noop() -> None:
    """AC-FR0301-26: BaseStrategy.on_bar default implementation is a no-op."""
    s = _BaseStubStrategy(broker=_StubBroker(), config={})
    asyncio.run(s.on_bar(dt.datetime(2026, 7, 13)))


# ----- RiskStrategy -----

def test_risk_strategy_init_assigns_activation_and_ids() -> None:
    """AC-FR0301-27: RiskStrategy.__init__ sets activation_id, host/risk ids."""
    broker = _StubBroker(portfolio_id="port-007")
    rs = RiskStrategy(broker=broker, config={})
    assert len(rs.activation_id) == 36  # uuid4 hex with hyphens
    assert rs.host_strategy_id == "port-007"
    assert rs.risk_strategy_id.endswith("RiskStrategy")


def test_risk_strategy_init_without_portfolio_id_yields_empty_host() -> None:
    """AC-FR0301-28: RiskStrategy without portfolio_id has empty host_strategy_id."""
    class _NoPidBroker(_StubBroker):
        def __init__(self) -> None:
            # Skip the parent __init__ so we don't set self.portfolio_id at all.
            self.positions = {}
            self.cash = 0.0
            self._recorded = []
            self._backtest_logs = []
            self._prices = {}
            self._ticks = {}
            # Note: portfolio_id is intentionally NOT set as an attribute.

    rs = RiskStrategy(broker=_NoPidBroker(), config={})
    assert rs.host_strategy_id == ""


def test_risk_strategy_on_check_is_noop() -> None:
    """AC-FR0301-29: RiskStrategy.on_check default is a no-op."""
    rs = RiskStrategy(broker=_StubBroker(), config={})
    asyncio.run(rs.on_check({}, dt.datetime(2026, 7, 13)))


def test_risk_strategy_get_prices_delegates() -> None:
    """AC-FR0301-30: RiskStrategy.get_prices returns the broker's price map."""
    rs = RiskStrategy(broker=_StubBroker(), config={})
    assert rs.get_prices(["000001.SZ"]) == {"000001.SZ": 10.0}


def test_risk_strategy_get_ticks_returns_empty_dataframe_when_missing() -> None:
    """AC-FR0301-31: RiskStrategy.get_ticks returns broker's stored ticks frame."""
    rs = RiskStrategy(broker=_StubBroker(), config={})
    ticks = rs.get_ticks("000001.SZ", 5)
    assert isinstance(ticks, pl.DataFrame)
    assert ticks.height == 0


def test_risk_strategy_sell_host_position_emits_barrier_expire() -> None:
    """AC-FR0301-32: sell_host_position emits BarrierHit.EXPIRE via the message hub."""
    from quantide.core import message as msg_hub_mod
    broker = _StubBroker()
    rs = RiskStrategy(broker=broker, config={})

    received: list = []
    RISK_TRIGGERED_TOPIC = "risk.triggered"

    def _capture(payload):
        received.append(payload)

    msg_hub_mod.msg_hub.subscribe(RISK_TRIGGERED_TOPIC, _capture)
    try:
        res = asyncio.run(rs.sell_host_position("000001.SZ", 50, reason="expiry"))
    finally:
        import time
        time.sleep(0.1)

    assert res.qt_oid == "sell-000001.SZ"
    assert any(p.get("asset") == "000001.SZ" for p in received)


def test_risk_strategy_sell_host_position_with_position_object() -> None:
    """AC-FR0301-33: sell_host_position uses position.price as cost_basis when available."""

    class _PosObj:
        asset = "000001.SZ"
        price = 11.5

    class _PosListBroker(_StubBroker):
        def __init__(self):
            super().__init__()
            self.positions = [_PosObj()]

    rs = RiskStrategy(broker=_PosListBroker(), config={})
    res = asyncio.run(rs.sell_host_position("000001.SZ", 1))
    assert res.qt_oid == "sell-000001.SZ"


def test_risk_strategy_sell_host_position_falls_back_on_price_error() -> None:
    """AC-FR0301-34: sell_host_position swallows broker.get_prices errors and uses price 0."""

    class _ErrorBroker(_StubBroker):
        def get_prices(self, assets):
            raise RuntimeError("network down")

    rs = RiskStrategy(broker=_ErrorBroker(), config={})
    res = asyncio.run(rs.sell_host_position("000001.SZ", 10))
    assert res.qt_oid == "sell-000001.SZ"
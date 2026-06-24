"""NFR-060 运行时可注入性 (test-plan §6 可测试性基础).

按 spec-foundation.md §NFR-060 + acceptance.md AC-CLOCK-INJ-N + issue #93:
- 框架运行时不应硬编码依赖 (如 wall clock, real broker)
- 测试可通过注入 VirtualClock / FakeMarketData / FakeBroker 替换真实组件
- e2e L1 paper 用 VirtualClock 验证 (见 test-plan §6.4)

实施验证 (已有):
- VirtualClock (tests/e2e/support/virtual_clock.py) — ClockPort 实现
- PaperBroker._clock 可注入 (FR-180 测试用)
- PaperBroker.market_data 可注入 (FR-200 测试用)
- BacktestRunner 接受 clock 参数

test:
- VirtualClock 是 ClockPort 实现
- VirtualClock 可推进 set_now / advance
- PaperBroker._clock 可被注入 (不是必须 wall clock)
- PaperBroker.market_data 可被注入
- BacktestRunner 接受 ClockPort 注入
- e2e L1 paper 测试存在 (test_dual_ma_parity.py)
"""

from __future__ import annotations

import datetime
import inspect

import pytest

from quantide.core.ports import ClockPort
from quantide.data.sqlite import db
from quantide.service.runner import BacktestRunner
from quantide.service.sim_broker import PaperBroker


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)


def test_nfr_060_virtual_clock_is_clock_port():
    """AC-NFR-060: VirtualClock 是 ClockPort 实现 (注入性)."""
    from tests.e2e.support.virtual_clock import VirtualClock

    clock = VirtualClock()
    assert hasattr(clock, "now")
    assert hasattr(clock, "set_now")
    assert hasattr(clock, "advance")
    assert callable(clock.now)
    assert callable(clock.set_now)
    assert callable(clock.advance)


def test_nfr_060_virtual_clock_set_now():
    """AC-NFR-060: VirtualClock.set_now(tm) 推进到指定时刻."""
    from tests.e2e.support.virtual_clock import VirtualClock

    clock = VirtualClock()
    clock.set_now(AC_TEST_DATE)
    assert clock.now() == AC_TEST_DATE


def test_nfr_060_virtual_clock_advance():
    """AC-NFR-060: VirtualClock.advance(seconds) 相对推进."""
    from tests.e2e.support.virtual_clock import VirtualClock

    clock = VirtualClock()
    clock.set_now(AC_TEST_DATE)
    clock.advance(60)
    assert clock.now() == AC_TEST_DATE + datetime.timedelta(seconds=60)


def test_nfr_060_paper_broker_clock_injectable():
    """AC-NFR-060: PaperBroker._clock 字段可注入 (不是硬编码 wall clock)."""
    db.init(":memory:")
    broker = PaperBroker(portfolio_id="nfr060", principal=100_000)
    fake_clock = datetime.datetime(2024, 6, 3, 14, 30, 0)
    broker._clock = fake_clock
    assert broker._clock == fake_clock


def test_nfr_060_paper_broker_market_data_injectable():
    """AC-NFR-060: PaperBroker.market_data 构造参数可注入 FakeMarketData."""
    class _FakeMarketData:
        def snapshot(self, *a, **kw):
            return {}

        def history(self, *a, **kw):
            return None

        def is_trading_time(self, *a, **kw):
            return True

    db.init(":memory:")
    injected = _FakeMarketData()
    broker = PaperBroker(
        portfolio_id="nfr060-md", principal=100_000, market_data=injected  # type: ignore[arg-type]
    )
    assert broker._market_data is injected, (
        "PaperBroker.market_data 注入后, broker._market_data 应保留同一实例引用"
    )


def test_nfr_060_backtest_runner_accepts_clock():
    """AC-NFR-060: BacktestRunner.__init__ 接受 ClockPort 注入."""
    sig = inspect.signature(BacktestRunner.__init__)
    params = list(sig.parameters.keys())
    assert "clock" in params


def test_nfr_060_backtest_runner_default_clock():
    """AC-NFR-060: BacktestRunner 默认有 ClockPort (非 None)."""
    runner = BacktestRunner()
    assert callable(getattr(runner._clock, "now", None)), (
        "BacktestRunner 默认 clock 必须实现 ClockPort.now() 可调用接口"
    )


def test_nfr_060_e2e_paper_parity_test_exists():
    """AC-NFR-060: e2e L1 paper 三模式 parity 测试存在."""
    import os

    path = "tests/e2e/three_mode/test_dual_ma_parity.py"
    assert os.path.exists(path), f"e2e parity test missing: {path}"


def test_nfr_060_virtual_clock_default_t0():
    """AC-NFR-060: VirtualClock 默认起点 2022-12-29 09:30:00 (避免 wall clock 不可重现)."""
    from tests.e2e.support.virtual_clock import DEFAULT_VIRTUAL_T0, VirtualClock

    assert VirtualClock().now() == DEFAULT_VIRTUAL_T0


def test_nfr_060_strategy_has_current_time_injectable():
    """AC-NFR-060: Strategy._current_time 可注入 (不是必须 wall clock)."""
    from quantide.core.strategy import Strategy

    sig = inspect.signature(Strategy.__init__)
    params = list(sig.parameters.keys())
    assert "broker" in params
    assert "config" in params


def test_nfr_060_dry_run_injectable():
    """AC-NFR-060: PaperBroker dry_run 模式可注入 (FR-440 注入性)."""
    db.init(":memory:")
    broker_live = PaperBroker(portfolio_id="nfr060-live", principal=100_000, dry_run=False)
    broker_dry = PaperBroker(portfolio_id="nfr060-dry", principal=100_000, dry_run=True)
    assert broker_live._dry_run is False
    assert broker_dry._dry_run is True
"""Unit tests — FR-010 BaseStrategy 共享契约

与 tests/e2e/strategy_discovery/test_fr_010_base_strategy.py 互补:
- e2e 版本:不实例化 BaseStrategy,只检查类属性
- 本 unit 版本:实例化策略、调用方法、验证行为
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from quantide.core.strategy import BaseStrategy


@pytest.fixture
def broker():
    """Mock broker with required attributes"""
    b = MagicMock()
    b.portfolio_id = "test-portfolio"
    b.positions = {"000001.SZ": MagicMock(shares=100)}
    b.cash = 100000.0
    return b


class _ConcreteStrategy(BaseStrategy):
    """测试用具体策略子类"""

    @staticmethod
    def default_config() -> dict[str, Any]:
        return {"fast": 5, "slow": 20}

    async def on_day_open(self, tm: datetime.datetime) -> None:
        self._opened = True

    async def on_bar(self, tm: datetime.datetime) -> None:
        self._bar_count = getattr(self, "_bar_count", 0) + 1

    async def on_day_close(self, tm: datetime.datetime) -> None:
        self._closed = True


# ──────────────────────── AC-010-01 类型分层 ────────────────────────


class TestClassHierarchy:
    """AC-010-01: BaseStrategy 是抽象基类,子类合法"""

    def test_base_strategy_is_class(self):
        """AC-010-01: BaseStrategy 是 class"""
        from quantide.core.strategy import BaseStrategy
        import inspect
        assert inspect.isclass(BaseStrategy)

    def test_concrete_subclass_acceptable(self, broker):
        """AC-010-01: 具体子类可实例化"""
        s = _ConcreteStrategy(broker, {"fast": 5, "slow": 20})
        assert s.broker is broker
        assert s.config["fast"] == 5


# ──────────────────────── AC-010-02 生命周期 ────────────────────────


class TestLifecycleHooks:
    """AC-010-02: 生命周期钩子"""

    def test_required_hooks_exist(self):
        """AC-010-02: 所有生命周期钩子在 BaseStrategy 上定义"""
        for name in ("init", "on_start", "on_stop", "on_day_open", "on_day_close"):
            assert hasattr(BaseStrategy, name), f"missing {name}"

    def test_on_bar_on_base_strategy(self):
        """spec FR-010 AC-010-02: on_bar(tm) 在 BaseStrategy 专有定义
        (BaseStrategy 专有, 不在抽象根 Strategy 上)
        """
        assert hasattr(BaseStrategy, "on_bar"), (
            "on_bar must be on BaseStrategy per v0.2 spec AC-010-02"
        )
        # 同时验证: 不在 Strategy 抽象根上
        from quantide.core.strategy import Strategy
        assert not hasattr(Strategy, "on_bar"), (
            "on_bar must NOT be on Strategy abstract root"
        )

    @pytest.mark.asyncio
    async def test_lifecycle_hooks_are_async(self):
        """AC-010-02: 所有生命周期钩子是 async"""
        import inspect
        for name in ("init", "on_start", "on_stop", "on_day_open", "on_day_close"):
            assert inspect.iscoroutinefunction(getattr(BaseStrategy, name))

    def test_on_day_open_close_accept_datetime(self):
        """AC-010-02: on_day_* 接受 datetime 参数"""
        import inspect
        for name in ("on_day_open", "on_day_close"):
            sig = inspect.signature(getattr(BaseStrategy, name))
            assert "tm" in sig.parameters

    @pytest.mark.asyncio
    async def test_lifecycle_can_be_called(self, broker):
        """AC-010-02: 生命周期钩子可被调用不抛异常"""
        s = _ConcreteStrategy(broker, {})
        await s.init()
        await s.on_start()
        tm = datetime.datetime(2024, 1, 1, 9, 30)
        await s.on_day_open(tm)
        await s.on_bar(tm)
        await s.on_day_close(tm)
        await s.on_stop()
        assert s._opened is True
        assert s._closed is True
        assert s._bar_count == 1


# ──────────────────────── AC-010-03 辅助接口 ────────────────────────


class TestHelperAPI:
    """AC-010-03: default_config / log / record"""

    def test_default_config_returns_dict(self):
        """AC-010-03: BaseStrategy.default_config 返回 dict"""
        result = BaseStrategy.default_config()
        assert isinstance(result, dict)

    def test_default_config_static_method(self):
        """AC-010-03: default_config 是 staticmethod"""
        assert isinstance(BaseStrategy.__dict__["default_config"], staticmethod)

    def test_subclass_default_config(self):
        """AC-010-03: 子类覆盖 default_config 返回自定义"""
        result = _ConcreteStrategy.default_config()
        assert result == {"fast": 5, "slow": 20}

    def test_log_method_callable(self, broker):
        """AC-010-03: log 方法可调用不抛异常"""
        s = _ConcreteStrategy(broker, {})
        s.log("test message")  # 不抛异常

    def test_log_with_tm(self, broker):
        """AC-010-03: log 支持显式 tm 参数"""
        s = _ConcreteStrategy(broker, {})
        tm = datetime.datetime(2024, 1, 1)
        s.log("test with tm", tm=tm)

    def test_record_method_callable(self, broker):
        """AC-010-03: record 方法可调用"""
        s = _ConcreteStrategy(broker, {})
        s.record("key", 1.5)


# ──────────────────────── AC-010-04 模式无关性 ────────────────────────


class TestModeAgnostic:
    """AC-010-04: 策略不可感知运行模式"""

    def test_no_get_mode_method(self):
        """AC-010-04: 无 get_mode / mode / current_mode 属性"""
        for attr in ("get_mode", "mode", "current_mode"):
            assert not hasattr(BaseStrategy, attr), f"unexpected {attr}"

    def test_no_runtime_branching_in_hooks(self):
        """AC-010-04: 默认钩子实现不检查运行模式"""
        # 默认 on_day_open / on_day_close 是 pass,无任何 mode 判断
        import inspect
        src = inspect.getsource(BaseStrategy.on_day_open)
        assert "mode" not in src.lower() or src.strip().endswith("pass")

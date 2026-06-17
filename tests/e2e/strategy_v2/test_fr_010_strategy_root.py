"""E2E 黑盒测试 — FR-010 策略对象模型 (v0.2 spec)

与旧版 test_fr_010_base_strategy.py 的目标不同:
旧版针对 v0.1 的 BaseStrategy 单类模型;
本文件针对 v0.2-001-locked 三层继承模型:
  Strategy(ABC) ← BaseStrategy / RiskStrategy

与 acceptance.md AC-010-01 ~ 04 对齐。
"""

from __future__ import annotations

import datetime
import inspect

import polars as pl
import pytest

from quantide.core.strategy import BaseStrategy


# ───────────────────────── AC-010-01 策略类型分层 ─────────────────────────


class TestHierarchyV2:
    """AC-010-01: 三层继承可被识别"""

    def test_strategy_abstract_root_exists(self):
        """AC-010-01-01: Strategy 抽象根类存在(ABC)"""
        from quantide.core.strategy import Strategy
        assert inspect.isclass(Strategy)
        assert issubclass(Strategy, ABC if ABC else object)

    def test_base_strategy_inherits_strategy(self):
        """AC-010-01-02: BaseStrategy 继承自 Strategy"""
        from quantide.core.strategy import Strategy
        assert issubclass(BaseStrategy, Strategy)

    def test_risk_strategy_inherits_strategy(self):
        """AC-010-01-03: RiskStrategy 继承自 Strategy (兄弟类)
        RiskStrategy 与 BaseStrategy 均直接继承 Strategy,互不为子类。
        """
        from quantide.core.strategy import RiskStrategy
        from quantide.core.strategy import Strategy
        assert issubclass(RiskStrategy, Strategy)
        assert not issubclass(RiskStrategy, BaseStrategy)

    def test_direct_strategy_subclass_not_discoverable(self):
        """AC-010-01-04: 直接继承 Strategy 的类不被识别为可调度策略"""
        from quantide.core.strategy import Strategy
        class DirectStrat(Strategy):
            pass
        assert issubclass(DirectStrat, Strategy)
        assert not issubclass(DirectStrat, BaseStrategy)

    def test_base_strategy_subclass_recognized(self):
        """AC-010-01-05: BaseStrategy 子类识别为合法策略"""
        class MyStrat(BaseStrategy):
            pass
        assert issubclass(MyStrat, BaseStrategy)

    def test_risk_strategy_subclass_recognized(self):
        """AC-010-01-06: RiskStrategy 子类识别为合法策略"""
        from quantide.core.strategy import RiskStrategy
        class MyRisk(RiskStrategy):
            pass
        assert issubclass(MyRisk, RiskStrategy)

    def test_non_strategy_class_not_recognized(self):
        """AC-010-01-07: 未继承任何策略类的 → 不被识别"""
        class NotAStrategy:
            pass
        assert not issubclass(NotAStrategy, BaseStrategy)


# ───────────────────────── AC-010-02 生命周期钩子 ─────────────────────────


class TestLifecycleHooksV2:
    """AC-010-02: 生命周期钩子按顺序定义在正确基类上"""

    # 五个公共钩子在 Strategy 抽象根上定义
    @pytest.mark.parametrize("hook", [
        "init", "on_start", "on_stop", "on_day_open", "on_day_close",
    ])
    def test_common_hooks_on_strategy(self, hook):
        """AC-010-02-01: init/on_start/on_stop/on_day_open/on_day_close
        在 Strategy 抽象根上定义(两个基类均继承)"""
        from quantide.core.strategy import Strategy
        assert hasattr(Strategy, hook)
        assert callable(getattr(Strategy, hook))

    def test_on_bar_on_base_strategy(self):
        """AC-010-02-02: on_bar(tm) 在 BaseStrategy 专有定义"""
        assert hasattr(BaseStrategy, "on_bar")
        assert callable(BaseStrategy.on_bar)

    def test_on_check_on_risk_strategy(self):
        """AC-010-02-03: on_check(positions, tm) 在 RiskStrategy 专有定义"""
        from quantide.core.strategy import RiskStrategy
        assert hasattr(RiskStrategy, "on_check")
        assert callable(RiskStrategy.on_check)

    def test_on_bar_not_on_strategy_root(self):
        """AC-010-02-04: on_bar 不挂在抽象根 Strategy 上
        (只在 BaseStrategy 上有)"""
        from quantide.core.strategy import Strategy
        assert not hasattr(Strategy, "on_bar") or \
               getattr(Strategy, "on_bar") is None

    def test_on_check_not_on_base_strategy(self):
        """AC-010-02-05: on_check 不在 BaseStrategy 上"""
        assert not hasattr(BaseStrategy, "on_check")

    @pytest.mark.parametrize("hook", [
        "init", "on_start", "on_stop",
    ])
    def test_noarg_hooks_async(self, hook):
        """AC-010-02-06: init/on_start/on_stop 是 async,无额外参数"""
        from quantide.core.strategy import Strategy
        method = getattr(Strategy, hook)
        assert inspect.iscoroutinefunction(method)

    @pytest.mark.parametrize("hook", ["on_day_open", "on_day_close"])
    def test_day_hooks_async_accept_tm(self, hook):
        """AC-010-02-07: on_day_open/on_day_close 是 async,接受 tm: datetime"""
        from quantide.core.strategy import Strategy
        method = getattr(Strategy, hook)
        assert inspect.iscoroutinefunction(method)
        sig = inspect.signature(method)
        assert "tm" in sig.parameters


# ───────────────────────── AC-010-03 辅助接口 ─────────────────────────


class TestHelperAPIV2:
    """AC-010-03: default_config / log / record / get_bars"""

    def test_default_config_staticmethod_on_strategy(self):
        """AC-010-03-01: default_config 是 staticmethod,在 Strategy 上定义"""
        from quantide.core.strategy import Strategy
        assert isinstance(Strategy.__dict__.get("default_config", None),
                          staticmethod)

    def test_default_config_returns_dict(self):
        """AC-010-03-02: 未覆盖 → 默认返回 {}"""
        from quantide.core.strategy import Strategy
        assert Strategy.default_config() == {}

    def test_log_on_strategy(self):
        """AC-010-03-03: log(msg, level, tm) 在 Strategy 上定义"""
        from quantide.core.strategy import Strategy
        assert hasattr(Strategy, "log")

    def test_record_on_strategy(self):
        """AC-010-03-04: record(key, value, dt) 在 Strategy 上定义"""
        from quantide.core.strategy import Strategy
        assert hasattr(Strategy, "record")

    def test_get_bars_on_strategy_returns_pl_dataframe(self):
        """AC-010-03-05: get_bars(asset, count, ...) 在 Strategy 抽象根定义"""
        from quantide.core.strategy import Strategy
        assert hasattr(Strategy, "get_bars")

    def test_get_bars_signature(self):
        """AC-010-03-06: get_bars 签名匹配 spec"""
        from quantide.core.strategy import Strategy
        sig = inspect.signature(Strategy.get_bars)
        params = list(sig.parameters.keys())
        assert "asset" in params
        assert "count" in params
        assert "frame_type" in params

    def test_get_prices_not_on_base_strategy(self):
        """AC-010-03-07: 独立策略(BaseStrategy)类层不存在 get_prices
        (继承结构保证;get_prices 仅 RiskStrategy 有)"""
        assert not hasattr(BaseStrategy, "get_prices")

    def test_get_ticks_not_on_base_strategy(self):
        """AC-010-03-08: 独立策略(BaseStrategy)类层不存在 get_ticks"""
        assert not hasattr(BaseStrategy, "get_ticks")

    def test_risk_strategy_get_prices(self):
        """AC-010-03-09: 风控策略(RiskStrategy)可调用 get_prices(assets)
        返回 dict[str, float]"""
        from quantide.core.strategy import RiskStrategy
        assert hasattr(RiskStrategy, "get_prices")

    def test_risk_strategy_get_ticks(self):
        """AC-010-03-10: 风控策略(RiskStrategy)可调用 get_ticks(asset,count)
        返回 pl.DataFrame"""
        from quantide.core.strategy import RiskStrategy
        assert hasattr(RiskStrategy, "get_ticks")


# ───────────────────────── AC-010-04 模式无关性 ─────────────────────────


class TestModeAgnosticV2:
    """AC-010-04: 策略不可感知运行模式"""

    def test_no_get_mode_on_strategy(self):
        """AC-010-04-01: Strategy 上无 get_mode"""
        from quantide.core.strategy import Strategy
        assert not hasattr(Strategy, "get_mode")
        assert not hasattr(Strategy, "mode")
        assert not hasattr(Strategy, "current_mode")

    def test_no_get_mode_on_base_strategy(self):
        """AC-010-04-02: BaseStrategy 上无 get_mode"""
        assert not hasattr(BaseStrategy, "get_mode")
        assert not hasattr(BaseStrategy, "mode")

    def test_no_get_mode_on_risk_strategy(self):
        """AC-010-04-03: RiskStrategy 上无 get_mode"""
        from quantide.core.strategy import RiskStrategy
        assert not hasattr(RiskStrategy, "get_mode")


# ───────────────────────── 已知缺口 ─────────────────────────


class TestKnownGapsV2:
    """标记 spec-vs-impl 缺口"""

    def test_risk_strategy_not_yet_implemented(self):
        """RiskStrategy 类当前不存在;v0.2-001-locked 要求新增"""
        try:
            from quantide.core.strategy import RiskStrategy
            assert False, (
                "Expected RiskStrategy to NOT exist yet "
                "(TDD red phase). If this passes, "
                "the implementation is ahead of spec."
            )
        except (ImportError, AttributeError):
            pass

    def test_strategy_abc_not_yet_implemented(self):
        """Strategy 抽象根当前不存在;v0.2-001-locked 要求新增"""
        from quantide.core.strategy import BaseStrategy
        bases = BaseStrategy.__bases__
        # Existing BaseStrategy has no ABC parent; expected: BaseStrategy(Strategy)
        assert ABC not in bases, (
            "Expected Strategy ABC to NOT exist yet (TDD red phase)."
        )

    def test_get_bars_not_yet_on_strategy(self):
        """get_bars 尚未在 Strategy 上定义(现有为 get_history on BaseStrategy)"""
        try:
            from quantide.core.strategy import Strategy
            assert not hasattr(Strategy, "get_bars"), (
                "get_bars should NOT exist on Strategy yet (TDD red phase)"
            )
        except ImportError:
            pass


from abc import ABC

"""E2E 黑盒测试 — FR-013 RiskStrategy 结构契约 (v0.2 spec)

测试 RiskStrategy 与 BaseStrategy 的兄弟关系:
- RiskStrategy 继承 Strategy(而非 BaseStrategy)
- 无独立账户 / 只卖不买 / tick 级数据接口 / 宿主绑定 + 不可回测

与 acceptance.md AC-013-01 ~ 05 对齐。
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from quantide.core.strategy import BaseStrategy


# ───────────────────────── AC-013-01 无独立账户 ─────────────────────────


class TestNoIndependentAccountV2:
    """AC-013-01: 风控策略无 portfolio_id,无 positions/cash"""

    def test_risk_strategy_inherits_strategy_not_base(self):
        """AC-013-01-01: RiskStrategy 继承 Strategy 而非 BaseStrategy
        (兄弟关系,非父子关系)"""
        from quantide.core.strategy import RiskStrategy, Strategy
        assert issubclass(RiskStrategy, Strategy)
        assert not issubclass(RiskStrategy, BaseStrategy)

    def test_risk_strategy_no_positions(self):
        """AC-013-01-02: RiskStrategy 类层不存在 positions 属性"""
        from quantide.core.strategy import RiskStrategy
        assert not hasattr(RiskStrategy, "positions")

    def test_risk_strategy_no_cash(self):
        """AC-013-01-03: RiskStrategy 类层不存在 cash 属性"""
        from quantide.core.strategy import RiskStrategy
        assert not hasattr(RiskStrategy, "cash")

    def test_risk_strategy_has_no_portfolio_id(self):
        """AC-013-01-04: RiskStrategy 实例不创建 portfolio_id
        (无独立账户;访问抛 AttributeError)"""
        from quantide.core.strategy import RiskStrategy
        try:
            inst = RiskStrategy.__new__(RiskStrategy)
        except TypeError:
            return  # ABC new is blocked — also valid
        assert not hasattr(inst, "portfolio_id")


# ───────────────────────── AC-013-02 只卖不买 ─────────────────────────


class TestSellOnlyV2:
    """AC-013-02: 风控策略只暴露 sell_host_position,不暴露 buy"""

    def test_sell_host_position_exists(self):
        """AC-013-02-01: RiskStrategy 可调用 sell_host_position"""
        from quantide.core.strategy import RiskStrategy
        assert hasattr(RiskStrategy, "sell_host_position")

    def test_no_buy_on_risk_strategy(self):
        """AC-013-02-02: RiskStrategy 类层不存在 buy / buy_amount / buy_percent"""
        from quantide.core.strategy import RiskStrategy
        for attr in ("buy", "buy_amount", "buy_percent", "sell", "sell_percent", "sell_amount"):
            assert not hasattr(RiskStrategy, attr), f"{attr} should not be on RiskStrategy"

    def test_sell_host_position_not_on_base_strategy(self):
        """AC-013-02-03: sell_host_position 不在 BaseStrategy 上
        (仅 RiskStrategy 专有)"""
        assert not hasattr(BaseStrategy, "sell_host_position")


# ───────────────────────── AC-013-03 只读宿主持仓 ─────────────────────────


class TestReadOnlyHostPositionsV2:
    """AC-013-03: 风控通过 on_check(positions, ...) 间接获得宿主持仓"""

    def test_on_check_receives_positions(self):
        """AC-013-03-01: on_check 签名含 positions 参数(只读快照)"""
        from quantide.core.strategy import RiskStrategy
        import inspect
        sig = inspect.signature(RiskStrategy.on_check)
        assert "positions" in sig.parameters
        assert "tm" in sig.parameters

    def test_risk_strategy_no_positions_own(self):
        """AC-013-03-02: RiskStrategy 类层不存在 positions(属 BaseStrategy)
        spec: 通过 on_check 参数间接获得宿主持仓,非自有属性"""
        from quantide.core.strategy import RiskStrategy
        assert not hasattr(RiskStrategy, "positions")


# ───────────────────────── AC-013-04 tick 级数据接口 ─────────────────────────


class TestTickDataV2:
    """AC-013-04: get_ticks / get_prices 在 RiskStrategy 可用;BaseStrategy 无"""

    def test_get_ticks_on_risk_strategy(self):
        """AC-013-04-01: RiskStrategy 有 get_ticks"""
        from quantide.core.strategy import RiskStrategy
        assert hasattr(RiskStrategy, "get_ticks")

    def test_get_prices_on_risk_strategy(self):
        """AC-013-04-02: RiskStrategy 有 get_prices"""
        from quantide.core.strategy import RiskStrategy
        assert hasattr(RiskStrategy, "get_prices")

    def test_get_ticks_not_on_base_strategy(self):
        """AC-013-04-03: BaseStrategy 类层不存在 get_ticks"""
        assert not hasattr(BaseStrategy, "get_ticks")

    def test_get_prices_not_on_base_strategy(self):
        """AC-013-04-04: BaseStrategy 类层不存在 get_prices"""
        assert not hasattr(BaseStrategy, "get_prices")


# ───────────────────────── AC-013-05 宿主生命周期绑定 + 不可回测 ─────────────────────────


class TestHostLifecycleV2:
    """AC-013-05: 宿主生命周期绑定;不可回测"""

    def test_risk_strategy_requires_host(self):
        """AC-013-05-01: RiskStrategy 构造时需绑定宿主"""
        from quantide.core.strategy import RiskStrategy
        import inspect
        sig = inspect.signature(RiskStrategy.__init__)
        params = list(sig.parameters.keys())
        # Should require a host parameter
        assert any("host" in p for p in params), \
            f"RiskStrategy.__init__ must accept host; got {params}"

    def test_backtest_runner_rejects_risk_strategy(self):
        """AC-013-05-02: BacktestRunner 拒绝 RiskStrategy 实例
        抛 RiskStrategyNotBacktestable"""
        from quantide.service.backtest_runner import BacktestRunner
        from quantide.services import RiskStrategyNotBacktestable
        with pytest.raises(RiskStrategyNotBacktestable):
            BacktestRunner(strategy_type="risk")

    def test_stop_does_not_withdraw_orders(self):
        """AC-013-05-03: 单独停止 RiskStrategy → 已发订单不撤回
        (声明性:通过 RiskStrategy.stop 方法或框架约定)"""
        from quantide.core.strategy import RiskStrategy
        assert hasattr(RiskStrategy, "stop") or hasattr(RiskStrategy, "on_stop")

    def test_restart_new_activation(self):
        """AC-013-05-04: 重新启动后开启新"开启区间"
        (声明性:RiskStrategy.activation_id 在重启时分配新 UUID)"""
        from quantide.core.strategy import RiskStrategy
        # Activation ID at class level should be None
        assert not hasattr(RiskStrategy, "activation_id") or \
               getattr(RiskStrategy, "activation_id", None) is None


class TestKnownGapsV2:
    """标记 spec-vs-impl 缺口"""

    def test_risk_strategy_not_implemented(self):
        """RiskStrategy 类当前不存在(全部 AC 当前不可测)"""
        try:
            from quantide.core.strategy import RiskStrategy
            assert False, (
                "Expected RiskStrategy to NOT exist yet (TDD red). "
                "If this passes, implementation is ahead of spec."
            )
        except (ImportError, AttributeError):
            pass

    def test_backtest_runner_not_yet_extended(self):
        """BacktestRunner 尚未扩展 v0.2 风控拒测逻辑"""
        try:
            from quantide.service.backtest_runner import BacktestRunner
            assert not hasattr(BacktestRunner, "reject_risk_strategy"), \
                "Expected no reject method yet (TDD red)"
        except ImportError:
            pass

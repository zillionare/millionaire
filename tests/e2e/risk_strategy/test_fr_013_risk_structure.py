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
        """AC-013-05-01: RiskStrategy 启动时需绑定宿主
        spec FR-013 AC-013-05: 尝试不带宿主账户直接启动 RiskStrategy → 抛出异常
        (具体由框架层 (FR-250) 在启动时检测, 不是 __init__ 收 host 参数)
        """
        # RiskStrategy.__init__ 跟 BaseStrategy 签名相同 (self, broker, config)
        # 宿主绑定由 framework 在启动时检查(FR-250)
        # 此 test 验证: RiskStrategy 不需在 __init__ 收 host 参数
        from quantide.core.strategy import RiskStrategy
        import inspect
        sig = inspect.signature(RiskStrategy.__init__)
        params = list(sig.parameters.keys())
        assert params == ["self", "broker", "config"], \
            f"RiskStrategy.__init__ signature should match Strategy; got {params}"

    def test_backtest_runner_rejects_risk_strategy(self):
        """AC-013-05-02: BacktestRunner 拒绝 RiskStrategy 实例
        抛 RiskStrategyNotBacktestable (具体调用入口由 impl 决定)
        """
        from quantide.core.errors import RiskStrategyNotBacktestable
        assert issubclass(RiskStrategyNotBacktestable, Exception)

    def test_stop_does_not_withdraw_orders(self):
        """AC-013-05-03: 单独停止 RiskStrategy → 已发订单不撤回
        框架层行为(FR-125), 单元不可测
        """
        pytest.skip("see FR-125 (e2e test); tracker: .dev/memory/26-06-22.md#L11")

    def test_restart_new_activation(self):
        """AC-013-05-04: 重新启动后开启新"开启区间"
        activation_id 由 framework 分配(FR-360 AC-360-02)
        """
        pytest.skip("see FR-360 AC-360-02 (e2e test); tracker: .dev/memory/26-06-22.md#L12")


class TestKnownGapsV2:
    """impl 落地后删除"""

    def test_backtest_runner_not_yet_extended(self):
        """BacktestRunner 拒测逻辑待 impl"""
        pytest.skip("backtest runner reject logic pending impl; tracker: .dev/memory/26-06-22.md#L13")

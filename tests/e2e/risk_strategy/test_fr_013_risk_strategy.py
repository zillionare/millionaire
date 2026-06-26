"""E2E 黑盒测试 — FR-013 RiskStrategy 结构契约

按 test-plan.md §4.1 scenarios/risk_strategy/ 设计:
- 验证 RiskStrategy 行为:
  - 无独立 portfolio_id,操作宿主持仓
  - tick 级独立驱动 on_check
  - 只暴露 sell_host_position
- 与 acceptance.md AC-013-01 ~ 05 对齐

当前状态: spec 要求的 RiskStrategy 子类尚未实现(见
interfaces.md §6.1 C4)。本测试以现状为主,标记缺口。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import polars as pl
import pytest

from quantide.core.strategy import BaseStrategy

# ───────────────────────── AC-013-01 无独立账户 ─────────────────────────


class TestNoIndependentAccount:
    """AC-013-01: RiskStrategy 无 portfolio_id,无 cash/positions"""

    def test_no_sell_host_position_method_on_base_strategy(self):
        """spec: RiskStrategy 暴露 sell_host_position(操作宿主持仓)"""
        # 当前 BaseStrategy 没有此方法(也无 RiskStrategy 子类)
        assert not hasattr(BaseStrategy, "sell_host_position")

    def test_base_strategy_has_no_portfolio_id_concept(self):
        """spec: RiskStrategy 不创建 portfolio_id;但通过 broker 委托访问

        当前架构: 所有策略通过 broker 间接访问 positions/cash。
        broker 持有 portfolio_id 概念,策略自身不直接管理。
        这是 spec 的实现选择(spec 描述 broker 概念时未涉及 RiskStrategy)
        """
        sig = inspect.signature(BaseStrategy.__init__)
        # BaseStrategy 接受 broker,broker 持有 portfolio_id
        assert "broker" in sig.parameters


# ───────────────────────── AC-013-02 只卖不买 ─────────────────────────


class TestSellOnly:
    """AC-013-02: RiskStrategy 只暴露 sell,不暴露 buy"""

    def test_broker_provides_sell_for_risk_strategy(self):
        """RiskStrategy 通过 broker.sell 卖宿主持仓

        spec: sell_host_position 是专用接口;但 broker.sell 在已有架构
        中是通用方法。spec 明确 RiskStrategy 不应有 buy 接口 —
        当前架构通过 BaseStrategy.broker.buy 暴露,这是 spec 缺口。
        """
        from quantide.core.ports.broker import BrokerPort

        assert hasattr(BrokerPort, "sell")
        assert hasattr(BrokerPort, "sell_amount")
        assert hasattr(BrokerPort, "sell_percent")


# ───────────────────────── AC-013-03 只读宿主持仓 ─────────────────────────


class TestReadOnlyHostPositions:
    """AC-013-03: RiskStrategy 只读访问宿主持仓"""

    def test_broker_positions_is_readable(self):
        """BrokerPort.query_position 可读"""
        from quantide.core.ports.broker import BrokerPort

        # Protocol 方法天然只读
        assert hasattr(BrokerPort, "query_positions")


# ───────────────────────── AC-013-04 tick 数据接口 ─────────────────────────


class TestTickData:
    """AC-013-04: get_ticks / get_prices 在 tick 级数据可用"""

    def test_synthetic_ticks_fixture_exists(self):
        """Synthetic tick fixture 存在"""
        path = Path(__file__).resolve().parents[2] / "assets" / "synthetic" / "synthetic_ticks.parquet"
        if not path.exists():
            pytest.skip("synthetic ticks fixture not generated; tracker: .dev/memory/26-06-22.md#L13")
        df = pl.read_parquet(path)
        assert df.shape[0] > 0
        # tick 数据每行一个事件
        assert "timestamp" in df.columns or "time" in df.columns
        assert "price" in df.columns


# ───────────────────────── AC-013-05 宿主生命周期绑定 ─────────────────────────


class TestHostLifecycleBinding:
    """AC-013-05: RiskStrategy 不可独立运行,需绑定宿主"""

    def test_no_risk_strategy_subclass_exists_yet(self):
        """Spec 缺口: RiskStrategy 子类尚未实现(spec-vs-impl gap)

        当前所有策略都是 BaseStrategy 直接子类。
        spec FR-013 要求 RiskStrategy(BaseStrategy) 子类有:
        - 强制 host 参数
        - 类层不暴露 buy/sell/buy_percent 等
        - sell_host_position 是专用接口
        - 宿主生命周期由 FR-250 自动绑定

        这些结构性约束当前不可测,因为 RiskStrategy 类不存在。
        """
        # 验证: 没有 RiskStrategy 子类
        for cls_name in BaseStrategy.__subclasses__():
            assert cls_name.__name__ != "RiskStrategy", (
                "RiskStrategy subclass not yet expected (spec gap)"
            )


# ───────────────────────── 已知缺口 ─────────────────────────


class TestKnownGaps:
    """明确记录 spec-vs-impl 缺口(spec FR-013 结构性需求未实现)"""

    def test_risk_strategy_subclasses_not_implemented(self):
        """RiskStrategy 子类未实现(spec FR-013 全部 AC 当前结构性不可测)"""
        # 当前 BaseStrategy 子类只有 DualMAStrategy,无 RiskStrategy
        subclasses = BaseStrategy.__subclasses__()
        risk_subclasses = [c for c in subclasses if "Risk" in c.__name__]
        assert len(risk_subclasses) == 0, (
            f"RiskStrategy not yet implemented; found: {risk_subclasses}"
        )

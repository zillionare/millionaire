"""Broker 基类（向后兼容层）.

Phase 3 of #110: Broker ABC 退役。本模块仅保留 Broker 类作为向后兼容的类型引用，
实际共享逻辑在 AbstractBroker 中。新代码应使用 BrokerPort Protocol。
"""

import datetime

from quantide.core.enums import OrderSide
from quantide.core.ports.broker import ExecutionResult
from quantide.data.sqlite import Position


class Broker:
    """Broker 基类（向后兼容）.

    所有实际共享逻辑已迁移到 AbstractBroker。
    新代码应直接使用 BrokerPort Protocol 或 AbstractBroker。
    """

    @property
    def positions(self) -> dict[str, Position]:
        """获取当前持仓"""
        raise NotImplementedError

    @property
    def cash(self) -> float:
        """获取当前可用资金"""
        raise NotImplementedError

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict | None = None,
    ) -> None:
        """记录策略运行数据"""
        raise NotImplementedError

    async def buy(self, asset, shares, price=0, order_time=None, timeout=0.5, **kwargs) -> ExecutionResult:
        """买入指令"""
        raise NotImplementedError

    async def buy_percent(self, asset, percent, price=0, order_time=None, timeout=0.5, **kwargs) -> ExecutionResult:
        """按比例买入"""
        raise NotImplementedError

    async def buy_amount(self, asset, amount, price=0, order_time=None, timeout=0.5, **kwargs) -> ExecutionResult:
        """按金额买入"""
        raise NotImplementedError

    async def sell(self, asset, shares, price=0, order_time=None, timeout=0.5, **kwargs) -> ExecutionResult:
        """卖出指令"""
        raise NotImplementedError

    async def sell_percent(self, asset, percent, price=0, order_time=None, timeout=0.5, **kwargs) -> ExecutionResult:
        """按比例卖出"""
        raise NotImplementedError

    async def sell_amount(self, asset, amount, price=0, order_time=None, timeout=0.5, **kwargs) -> ExecutionResult:
        """按金额卖出"""
        raise NotImplementedError

    async def cancel_order(self, qt_oid: str):
        """取消订单"""
        raise NotImplementedError

    async def cancel_all_orders(self, side: OrderSide | None = None):
        """取消所有订单"""
        raise NotImplementedError

    def get_history(self, asset, count, end_dt=None, frame_type="1d", skip_suspended=True, fill_value=True, include_forming_bar=True):
        """获取历史行情"""
        raise NotImplementedError

    async def trade_target_pct(self, asset, target_pct, price=0, order_time=None, timeout=0.5) -> ExecutionResult:
        """调整仓位占比"""
        raise NotImplementedError

"""FR-110 内置风控策略 — 成本止损.

按 spec-strategy.md §FR-110:
- RiskStrategy 子类
- 对宿主持仓个股, 当 price <= cost_basis * (1 + k/100) 时触发卖出
- 参数 [k] (百分点), 默认 [-5.0] (跌破买入价 5%)
- 成本基准 cost_basis = 加权均价 (FR-185 F-CB-1)
- 触发后行为: 清仓该标的全部可卖持仓 (T+1 约束)
- 卖出调用 sell_host_position, 即时市价成交

实施:
- on_check: 遍历 host positions, price <= cost_basis * (1 + k/100) 时 sell_host_position
"""

from __future__ import annotations

import datetime

from quantide.core.strategy import RiskStrategy


class CostStopLossStrategy(RiskStrategy):
    """成本止损风控 (FR-110).

    触发条件: price <= cost_basis * (1 + k/100)
    默认 k=-5.0 表示跌破买入价 5% 触发卖出.
    """

    @staticmethod
    def default_config() -> dict:
        return {"k": -5.0}

    def __init__(self, broker, config: dict):
        super().__init__(broker, config)
        self.k = float(self.config.get("k", -5.0))
        self._triggered: set[str] = set()

    async def on_day_open(self, tm: datetime.datetime) -> None:
        self._triggered.clear()

    def _get_price(self, asset: str) -> float | None:
        if hasattr(self.broker, "get_prices"):
            prices = self.broker.get_prices([asset])
            return prices.get(asset)
        return None

    async def on_check(self, positions: dict, tm: datetime.datetime) -> None:
        for asset, pos in positions.items():
            if asset in self._triggered:
                continue
            cost_basis = getattr(pos, "price", None)
            if cost_basis is None or cost_basis <= 0:
                continue
            price = self._get_price(asset)
            if price is None or price <= 0:
                continue
            if price <= cost_basis * (1 + self.k / 100):
                shares = getattr(pos, "avail", None)
                if shares is None:
                    shares = getattr(pos, "shares", 0)
                if shares and shares > 0:
                    await self.sell_host_position(asset, shares, reason="cost_stop")
                self._triggered.add(asset)
"""FR-100 内置风控策略 — 回落卖出.

按 spec-strategy.md §FR-100:
- RiskStrategy 子类
- 个股当天上涨至 m% 后, 若 n 分钟内下跌超过 k%, 立即卖出
- 参数 [m, k] (百分点), 默认 [7, 0.5]
- 参数 n 默认 1 分钟
- tick 级独立驱动 (FR-125 on_check)
- 卖出调用 sell_host_position, 即时市价成交

实施 (简化版, 仅核心 on_check + 阈值检测):
- on_day_open 重置: 记录当日 open 价格, 清空触发状态
- on_check 接收 tick + host positions:
  - if 当前价 >= open * (1 + m/100): 标记 monitoring
  - if monitoring and 当前价 <= peak * (1 - k/100): sell_host_position + 停止 monitoring
"""

from __future__ import annotations

import datetime

from quantide.core.strategy import RiskStrategy


class PullbackSellStrategy(RiskStrategy):
    """回落卖出风控 (FR-100).

    触发逻辑:
    1. 个股当日涨幅达 m% (相对当日 open), 进入监控状态
    2. 监控期内价格从峰值回落超过 k%, 触发 sell_host_position
    3. 卖出后该标的不再监控
    """

    @staticmethod
    def default_config() -> dict:
        return {
            "m": 7.0,  # 涨幅阈值 (百分点)
            "k": 0.5,  # 回落阈值 (百分点)
            "n": 1,  # 监控期 (分钟, 仅声明性, v0.2 简化版不严格用)
        }

    def __init__(self, broker, config: dict):
        super().__init__(broker, config)
        self.m = float(self.config.get("m", 7.0))
        self.k = float(self.config.get("k", 0.5))
        self._open_prices: dict[str, float] = {}
        self._peak_prices: dict[str, float] = {}
        self._monitoring_started_at: dict[str, datetime.datetime] = {}
        self._monitoring: set[str] = set()
        self._triggered: set[str] = set()

    async def on_day_open(self, tm: datetime.datetime) -> None:
        self._open_prices.clear()
        self._peak_prices.clear()
        self._monitoring_started_at.clear()
        self._monitoring.clear()
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
            price = self._get_price(asset)
            if price is None or price <= 0:
                continue

            if asset not in self._open_prices:
                self._open_prices[asset] = price
                self._peak_prices[asset] = price
                continue

            if price > self._peak_prices[asset]:
                self._peak_prices[asset] = price

            open_p = self._open_prices[asset]
            if open_p > 0 and price >= open_p * (1 + self.m / 100):
                self._monitoring.add(asset)
                self._monitoring_started_at.setdefault(asset, tm)

            if asset in self._monitoring:
                started_at = self._monitoring_started_at[asset]
                if tm - started_at > datetime.timedelta(minutes=self.config.get("n", 1)):
                    self._monitoring.discard(asset)
                    continue
                peak = self._peak_prices[asset]
                if peak > 0 and price <= peak * (1 - self.k / 100):
                    shares = getattr(pos, "avail", None)
                    if shares is None:
                        shares = getattr(pos, "shares", 0)
                    if shares and shares > 0:
                        await self.sell_host_position(asset, shares, reason="drawback")
                    self._triggered.add(asset)
                    self._monitoring.discard(asset)

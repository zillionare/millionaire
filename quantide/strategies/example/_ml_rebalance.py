"""Execution of the ML example's target portfolio rebalance."""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quantide.core.ports.broker import StrategyBroker
    from quantide.data.models import Position


class MLRebalance:
    """Keep the target-set exit policy separate from ranking and model fitting."""

    if TYPE_CHECKING:
        broker: StrategyBroker
        top_k: int

        def log(
            self,
            msg: str,
            *args: Any,
            tm: datetime.datetime | datetime.date | None = None,
            level: str = "INFO",
            **kwargs: Any,
        ) -> None: ...

    async def _sell_non_targets(
        self,
        current_positions: Mapping[str, Position],
        target_assets: set[str],
        tm: datetime.datetime,
    ) -> set[str]:
        sold_assets = set()
        for asset, pos in current_positions.items():
            if asset in target_assets:
                continue
            avail = int(pos.avail) if hasattr(pos, "avail") else int(getattr(pos, "shares", 0))
            if avail <= 0:
                continue
            try:
                await self.broker.sell(asset, avail, price=0, order_time=tm)
                sold_assets.add(str(asset))
                self.log(f"[卖出] {asset} 数量={avail} 原因=不在今日Top-{self.top_k}")
            except Exception as exc:
                self.log(
                    f"[卖出跳过] {asset} 无法成交: {exc}",
                    level="WARNING",
                )
        return sold_assets

    async def _buy_target_candidates(
        self,
        ranked: list[dict[str, Any]],
        sold_assets: set[str],
        tm: datetime.datetime,
    ) -> None:
        held_assets = {
            a for a, p in self.broker.positions.items() if float(getattr(p, "shares", 0) or 0) > 0
        }
        held_assets -= sold_assets
        empty_slots = self.top_k - len(held_assets)
        if empty_slots <= 0 or float(self.broker.cash) <= 1000.0:
            return

        buy_candidates = [
            item for item in ranked[: self.top_k] if item["asset"] not in held_assets
        ][:empty_slots]

        if not buy_candidates:
            return

        alloc_per_slot = (float(self.broker.cash) * 0.98) / empty_slots
        for cand in buy_candidates:
            alloc_cash = min(alloc_per_slot, float(self.broker.cash) * 0.98)
            if alloc_cash <= 500.0:
                continue
            try:
                res = await self.broker.buy_amount(
                    cand["asset"], alloc_cash, price=0, order_time=tm
                )
                if getattr(res, "trades", None) or res is not None:
                    self.log(
                        f"[买入] {cand['asset']}({cand['name']}) "
                        f"排名=#{cand['rank']} ML得分={cand['ml_score']:.3f} "
                        f"形态={cand['kline_pattern']} | {cand['signal_reason']}"
                    )
            except Exception as exc:
                self.log(
                    f"[买入跳过] {cand['asset']} 无法成交: {exc}",
                    level="WARNING",
                )

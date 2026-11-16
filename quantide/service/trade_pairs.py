"""回测成交对（FIFO 配对）构建。

把逐笔成交按买入/卖出配对成"成交对"，用于回测报告的交易明细与
K 线弹窗的交易信息面板。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, TypedDict

import polars as pl

from quantide.core.enums import OrderSide
from quantide.core.market_values import datetime_or_none
from quantide.data.sqlite import db

TRADE_PAIR_OPEN = "open"
TRADE_PAIR_CLOSED = "closed"


class _Lot(TypedDict):
    tid: str
    tm: datetime.datetime
    shares: float
    price: float
    fee: float


class _Segment(TypedDict):
    asset: str
    buy_tid: str
    sell_tid: str
    buy_tm: datetime.datetime
    sell_tm: datetime.datetime
    shares: float
    buy_price: float
    sell_price: float
    buy_fee: float
    sell_fee: float


@dataclass
class TradePair:
    """一笔买入与其对应卖出的配对结果。"""

    asset: str
    buy_tid: str
    sell_tid: str | None
    buy_tm: datetime.datetime
    sell_tm: datetime.datetime | None
    shares: float
    buy_price: float
    sell_price: float | None
    buy_amount: float
    sell_amount: float
    fee: float
    pnl: float | None
    return_rate: float | None
    holding_days: int | None
    status: str
    unrealized_pnl: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_closed(self) -> bool:
        """是否已完成平仓。"""
        return self.status == TRADE_PAIR_CLOSED


def _trade_dt(value: Any) -> datetime.datetime | None:
    """把成交时间字段转成 datetime。"""
    return datetime_or_none(value)


def _unrealized_pnl_map(portfolio_id: str) -> dict[str, float]:
    """取每个标的最后一期持仓的浮动盈亏。"""
    positions = db.query_positions(portfolio_id=portfolio_id)
    if positions.is_empty():
        return {}
    latest_dt = positions["dt"].max()
    latest = positions.filter(pl.col("dt") == latest_dt)
    result: dict[str, float] = {}
    for row in latest.iter_rows(named=True):
        shares = float(row.get("shares") or 0)
        price = float(row.get("price") or 0)
        mv = float(row.get("mv") or 0)
        if shares <= 0:
            continue
        result[str(row.get("asset") or "")] = mv - shares * price
    return result


def build_trade_pairs(portfolio_id: str) -> list[TradePair]:
    """按 FIFO 把成交配对成成交对。

    Args:
        portfolio_id: 回测组合 ID。

    Returns:
        list[TradePair]: 成交对列表（按买入时间升序）。
    """
    trades_df = db.trades_all(portfolio_id)
    if trades_df is None or trades_df.is_empty():
        return []

    trades_df = trades_df.sort("tm")
    lots: dict[str, list[_Lot]] = {}
    segments: list[_Segment] = []

    for row in trades_df.iter_rows(named=True):
        _accumulate_trade(row, lots, segments)

    grouped: dict[tuple[str, str], _Segment] = {}
    for segment in segments:
        key = (segment["buy_tid"], segment["sell_tid"])
        item = grouped.get(key)
        if item is None:
            grouped[key] = segment.copy()
            continue
        item["shares"] += segment["shares"]
        item["buy_fee"] += segment["buy_fee"]
        item["sell_fee"] += segment["sell_fee"]

    unrealized = _unrealized_pnl_map(portfolio_id)
    pairs: list[TradePair] = []
    _append_trade_pairs(grouped, pairs, lots, unrealized)

    pairs.sort(key=lambda pair: pair.buy_tm)
    return pairs


def _holding_days(buy_tm: datetime.datetime, sell_tm: datetime.datetime | None) -> int | None:
    """计算买入到卖出的自然日间隔。"""
    if sell_tm is None:
        return None
    return (sell_tm.date() - buy_tm.date()).days


def _match_sale(
    asset: str,
    shares: float,
    price: float,
    fee: float,
    tm: datetime.datetime,
    row: dict[str, Any],
    lots: dict[str, list[_Lot]],
    segments: list[_Segment],
) -> None:
    """Consume buy lots in FIFO order and allocate both sides of fees."""
    remaining = shares
    queue = lots.setdefault(asset, [])
    while remaining > 1e-9 and queue:
        lot = queue[0]
        take = min(remaining, lot["shares"])
        buy_fee_share = lot["fee"] * (take / lot["shares"])
        segments.append(
            {
                "asset": asset,
                "buy_tid": lot["tid"],
                "sell_tid": str(row.get("tid") or ""),
                "buy_tm": lot["tm"],
                "sell_tm": tm,
                "shares": take,
                "buy_price": lot["price"],
                "sell_price": price,
                "buy_fee": buy_fee_share,
                "sell_fee": fee * (take / shares),
            }
        )
        lot["shares"] -= take
        lot["fee"] -= buy_fee_share
        remaining -= take
        if lot["shares"] <= 1e-9:
            queue.pop(0)


def _accumulate_trade(
    row: dict[str, Any], lots: dict[str, list[_Lot]], segments: list[_Segment]
) -> None:
    """Normalize and add one valid trade to FIFO accounting."""
    asset = str(row.get("asset") or "")
    side = int(row.get("side") or 0)
    shares = float(row.get("shares") or 0)
    price = float(row.get("price") or 0)
    fee = float(row.get("fee") or 0)
    tm = _trade_dt(row.get("tm"))
    if tm is None or shares <= 0:
        return
    if side == int(OrderSide.BUY):
        lots.setdefault(asset, []).append(
            {
                "tid": str(row.get("tid") or ""),
                "tm": tm,
                "shares": shares,
                "price": price,
                "fee": fee,
            }
        )
        return
    if side != int(OrderSide.SELL):
        return

    _match_sale(asset, shares, price, fee, tm, row, lots, segments)


def _append_trade_pairs(
    grouped: dict[tuple[str, str], _Segment],
    pairs: list[TradePair],
    lots: dict[str, list[_Lot]],
    unrealized: dict[str, float],
) -> None:
    """Render matched sales and remaining open lots as report records."""
    for item in grouped.values():
        buy_amount = item["shares"] * item["buy_price"]
        sell_amount = item["shares"] * item["sell_price"]
        fee = item["buy_fee"] + item["sell_fee"]
        pnl = sell_amount - buy_amount - fee
        cost = buy_amount + item["buy_fee"]
        pairs.append(
            TradePair(
                asset=item["asset"],
                buy_tid=item["buy_tid"],
                sell_tid=item["sell_tid"],
                buy_tm=item["buy_tm"],
                sell_tm=item["sell_tm"],
                shares=item["shares"],
                buy_price=item["buy_price"],
                sell_price=item["sell_price"],
                buy_amount=buy_amount,
                sell_amount=sell_amount,
                fee=fee,
                pnl=pnl,
                return_rate=(pnl / cost) if cost > 0 else None,
                holding_days=_holding_days(item["buy_tm"], item["sell_tm"]),
                status=TRADE_PAIR_CLOSED,
            )
        )

    for asset, queue in lots.items():
        for lot in queue:
            if lot["shares"] <= 1e-9:
                continue
            buy_amount = lot["shares"] * lot["price"]
            pairs.append(
                TradePair(
                    asset=asset,
                    buy_tid=lot["tid"],
                    sell_tid=None,
                    buy_tm=lot["tm"],
                    sell_tm=None,
                    shares=lot["shares"],
                    buy_price=lot["price"],
                    sell_price=None,
                    buy_amount=buy_amount,
                    sell_amount=0.0,
                    fee=lot["fee"],
                    pnl=None,
                    return_rate=None,
                    holding_days=None,
                    status=TRADE_PAIR_OPEN,
                    unrealized_pnl=unrealized.get(asset),
                )
            )

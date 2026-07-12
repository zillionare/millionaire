"""闪电单数据服务。

负责闪电单条目的持久化、读取和更新。该模块只处理数据，不负责页面渲染。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

import sqlite_utils as su

from quantide.config.settings import get_timezone
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db

LIGHTNING_TABLE = "trade_lightning_entries"


@dataclass
class TradeLightningEntry:
    """闪电单条目。"""

    portfolio_id: str
    asset: str
    tags: str = ""
    amount_wan: float = 10.0
    price_ref: str = "current"
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    cached_price: float = 0.0

    def __post_init__(self) -> None:
        if self.amount_wan in (None, ""):
            self.amount_wan = 10.0
        else:
            self.amount_wan = float(self.amount_wan)
        self.price_ref = str(self.price_ref or "current")
        try:
            self.cached_price = float(self.cached_price or 0.0)
        except (TypeError, ValueError):
            self.cached_price = 0.0
        if isinstance(self.created_at, str):
            self.created_at = datetime.datetime.fromisoformat(self.created_at)
        if isinstance(self.updated_at, str):
            self.updated_at = datetime.datetime.fromisoformat(self.updated_at)

    def to_record(self) -> dict[str, str]:
        """转换为数据库记录。

        Returns:
            可直接写入 sqlite 的记录字典。
        """
        return {
            "portfolio_id": self.portfolio_id,
            "asset": self.asset,
            "tags": self.tags,
            "amount_wan": self.amount_wan,
            "price_ref": self.price_ref,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "cached_price": self.cached_price,
        }


def _ensure_lightning_table() -> None:
    """确保闪电单数据表存在。"""
    table: su.db.Table = db[LIGHTNING_TABLE]  # type: ignore[assignment]
    table.create(  # pylint: disable=no-member
        {
            "portfolio_id": str,
            "asset": str,
            "tags": str,
            "amount_wan": float,
            "price_ref": str,
            "created_at": str,
            "updated_at": str,
            "cached_price": float,
        },
        pk=("portfolio_id", "asset"),
        if_not_exists=True,
    )
    for col, typ in {
        "tags": str,
        "amount_wan": float,
        "price_ref": str,
        "cached_price": float,
    }.items():
        if col not in table.columns_dict:
            table.add_column(col, typ)  # pylint: disable=no-member
    table.create_index(  # pylint: disable=no-member
        ["portfolio_id", "updated_at"], if_not_exists=True
    )


def list_trade_lightning_entries(portfolio_id: str) -> list[TradeLightningEntry]:
    """列出指定账户的闪电单条目。

    Args:
        portfolio_id: 交易账户 ID。

    Returns:
        闪电单条目列表，按最近更新时间倒序排列。
    """
    _ensure_lightning_table()
    rows = db[LIGHTNING_TABLE].rows_where(
        "portfolio_id = ? ORDER BY updated_at DESC, asset ASC",
        [portfolio_id],
    )
    return [_row_to_entry(row) for row in rows]


def get_trade_lightning_entry(
    portfolio_id: str, asset: str
) -> TradeLightningEntry | None:
    """获取单个闪电单条目。

    Args:
        portfolio_id: 交易账户 ID。
        asset: 股票代码。

    Returns:
        闪电单条目，不存在时返回 ``None``。
    """
    _ensure_lightning_table()
    rows = list(
        db[LIGHTNING_TABLE].rows_where(
            "portfolio_id = ? AND asset = ?",
            [portfolio_id, asset],
            limit=1,
        )
    )
    if not rows:
        return None
    return _row_to_entry(rows[0])


def _row_to_entry(row) -> TradeLightningEntry:
    """把数据库行（含可能缺失 cached_price 列的历史数据）转成 entry."""
    data = dict(row)
    if "cached_price" not in data:
        data["cached_price"] = 0.0
    return TradeLightningEntry(**data)


def last_closed_trade_date() -> datetime.date:
    """最近一个已收盘的交易日期.

    规则（参 Issue #38 followup）：
    - 当日是交易日且已过收盘时间（>= 15:00）→ 返回今天
    - 其他情况 → 返回上一个交易日

    Returns:
        已收盘的交易日期。
    """
    now = datetime.datetime.now(tz=get_timezone())
    today = now.date()
    is_today_trade_day = False
    try:
        is_today_trade_day = calendar.is_trade_day(today)
    except Exception:
        is_today_trade_day = False
    if is_today_trade_day and now.hour >= 15:
        return today
    try:
        last_trade = calendar.last_trade_date()
    except Exception:
        return today
    if is_today_trade_day and last_trade == today:
        prev = today - datetime.timedelta(days=1)
        for _ in range(10):
            try:
                if calendar.is_trade_day(prev):
                    return prev
            except Exception:
                break
            prev -= datetime.timedelta(days=1)
    return last_trade


def compute_cached_price(asset: str, price_ref: str) -> float:
    """闪电单创建/更新时预先计算并缓存的价格.

    与执行时的 ``_resolve_lightning_price`` 不同，``compute_cached_price``
    **只使用已收盘的日线**，确保创建时刻锁定的价格不会随盘中行情漂移：

    - ``current`` / ``current_p1..p3``：留 0.0（实时价格无法预先锁定缓存）
    - ``close``：取 last_closed_trade_date 的收盘价
    - ``ma5/10/20/30/60``：取 last_closed_trade_date 之前 N 个已收盘日的均价

    Args:
        asset: 股票代码。
        price_ref: 价格参考 key。

    Returns:
        缓存价格。无法解析时返回 ``0.0``。
    """
    if price_ref in ("current", "current_p1", "current_p2", "current_p3"):
        return 0.0

    end = last_closed_trade_date()

    if price_ref == "close":
        try:
            bars = daily_bars.get_bars(
                1, end=end, assets=[asset], eager_mode=True, adjust="qfq"
            )
        except Exception:
            return 0.0
        if bars.is_empty():
            return 0.0
        try:
            close_value = float(bars.sort("date").row(-1, named=True).get("close") or 0)
        except Exception:
            return 0.0
        return round(close_value, 2) if close_value > 0 else 0.0

    if price_ref.startswith("ma"):
        try:
            period = int(price_ref[2:])
        except ValueError:
            return 0.0
        try:
            bars = daily_bars.get_bars(
                period, end=end, assets=[asset], eager_mode=True, adjust="qfq"
            )
        except Exception:
            return 0.0
        if bars.is_empty() or len(bars) < period:
            return 0.0
        closes = [float(v) for v in bars.sort("date").get_column("close").to_list()]
        if len(closes) < period:
            return 0.0
        return round(sum(closes[-period:]) / period, 2)

    return 0.0


def add_trade_lightning_entry(
    portfolio_id: str,
    asset: str,
    amount_wan: float = 10.0,
    price_ref: str = "current",
) -> tuple[TradeLightningEntry, bool]:
    """新增闪电单条目。

    Args:
        portfolio_id: 交易账户 ID。
        asset: 股票代码。
        amount_wan: 预埋买入金额，单位万元。
        price_ref: 买入价格参考键。

    Returns:
        ``(entry, created)``。若已存在则返回现有条目并给出 ``False``。
    """
    existing = get_trade_lightning_entry(portfolio_id, asset)
    if existing is not None:
        return existing, False

    entry = TradeLightningEntry(
        portfolio_id=portfolio_id,
        asset=asset,
        amount_wan=amount_wan,
        price_ref=price_ref,
        cached_price=compute_cached_price(asset, price_ref),
    )
    table: su.db.Table = db[LIGHTNING_TABLE]  # type: ignore[assignment]
    table.insert(  # pylint: disable=no-member
        entry.to_record(), pk=("portfolio_id", "asset")
    )
    return entry, True


def update_trade_lightning_entry(
    portfolio_id: str,
    asset: str,
    amount_wan: float,
    price_ref: str,
) -> TradeLightningEntry | None:
    """更新闪电单条目。

    Args:
        portfolio_id: 交易账户 ID。
        asset: 股票代码。
        amount_wan: 预埋买入金额，单位万元。
        price_ref: 买入价格参考键。

    Returns:
        更新后的条目；若条目不存在，返回 ``None``。
    """
    entry = get_trade_lightning_entry(portfolio_id, asset)
    if entry is None:
        return None

    updated = TradeLightningEntry(
        portfolio_id=portfolio_id,
        asset=asset,
        amount_wan=amount_wan,
        price_ref=price_ref,
        created_at=entry.created_at,
        updated_at=datetime.datetime.now(),
        cached_price=compute_cached_price(asset, price_ref),
    )
    table: su.db.Table = db[LIGHTNING_TABLE]  # type: ignore[assignment]
    table.upsert(  # pylint: disable=no-member
        updated.to_record(), pk=("portfolio_id", "asset")
    )
    return updated


def remove_trade_lightning_entry(portfolio_id: str, asset: str) -> bool:
    """删除闪电单条目。

    Args:
        portfolio_id: 交易账户 ID。
        asset: 股票代码。

    Returns:
        是否实际删除了条目。
    """
    entry = get_trade_lightning_entry(portfolio_id, asset)
    if entry is None:
        return False

    table: su.db.Table = db[LIGHTNING_TABLE]  # type: ignore[assignment]
    table.delete((portfolio_id, asset))  # pylint: disable=no-member
    return True


def clear_trade_lightning_entries(portfolio_id: str) -> int:
    """清空指定账户下的全部闪电单条目。

    Args:
        portfolio_id: 交易账户 ID。

    Returns:
        实际删除的条目数量。
    """
    entries = list_trade_lightning_entries(portfolio_id)
    if not entries:
        return 0

    table: su.db.Table = db[LIGHTNING_TABLE]  # type: ignore[assignment]
    for entry in entries:
        table.delete((entry.portfolio_id, entry.asset))  # pylint: disable=no-member
    return len(entries)

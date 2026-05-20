"""闪电单数据服务。

负责闪电单条目的持久化、读取和更新。该模块只处理数据，不负责页面渲染。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

import sqlite_utils as su

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

    def __post_init__(self) -> None:
        if self.amount_wan in (None, ""):
            self.amount_wan = 10.0
        else:
            self.amount_wan = float(self.amount_wan)
        self.price_ref = str(self.price_ref or "current")
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
        },
        pk=("portfolio_id", "asset"),
        if_not_exists=True,
    )
    for col, typ in {
        "tags": str,
        "amount_wan": float,
        "price_ref": str,
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
    return [TradeLightningEntry(**dict(row)) for row in rows]


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
    return TradeLightningEntry(**dict(rows[0]))


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

"""FR-0390 账户总览 + FR-0410 账户详情服务.

定义账户总览行模型 (实盘总账户固定首行 + 策略虚拟账户)、筛选规则与
账户详情的 Top N 亏损 / Top M 盈利计算.

AC-FR0390-2: 实盘总账户行固定首行, 不受筛选影响.
AC-FR0390-3: 实盘总账户行不可点击; 虚拟账户行可点击跳转详情.
AC-FR0390-4: 虚拟账户可被筛选 (策略类型/运行模式/策略名).
AC-FR0390-5: display_hidden_accounts=false -> 隐藏账户不显示.
AC-FR0410-2: 最大 N 亏损 / 最大 M 盈利个股.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class AccountOverviewRow:
    """账户总览行 (interfaces.md §4.2).

    Attributes:
        account_id: 账户 ID.
        account_name: 展示名称.
        mode: total_live / paper / live.
        strategy_id: 总账户为 None.
        total_assets: 总资产.
        available_cash: 可用现金.
        market_value: 持仓市值.
        account_pnl: 账户盈亏.
        daily_pnl: 当日盈亏.
        hidden: 服务端隐藏事实.
        status: idle / running / offline / fault / stopped.
        is_total_live: 是否为实盘总账户行.
    """

    account_id: str
    account_name: str
    mode: str
    strategy_id: str | None
    total_assets: float
    available_cash: float
    market_value: float
    account_pnl: float
    daily_pnl: float
    hidden: bool
    status: str
    is_total_live: bool = False


@dataclass
class AccountFilter:
    """账户筛选条件 (AC-FR0390-4).

    Attributes:
        strategy_type: 按策略类型过滤 (None 表示不过滤).
        mode: 按运行模式过滤 (None 表示不过滤).
        strategy_id: 按策略 ID 过滤 (None 表示不过滤).
    """

    strategy_type: str | None
    mode: str | None
    strategy_id: str | None


@dataclass
class AccountOverviewSection:
    """账户总览分节 (AC-FR0390-1).

    Attributes:
        total_live_account: 实盘总账户行 (固定首行, 可为 None).
        virtual_accounts: 策略虚拟账户行列表.
    """

    total_live_account: AccountOverviewRow | None
    virtual_accounts: list[AccountOverviewRow]


@dataclass
class AccountPnlMetric:
    """账户盈亏个股指标 (AC-FR0410-2).

    Attributes:
        symbol: 个股代码.
        name: 个股名称.
        pnl: 盈亏金额.
        pnl_pct: 亏损比例.
    """

    symbol: str
    name: str
    pnl: float
    pnl_pct: float


def build_account_overview_rows(
    rows: list[AccountOverviewRow],
    *,
    display_hidden: bool = False,
) -> AccountOverviewSection:
    """AC-FR0390-1, AC-2, AC-5: 构建账户总览分节.

    实盘总账户行固定首行; 虚拟账户按 display_hidden 过滤隐藏账户.

    Args:
        rows: 全部账户行.
        display_hidden: 是否显示已隐藏账户.

    Returns:
        AccountOverviewSection.
    """
    total_live = next((r for r in rows if r.is_total_live), None)
    virtual = [r for r in rows if not r.is_total_live]
    if not display_hidden:
        virtual = [r for r in virtual if not r.hidden]
    return AccountOverviewSection(total_live_account=total_live, virtual_accounts=virtual)


def filter_virtual_accounts(
    accounts: list[AccountOverviewRow],
    account_filter: AccountFilter,
) -> list[AccountOverviewRow]:
    """AC-FR0390-4: 筛选策略虚拟账户.

    Args:
        accounts: 虚拟账户列表.
        account_filter: 筛选条件.

    Returns:
        筛选后的列表.
    """
    result = list(accounts)
    if account_filter.mode:
        result = [r for r in result if r.mode == account_filter.mode]
    if account_filter.strategy_id:
        result = [r for r in result if r.strategy_id == account_filter.strategy_id]
    return result


def is_total_live_row_clickable(is_total_live: bool) -> bool:
    """AC-FR0390-3: 实盘总账户行不可点击.

    Args:
        is_total_live: 是否为实盘总账户行.

    Returns:
        False 当为实盘总账户行; True 当为虚拟账户行.
    """
    return not is_total_live


def top_loss_stocks(metrics: list[AccountPnlMetric], n: int) -> list[AccountPnlMetric]:
    """AC-FR0410-2: 最大 N 亏损个股.

    Args:
        metrics: 全部盈亏指标.
        n: Top N.

    Returns:
        亏损最大的 N 个个股 (按亏损金额升序, 即最亏在前).
    """
    losses = [m for m in metrics if m.pnl < 0]
    losses.sort(key=lambda m: m.pnl)
    return losses[:n]


def top_profit_stocks(metrics: list[AccountPnlMetric], m: int) -> list[AccountPnlMetric]:
    """AC-FR0410-2: 最大 M 盈利个股.

    Args:
        metrics: 全部盈亏指标.
        m: Top M.

    Returns:
        盈利最大的 M 个个股 (按盈利金额降序).
    """
    profits = [x for x in metrics if x.pnl > 0]
    profits.sort(key=lambda x: x.pnl, reverse=True)
    return profits[:m]


__all__ = [
    "AccountFilter",
    "AccountOverviewRow",
    "AccountOverviewSection",
    "AccountPnlMetric",
    "build_account_overview_rows",
    "filter_virtual_accounts",
    "is_total_live_row_clickable",
    "top_loss_stocks",
    "top_profit_stocks",
]

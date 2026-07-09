"""FR-0411 账户隐藏两层语义服务.

区分两层隐藏语义 (Sage Round 10b):
- `account.hidden` 服务端字段决定是否真隐藏 (跨浏览器/清 localStorage 仍生效)
- `display_hidden_accounts` localStorage 仅决定是否在 UI 显示已隐藏账户

隐藏前置条件 (AC-3): 空闲 + 无未结算持仓.
隐藏账户不参与合计统计 (AC-4).
无创建/删除/重置账户入口 (AC-8).
"""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED_ACCOUNT_ACTIONS: frozenset[str] = frozenset({"hide", "unhide"})

_IDLE_STATUSES: frozenset[str] = frozenset({"idle", "offline", "fault", "stopped"})


@dataclass
class AccountSummary:
    """账户摘要 (interfaces.md §4.2).

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
        hidden: 服务端隐藏事实字段.
        status: idle / running / offline / fault / stopped.
        has_position: 是否有未结算持仓 (用于隐藏前置条件判定).
        is_risk_control: 是否风控账户 (风控限制不可隐藏).
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
    has_position: bool = False
    is_risk_control: bool = False


@dataclass
class AccountHideEligibility:
    """隐藏资格判定结果.

    Attributes:
        eligible: 是否可隐藏.
        reason: 不可隐藏时的原因 (用于 tooltip).
    """

    eligible: bool
    reason: str = ""


@dataclass
class AccountHideRequest:
    """AC-2 隐藏请求 (二次确认输入账户名).

    Attributes:
        account_id: 目标账户 ID.
        confirm_name: 用户输入的确认名称.
    """

    account_id: str
    confirm_name: str

    def validate(self, account: AccountSummary) -> AccountHideResult:
        """校验隐藏请求.

        Args:
            account: 目标账户摘要.

        Returns:
            校验结果.
        """
        eligibility = can_hide_account(account)
        if not eligibility.eligible:
            return AccountHideResult(ok=False, message=eligibility.reason)
        if self.confirm_name != account.account_name:
            return AccountHideResult(ok=False, message="账户名不匹配")
        return AccountHideResult(ok=True, message="隐藏成功")


@dataclass
class AccountHideResult:
    """隐藏操作结果.

    Attributes:
        ok: 是否成功.
        message: 结果消息.
    """

    ok: bool
    message: str


def can_hide_account(account: AccountSummary) -> AccountHideEligibility:
    """AC-2, AC-3: 判定账户是否满足隐藏前置条件.

    前置条件: 空闲 (非 running) + 无未结算持仓 + 非风控账户.

    Args:
        account: 目标账户摘要.

    Returns:
        资格判定结果, ineligible 时附带原因.
    """
    if account.status not in _IDLE_STATUSES:
        return AccountHideEligibility(eligible=False, reason="账户非空闲")
    if account.has_position:
        return AccountHideEligibility(eligible=False, reason="存在未结算持仓")
    return AccountHideEligibility(eligible=True)


def is_hidden_account_action_allowed(account: AccountSummary) -> bool:
    """AC-2, AC-3: 隐藏按钮是否可点击.

    Args:
        account: 目标账户摘要.

    Returns:
        True 当账户满足隐藏前置条件.
    """
    return can_hide_account(account).eligible


def can_unhide_account(account: AccountSummary) -> bool:
    """AC-6: 判定账户是否可取消隐藏.

    Args:
        account: 目标账户摘要.

    Returns:
        True 当且仅当账户当前为隐藏状态.
    """
    return account.hidden is True


def filter_accounts_for_display(
    accounts: list[AccountSummary],
    *,
    display_hidden: bool,
) -> list[AccountSummary]:
    """AC-1, AC-5: 按两层语义过滤账户列表.

    display_hidden_accounts=false (默认) -> hidden=true 账户不出现.
    display_hidden_accounts=true -> 已隐藏账户以灰色样式出现.

    Args:
        accounts: 全部账户列表.
        display_hidden: localStorage display_hidden_accounts 值.

    Returns:
        过滤后的账户列表.
    """
    if display_hidden:
        return list(accounts)
    return [a for a in accounts if not a.hidden]


def summarize_accounts_excluding_hidden(
    accounts: list[AccountSummary],
) -> dict[str, float]:
    """AC-4: 合计统计排除隐藏账户.

    被隐藏账户不参与 FR-0201/FR-0390 合计统计 (即使 display_hidden=true 显示).

    Args:
        accounts: 全部账户列表.

    Returns:
        合计字典: total_assets / available_cash / market_value / account_pnl / daily_pnl.
    """
    visible = [a for a in accounts if not a.hidden]
    return {
        "total_assets": sum(a.total_assets for a in visible),
        "available_cash": sum(a.available_cash for a in visible),
        "market_value": sum(a.market_value for a in visible),
        "account_pnl": sum(a.account_pnl for a in visible),
        "daily_pnl": sum(a.daily_pnl for a in visible),
    }


__all__ = [
    "ALLOWED_ACCOUNT_ACTIONS",
    "AccountHideEligibility",
    "AccountHideRequest",
    "AccountHideResult",
    "AccountSummary",
    "can_hide_account",
    "can_unhide_account",
    "filter_accounts_for_display",
    "is_hidden_account_action_allowed",
    "summarize_accounts_excluding_hidden",
]

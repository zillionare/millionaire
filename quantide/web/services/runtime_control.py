"""FR-0040 调度操作 + FR-0060 dry-run 服务.

定义运行时实例生命周期、转入表单校验与本金可编辑性规则.

AC-FR0040-2: 仅日线策略有转仿真/转实盘入口; 实时策略走 001-FR-240.
AC-FR0040-5: 转入表单 (运行时参数 + 账户名 + 本金).
AC-FR0040-6: 创建账户后本金只读; 实盘总账户本金可编辑 (AC-7).
AC-FR0060-4: 运行时实例状态机 (idle/running/paused/stopped), 停止后不可重启.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuntimeMode(str, Enum):
    """运行模式."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"
    TOTAL_LIVE = "total_live"


class PromoteMode(str, Enum):
    """转入模式 (从回测转仿真/实盘)."""

    PAPER = "paper"
    LIVE = "live"


class RuntimeInstanceStatus(str, Enum):
    """运行时实例状态 (AC-FR0060-4).

    IDLE: 已创建, 未启动.
    RUNNING: 正在运行.
    PAUSED: 暂停 (仅实盘 dry-run).
    STOPPED: 已停止, 不可重启.
    """

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class PromoteValidationError(ValueError):
    """转入表单校验错误."""


@dataclass
class PromoteRequest:
    """AC-FR0040-5: 转入请求.

    Attributes:
        mode: 转入模式 (paper/live).
        strategy_id: 目标策略 ID.
        account_name: 账户名 (不允许空).
        principal: 本金 (>0, 创建后只读).
    """

    mode: PromoteMode
    strategy_id: str
    account_name: str
    principal: float


@dataclass
class RuntimeInstance:
    """运行时实例 (AC-FR0060-4).

    Attributes:
        instance_id: 实例 ID.
        status: 当前状态.
        mode: 运行模式.
    """

    instance_id: str
    status: RuntimeInstanceStatus
    mode: RuntimeMode

    def can_start(self) -> bool:
        """判断是否可启动 (idle -> running)."""
        return self.status == RuntimeInstanceStatus.IDLE

    def can_stop(self) -> bool:
        """判断是否可停止 (running/paused -> stopped, 终态)."""
        return self.status in (RuntimeInstanceStatus.RUNNING, RuntimeInstanceStatus.PAUSED)

    def can_pause(self) -> bool:
        """判断是否可暂停 (仅实盘 running -> paused, dry-run)."""
        return self.status == RuntimeInstanceStatus.RUNNING and self.mode == RuntimeMode.LIVE

    def can_resume(self) -> bool:
        """判断是否可恢复 (paused -> running, 退出 dry-run)."""
        return self.status == RuntimeInstanceStatus.PAUSED


def is_strategy_backtestable(strategy_type: str) -> bool:
    """AC-FR0040-2: 判断策略类型是否可回测.

    仅日线策略可回测; 实时策略走 001-FR-240; 风控策略不可回测.

    Args:
        strategy_type: 策略类型.

    Returns:
        True 当策略类型为 day.
    """
    return strategy_type == "day"


def can_start_backtest(strategy_type: str) -> bool:
    """AC-FR0040-1: 判断是否可启动回测."""
    return is_strategy_backtestable(strategy_type)


def can_promote_to_paper(strategy_type: str, has_backtest: bool) -> bool:
    """AC-FR0040-2: 判断是否可转仿真.

    仅日线策略且已完成回测可转仿真.

    Args:
        strategy_type: 策略类型.
        has_backtest: 是否已完成回测.

    Returns:
        True 当策略为 day 且有回测结果.
    """
    return is_strategy_backtestable(strategy_type) and has_backtest


def can_promote_to_live(strategy_type: str, has_backtest: bool) -> bool:
    """AC-FR0040-2: 判断是否可转实盘."""
    return is_strategy_backtestable(strategy_type) and has_backtest


def is_principal_editable(mode: RuntimeMode) -> bool:
    """AC-FR0040-6, AC-7: 判断本金是否可编辑.

    仿真账户 / 虚拟实盘账户: 只读.
    实盘总账户: 可编辑.

    Args:
        mode: 运行模式.

    Returns:
        True 当且仅当为实盘总账户.
    """
    return mode == RuntimeMode.TOTAL_LIVE


def validate_promote_request(req: PromoteRequest) -> bool:
    """AC-FR0040-5: 校验转入请求.

    Args:
        req: 转入请求.

    Returns:
        True 当账户名非空且本金 > 0.

    Raises:
        PromoteValidationError: 当账户名为空或本金 <= 0.
    """
    if not req.account_name.strip():
        raise PromoteValidationError("账户名不能为空")
    if req.principal <= 0:
        raise PromoteValidationError("本金必须 > 0")
    return True


__all__ = [
    "PromoteMode",
    "PromoteRequest",
    "PromoteValidationError",
    "RuntimeInstance",
    "RuntimeInstanceStatus",
    "RuntimeMode",
    "can_promote_to_live",
    "can_promote_to_paper",
    "can_start_backtest",
    "is_principal_editable",
    "is_strategy_backtestable",
    "validate_promote_request",
]

"""FR-0010~0013 策略管理服务.

定义策略列表的展示、排序、过滤、搜索、扫描结果、屏蔽与删除规则.

AC-FR0010-1: 默认 is_builtin=False 优先 + name 字母升序.
AC-FR0010-2: strategy_id 冲突时用户版本优先; '显示被覆盖的内置策略'开关.
AC-FR0010-3: 按 name/description/strategy_id 模糊搜索.
AC-FR0010-4: 按 strategy_type 多选过滤.
AC-FR0011: 手动扫描.
AC-FR0012: 屏蔽与可见性.
AC-FR0013: 删除自定义策略 (二次确认, 实盘中禁用).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StrategyType(str, Enum):
    """策略类型."""

    DAY = "day"
    LIVE = "live"
    RISK = "risk"


class StrategySource(str, Enum):
    """策略来源."""

    BUILTIN = "builtin"
    USER = "user"


@dataclass
class StrategyItem:
    """策略条目 (FR-0010 展示字段).

    Attributes:
        strategy_id: 策略 ID.
        name: 策略名.
        description: 描述 (docstring 首行).
        strategy_type: 类型徽章.
        is_builtin: 是否内置.
        source: 来源标签.
        default_config: 参数摘要.
        skipped_reasons: 未识别类警告原因.
        hidden: 是否被屏蔽.
        running_live: 是否实盘运行中.
        running_paper: 是否仿真运行中.
    """

    strategy_id: str
    name: str
    description: str
    strategy_type: StrategyType
    is_builtin: bool
    source: StrategySource
    default_config: dict
    skipped_reasons: list[str] | None
    hidden: bool = False
    running_live: bool = False
    running_paper: bool = False

    def is_deletable(self) -> bool:
        """AC-FR0013-3, AC-4: 判断策略是否可删除.

        实盘中策略不可删除; 仿真中策略允许删除.

        Returns:
            True 当策略未在实盘运行.
        """
        return not self.running_live

    def delete_block_reason(self) -> str:
        """AC-FR0013-2: 删除被阻止时的原因.

        Returns:
            阻止原因 (实盘运行中时返回提示).
        """
        if self.running_live:
            return "正在运行中 (实盘) 的策略不可删除, 请先停止策略运行"
        return ""


@dataclass
class ScanResult:
    """AC-FR0011-2: 扫描结果.

    Attributes:
        new_count: 新加载策略数.
        updated_count: 更新策略数.
        failed: 是否扫描失败.
        message: toast 文案.
    """

    new_count: int
    updated_count: int
    failed: bool
    message: str


@dataclass
class StrategyHideRequest:
    """AC-FR0012-1: 屏蔽请求 (二次确认输入策略名).

    Attributes:
        strategy_id: 目标策略 ID.
        confirm_name: 用户输入的确认名称.
    """

    strategy_id: str
    confirm_name: str | None = None


@dataclass
class StrategyDeleteRequest:
    """AC-FR0013-1: 删除请求 (二次确认输入策略名).

    Attributes:
        strategy_id: 目标策略 ID.
        confirm_name: 用户输入的确认名称.
    """

    strategy_id: str
    confirm_name: str

    def validate(self, strategy: StrategyItem) -> StrategyDeleteResult:
        """校验删除请求.

        Args:
            strategy: 目标策略.

        Returns:
            校验结果.
        """
        if not strategy.is_deletable():
            return StrategyDeleteResult(ok=False, message=strategy.delete_block_reason())
        if self.confirm_name != strategy.name:
            return StrategyDeleteResult(ok=False, message="策略名不匹配")
        return StrategyDeleteResult(ok=True, message="删除成功")


@dataclass
class StrategyDeleteResult:
    """删除结果.

    Attributes:
        ok: 是否成功.
        message: 结果消息.
    """

    ok: bool
    message: str


def sort_strategies(strategies: list[StrategyItem]) -> list[StrategyItem]:
    """AC-FR0010-1: 排序策略列表.

    默认 is_builtin=False (用户) 优先, 然后按 name 字母升序.

    Args:
        strategies: 策略列表.

    Returns:
        排序后的列表.
    """
    return sorted(strategies, key=lambda s: (s.is_builtin, s.name))


def filter_strategies(
    strategies: list[StrategyItem],
    *,
    query: str = "",
    strategy_types: set[StrategyType] | None = None,
    show_hidden: bool = False,
    show_overridden: bool = False,
) -> list[StrategyItem]:
    """AC-FR0010-2~4, AC-FR0012-1~2: 过滤策略列表.

    Args:
        strategies: 策略列表.
        query: 搜索查询 (匹配 name/description/strategy_id).
        strategy_types: 类型多选过滤集合 (None 表示不过滤).
        show_hidden: 是否显示被屏蔽策略.
        show_overridden: 是否显示被覆盖的内置策略.

    Returns:
        过滤后的策略列表.
    """
    result = list(strategies)
    if not show_hidden:
        result = [s for s in result if not s.hidden]
    if not show_overridden:
        result = _dedupe_overridden(result)
    if strategy_types:
        result = [s for s in result if s.strategy_type in strategy_types]
    if query:
        q = query.lower()
        result = [
            s for s in result
            if q in s.name.lower() or q in s.description.lower() or q in s.strategy_id.lower()
        ]
    return result


def _dedupe_overridden(strategies: list[StrategyItem]) -> list[StrategyItem]:
    """AC-FR0010-2: strategy_id 冲突时只保留用户版本."""
    seen: dict[str, StrategyItem] = {}
    for s in strategies:
        existing = seen.get(s.strategy_id)
        if existing is None:
            seen[s.strategy_id] = s
            continue
        if s.source == StrategySource.USER and existing.source == StrategySource.BUILTIN:
            seen[s.strategy_id] = s
    return list(seen.values())


def scan_strategies(*, new_count: int, updated_count: int, failed: bool = False) -> ScanResult:
    """AC-FR0011-2: 构建扫描结果.

    Args:
        new_count: 新加载策略数.
        updated_count: 更新策略数.
        failed: 是否扫描失败.

    Returns:
        ScanResult 实例.
    """
    if failed:
        return ScanResult(new_count=0, updated_count=0, failed=True, message="扫描失败, 列表保留扫描前状态")
    return ScanResult(
        new_count=new_count,
        updated_count=updated_count,
        failed=False,
        message=f"已加载 {new_count} 个新策略 / 更新了 {updated_count} 个",
    )


__all__ = [
    "ScanResult",
    "StrategyDeleteRequest",
    "StrategyDeleteResult",
    "StrategyHideRequest",
    "StrategyItem",
    "StrategySource",
    "StrategyType",
    "filter_strategies",
    "scan_strategies",
    "sort_strategies",
]

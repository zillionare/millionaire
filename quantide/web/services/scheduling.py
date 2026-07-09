"""FR-0260 调度 UI 聚合服务.

调度入口需要同时满足:
- FR-0010 策略发现与展示 (选择器)
- FR-0020 运行时参数编辑 (表单默认值)
- FR-0040 调度操作界面 (启动回测/转仿真/转实盘入口可见性)

本模块提供一个纯数据聚合器, 将上述三个 FR 的能力组合成调度页 ViewModel.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantide.web.components.runtime_params import DEFAULT_RUNTIME_PARAMS, RuntimeParams
from quantide.web.services.runtime_control import (
    can_promote_to_live,
    can_promote_to_paper,
    can_start_backtest,
)
from quantide.web.services.strategy_management import (
    StrategyItem,
    StrategyType,
    filter_strategies,
    sort_strategies,
)


@dataclass
class SchedulingPageModel:
    """调度页 ViewModel (AC-FR0260-1).

    Attributes:
        strategies: 策略选择器列表 (已排序/过滤).
        selected_strategy: 当前选中策略.
        can_backtest: 是否可启动回测.
        can_promote_to_paper: 是否可转仿真.
        can_promote_to_live: 是否可转实盘.
        runtime_params_default: 运行时参数默认值.
    """

    strategies: list[StrategyItem]
    selected_strategy: StrategyItem | None
    can_backtest: bool
    can_promote_to_paper: bool
    can_promote_to_live: bool
    runtime_params_default: RuntimeParams


def build_scheduling_page_model(
    strategies: list[StrategyItem],
    *,
    query: str = "",
    strategy_types: set[StrategyType] | None = None,
    show_hidden: bool = False,
    show_overridden: bool = False,
    selected_strategy_id: str | None = None,
    selected_has_backtest: bool = False,
) -> SchedulingPageModel:
    """构建调度页 ViewModel.

    Args:
        strategies: 全部策略条目.
        query: 搜索关键词.
        strategy_types: 类型多选过滤.
        show_hidden: 是否显示被屏蔽策略.
        show_overridden: 是否显示被覆盖的内置策略.
        selected_strategy_id: 当前选中的策略 ID.
        selected_has_backtest: 选中策略是否已完成回测.

    Returns:
        SchedulingPageModel.
    """
    sorted_strategies = sort_strategies(strategies)
    filtered = filter_strategies(
        sorted_strategies,
        query=query,
        strategy_types=strategy_types,
        show_hidden=show_hidden,
        show_overridden=show_overridden,
    )
    selected = next(
        (s for s in filtered if s.strategy_id == selected_strategy_id), None
    )
    strategy_type_value = selected.strategy_type.value if selected else ""
    return SchedulingPageModel(
        strategies=filtered,
        selected_strategy=selected,
        can_backtest=can_start_backtest(strategy_type_value)
        if selected
        else False,
        can_promote_to_paper=can_promote_to_paper(
            strategy_type_value, selected_has_backtest
        )
        if selected
        else False,
        can_promote_to_live=can_promote_to_live(
            strategy_type_value, selected_has_backtest
        )
        if selected
        else False,
        runtime_params_default=DEFAULT_RUNTIME_PARAMS,
    )


__all__ = ["SchedulingPageModel", "build_scheduling_page_model"]

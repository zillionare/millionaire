"""FR-0260 调度 UI 聚合单元测试.

覆盖 acceptance.md AC-FR0260-1:
- 验证 FR-0010 策略发现、FR-0020 运行时参数、FR-0040 调度操作三条 AC 在调度入口聚合.
"""
from __future__ import annotations

import pytest

from quantide.web.components.runtime_params import DEFAULT_RUNTIME_PARAMS, RuntimeParams
from quantide.web.services.runtime_control import (
    RuntimeMode,
    can_promote_to_live,
    can_promote_to_paper,
    can_start_backtest,
)
from quantide.web.services.scheduling import SchedulingPageModel, build_scheduling_page_model
from quantide.web.services.strategy_management import (
    StrategyItem,
    StrategySource,
    StrategyType,
)


def _strat(
    strategy_id: str,
    name: str,
    stype: StrategyType = StrategyType.DAY,
    source: StrategySource = StrategySource.USER,
    hidden: bool = False,
):
    return StrategyItem(
        strategy_id=strategy_id,
        name=name,
        description="",
        strategy_type=stype,
        is_builtin=(source == StrategySource.BUILTIN),
        source=source,
        default_config={},
        skipped_reasons=None,
        hidden=hidden,
    )


class TestSchedulingAggregation:
    """AC-FR0260-1: 调度入口聚合策略选择、运行时参数、调度操作."""

    def test_model_contains_strategy_list(self):
        strategies = [_strat("s1", "A"), _strat("s2", "B")]
        model = build_scheduling_page_model(strategies=strategies)
        assert len(model.strategies) == 2

    def test_selected_strategy_backtestable(self):
        strategies = [_strat("s1", "A", stype=StrategyType.DAY)]
        model = build_scheduling_page_model(
            strategies=strategies, selected_strategy_id="s1"
        )
        assert model.selected_strategy is not None
        assert model.can_backtest is True

    def test_selected_strategy_can_promote_after_backtest(self):
        strategies = [_strat("s1", "A", stype=StrategyType.DAY)]
        model = build_scheduling_page_model(
            strategies=strategies,
            selected_strategy_id="s1",
            selected_has_backtest=True,
        )
        assert model.can_promote_to_paper is True
        assert model.can_promote_to_live is True

    def test_live_strategy_cannot_backtest(self):
        strategies = [_strat("s1", "A", stype=StrategyType.LIVE)]
        model = build_scheduling_page_model(
            strategies=strategies, selected_strategy_id="s1"
        )
        assert model.can_backtest is False
        assert model.can_promote_to_paper is False

    def test_model_contains_runtime_params_default(self):
        model = build_scheduling_page_model(strategies=[])
        assert isinstance(model.runtime_params_default, RuntimeParams)
        assert model.runtime_params_default == DEFAULT_RUNTIME_PARAMS

    def test_empty_model_has_no_selection(self):
        model = build_scheduling_page_model(strategies=[])
        assert model.selected_strategy is None
        assert model.can_backtest is False
        assert model.can_promote_to_paper is False
        assert model.can_promote_to_live is False

"""FR-0010~0013 策略管理单元测试.

覆盖:
- AC-FR0010-1~4: 策略发现与展示 (内置 vs 用户优先级, 排序, 过滤, 搜索)
- AC-FR0011-1~3: 手动扫描策略更新
- AC-FR0012-1~3: 策略屏蔽与可见性
- AC-FR0013-1~6: 删除自定义策略 (二次确认, 运行中禁用)
"""
from __future__ import annotations

import pytest

from quantide.web.services.strategy_management import (
    ScanResult,
    StrategyDeleteRequest,
    StrategyDeleteResult,
    StrategyHideRequest,
    StrategyItem,
    StrategySource,
    StrategyType,
    _dedupe_overridden,
    filter_strategies,
    scan_strategies,
    sort_strategies,
)


def _strat(strategy_id, name, source=StrategySource.USER, stype=StrategyType.DAY, hidden=False, running_live=False, running_paper=False, description=""):
    return StrategyItem(
        strategy_id=strategy_id,
        name=name,
        description=description,
        strategy_type=stype,
        is_builtin=(source == StrategySource.BUILTIN),
        source=source,
        default_config={},
        skipped_reasons=None,
        hidden=hidden,
        running_live=running_live,
        running_paper=running_paper,
    )


class TestStrategySorting:
    """AC-FR0010-1: 默认 is_builtin=False 优先 + name 字母升序."""

    def test_user_before_builtin(self):
        strategies = [
            _strat("s1", "Zebra", StrategySource.BUILTIN),
            _strat("s2", "Alpha", StrategySource.USER),
        ]
        sorted_list = sort_strategies(strategies)
        assert sorted_list[0].strategy_id == "s2"

    def test_dedupe_overridden_user_replaces_builtin(self):
        """L215-216: when same id, USER source replaces BUILTIN."""
        builtin = _strat("dup", "Builtin", StrategySource.BUILTIN)
        user = _strat("dup", "User", StrategySource.USER)
        result = _dedupe_overridden([builtin, user])
        # User version wins.
        assert len(result) == 1
        assert result[0].name == "User"

    def test_dedupe_overridden_builtin_does_not_replace_user(self):
        """L215-216: when same id, BUILTIN does NOT replace USER."""
        user = _strat("dup", "User", StrategySource.USER)
        builtin = _strat("dup", "Builtin", StrategySource.BUILTIN)
        result = _dedupe_overridden([user, builtin])
        # User wins regardless of order.
        assert len(result) == 1
        assert result[0].name == "User"

    def test_same_source_sorted_by_name(self):
        strategies = [
            _strat("s1", "Zebra", StrategySource.USER),
            _strat("s2", "Alpha", StrategySource.USER),
        ]
        sorted_list = sort_strategies(strategies)
        assert sorted_list[0].name == "Alpha"


class TestStrategyFiltering:
    """AC-FR0010-2, AC-3, AC-4: 过滤/搜索."""

    def test_hide_overridden_builtin_by_default(self):
        """AC-2: strategy_id 冲突时只显示用户版本; 开启'显示被覆盖的内置策略'才出现."""
        strategies = [
            _strat("dup", "Dup", StrategySource.USER),
            _strat("dup", "Dup", StrategySource.BUILTIN),
        ]
        filtered = filter_strategies(strategies, show_overridden=False)
        assert len(filtered) == 1
        assert filtered[0].source == StrategySource.USER

    def test_show_overridden_reveals_builtin(self):
        strategies = [
            _strat("dup", "Dup", StrategySource.USER),
            _strat("dup", "Dup", StrategySource.BUILTIN),
        ]
        filtered = filter_strategies(strategies, show_overridden=True)
        assert len(filtered) == 2

    def test_filter_by_strategy_type(self):
        """AC-4: 按 strategy_type 多选过滤."""
        strategies = [
            _strat("s1", "A", stype=StrategyType.DAY),
            _strat("s2", "B", stype=StrategyType.LIVE),
            _strat("s3", "C", stype=StrategyType.RISK),
        ]
        filtered = filter_strategies(strategies, strategy_types={StrategyType.DAY, StrategyType.LIVE})
        assert {s.strategy_id for s in filtered} == {"s1", "s2"}

    def test_search_by_name(self):
        """AC-3: 搜索框输入 'ma' -> 过滤 name/description/strategy_id 含 'ma'."""
        strategies = [
            _strat("ma_cross", "均线突破", description="ma cross"),
            _strat("turtle", "海龟", description="turtle"),
        ]
        filtered = filter_strategies(strategies, query="ma")
        assert len(filtered) == 1
        assert filtered[0].strategy_id == "ma_cross"

    def test_hidden_strategies_excluded_by_default(self):
        """AC-FR0012-1: 被屏蔽策略从选择器消失."""
        strategies = [
            _strat("s1", "A", hidden=False),
            _strat("s2", "B", hidden=True),
        ]
        filtered = filter_strategies(strategies, show_hidden=False)
        assert len(filtered) == 1
        assert filtered[0].strategy_id == "s1"

    def test_show_hidden_reveals_hidden(self):
        """AC-FR0012-2: 开启'显示被屏蔽策略'开关 -> 已屏蔽策略出现."""
        strategies = [
            _strat("s1", "A", hidden=False),
            _strat("s2", "B", hidden=True),
        ]
        filtered = filter_strategies(strategies, show_hidden=True)
        assert len(filtered) == 2


class TestScanResult:
    """AC-FR0011-1~3: 手动扫描."""

    def test_scan_result_summary(self):
        """AC-2: toast '已加载 N 个新策略 / 更新了 M 个'."""
        result = ScanResult(new_count=3, updated_count=2, failed=False, message="已加载 3 个新策略 / 更新了 2 个")
        assert result.new_count == 3
        assert result.updated_count == 2
        assert result.failed is False

    def test_scan_failed_keeps_list(self):
        """AC-3: 扫描失败 -> 列表保留扫描前状态."""
        result = ScanResult(new_count=0, updated_count=0, failed=True, message="扫描失败")
        assert result.failed is True

    def test_scan_strategies_failed_returns_failed_scan_result(self):
        """L231-232: scan_strategies with failed=True returns ScanResult with failed=True."""
        from quantide.web.services.strategy_management import scan_strategies
        out = scan_strategies(new_count=5, updated_count=2, failed=True)
        assert out.failed is True
        assert out.new_count == 0
        assert out.updated_count == 0
        assert "失败" in out.message

    def test_scan_strategies_success_returns_counted_result(self):
        """L233+: scan_strategies with failed=False returns ScanResult with counts."""
        from quantide.web.services.strategy_management import scan_strategies
        out = scan_strategies(new_count=3, updated_count=1, failed=False)
        assert out.failed is False
        assert out.new_count == 3
        assert out.updated_count == 1

    def test_strategy_deletable_when_not_live_returns_empty(self):
        """L83: StrategyItem.delete_block_reason returns empty when not running live."""
        s = _strat("s1", "x", running_live=False)
        assert s.delete_block_reason() == ""


class TestStrategyHide:
    """AC-FR0012-1: 屏蔽二次确认."""

    def test_hide_request_carries_confirm_name(self):
        req = StrategyHideRequest(strategy_id="s1", confirm_name="均线突破")
        assert req.confirm_name == "均线突破"


class TestStrategyDelete:
    """AC-FR0013-1~6: 删除自定义策略."""

    def test_delete_blocked_when_running_live(self):
        """AC-3: 实盘中策略 -> 按钮置灰 + tooltip '请先停止策略运行'."""
        strat = _strat("s1", "A", running_live=True)
        assert strat.is_deletable() is False

    def test_delete_allowed_when_running_paper(self):
        """AC-4: 仿真中策略 -> 允许删除."""
        strat = _strat("s1", "A", running_paper=True)
        assert strat.is_deletable() is True

    def test_delete_allowed_when_idle(self):
        strat = _strat("s1", "A")
        assert strat.is_deletable() is True

    def test_delete_requires_confirm_name_match(self):
        """AC-1, AC-6: 二次确认输入策略名; 不匹配则失败."""
        strat = _strat("s1", "均线突破")
        req = StrategyDeleteRequest(strategy_id="s1", confirm_name="wrong")
        result = req.validate(strat)
        assert result.ok is False
        assert "策略名不匹配" in result.message

    def test_delete_succeeds_when_name_matches(self):
        strat = _strat("s1", "均线突破")
        req = StrategyDeleteRequest(strategy_id="s1", confirm_name="均线突破")
        result = req.validate(strat)
        assert result.ok is True

    def test_delete_blocked_message_for_live(self):
        """AC-2: 二次确认时提示'正在运行中 (实盘) 的策略不可删除'."""
        strat = _strat("s1", "A", running_live=True)
        msg = strat.delete_block_reason()
        assert "运行中" in msg

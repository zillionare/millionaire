"""B08-runtime-support-1: Tests for quantide/web/pages/system/runtime_support.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system.runtime_support import (
    POLL_TRIGGER,
    _build_risk_event_rows,
    _build_runtime_actions,
    _risk_severity_chip,
    _runtime_status_chip,
    build_risk_event_center_card,
    build_risk_event_center_content,
    build_runtime_table_card,
    build_runtime_table_content,
)


# ---------------------------------------------------------------------------
# _runtime_status_chip / _risk_severity_chip
# ---------------------------------------------------------------------------


def test_runtime_status_chip_running():
    chip = _runtime_status_chip("running")
    text = str(chip)
    assert "running" in text


def test_runtime_status_chip_blocked():
    chip = _runtime_status_chip("blocked")
    text = str(chip)
    assert "blocked" in text


def test_runtime_status_chip_failed():
    chip = _runtime_status_chip("failed")
    text = str(chip)
    assert "failed" in text


def test_runtime_status_chip_unknown_status():
    chip = _runtime_status_chip("weird")
    text = str(chip)
    assert "weird" in text


def test_risk_severity_chip_critical():
    chip = _risk_severity_chip("critical")
    text = str(chip)
    assert "critical" in text


def test_risk_severity_chip_warning():
    chip = _risk_severity_chip("warning")
    text = str(chip)
    assert "warning" in text


def test_risk_severity_chip_info_default():
    chip = _risk_severity_chip("info")
    text = str(chip)
    assert "info" in text


def test_risk_severity_chip_unknown_severity():
    """Severity other than critical/warning falls to default."""
    chip = _risk_severity_chip("debug")
    text = str(chip)
    assert "debug" in text


# ---------------------------------------------------------------------------
# _build_risk_event_rows
# ---------------------------------------------------------------------------


def test_build_risk_event_rows_with_events():
    events = [
        {
            "severity": "critical",
            "title": "Test",
            "message": "Critical alarm",
            "scope": "account",
            "created_at": "2024-01-01 10:00",
        }
    ]
    rows = _build_risk_event_rows(events)
    text = str(rows)
    assert "Test" in text or len(rows) >= 1


def test_build_risk_event_rows_empty_returns_placeholder():
    rows = _build_risk_event_rows([])
    # Returns a placeholder row.
    text = str(rows)
    assert "暂无风险事件" in text or len(rows) == 1


# ---------------------------------------------------------------------------
# _build_runtime_actions
# ---------------------------------------------------------------------------


def test_build_runtime_actions_no_actions():
    """Item with no can_* flags returns empty list."""
    item = {"runtime_id": "x", "can_stop": False, "can_start": False,
            "can_block_account": False, "can_unblock_account": False,
            "can_block_strategy": False, "can_unblock_strategy": False,
            "strategy_id": ""}
    actions = _build_runtime_actions(item, "/api", "#table")
    assert actions == []


def test_build_runtime_actions_with_stop():
    item = {"runtime_id": "x", "can_stop": True, "can_start": False,
            "can_block_account": False, "can_unblock_account": False,
            "can_block_strategy": False, "can_unblock_strategy": False,
            "strategy_id": ""}
    actions = _build_runtime_actions(item, "/api", "#table")
    text = str(actions)
    assert "停止" in text


def test_build_runtime_actions_with_start():
    item = {"runtime_id": "x", "can_stop": False, "can_start": True,
            "can_block_account": False, "can_unblock_account": False,
            "can_block_strategy": False, "can_unblock_strategy": False,
            "strategy_id": ""}
    actions = _build_runtime_actions(item, "/api", "#table")
    text = str(actions)
    assert "启动" in text


def test_build_runtime_actions_with_block_account():
    item = {"runtime_id": "x", "can_stop": False, "can_start": False,
            "can_block_account": True, "can_unblock_account": False,
            "can_block_strategy": False, "can_unblock_strategy": False,
            "strategy_id": ""}
    actions = _build_runtime_actions(item, "/api", "#table")
    text = str(actions)
    assert "封锁账户" in text


def test_build_runtime_actions_with_unblock_account():
    item = {"runtime_id": "x", "can_stop": False, "can_start": False,
            "can_block_account": False, "can_unblock_account": True,
            "can_block_strategy": False, "can_unblock_strategy": False,
            "strategy_id": ""}
    actions = _build_runtime_actions(item, "/api", "#table")
    text = str(actions)
    assert "解除账户封锁" in text


def test_build_runtime_actions_with_block_strategy():
    item = {"runtime_id": "x", "can_stop": False, "can_start": False,
            "can_block_account": False, "can_unblock_account": False,
            "can_block_strategy": True, "can_unblock_strategy": False,
            "strategy_id": "s1"}
    actions = _build_runtime_actions(item, "/api", "#table")
    text = str(actions)
    assert "封锁策略" in text


def test_build_runtime_actions_with_unblock_strategy():
    item = {"runtime_id": "x", "can_stop": False, "can_start": False,
            "can_block_account": False, "can_unblock_account": False,
            "can_block_strategy": False, "can_unblock_strategy": True,
            "strategy_id": "s1"}
    actions = _build_runtime_actions(item, "/api", "#table")
    text = str(actions)
    assert "解除策略封锁" in text


def test_build_runtime_actions_blocked_scope_account():
    """When blocked_scope == account and strategy_id set, shows info span."""
    item = {"runtime_id": "x", "can_stop": False, "can_start": False,
            "can_block_account": False, "can_unblock_account": False,
            "can_block_strategy": False, "can_unblock_strategy": False,
            "blocked_scope": "account", "strategy_id": "s1"}
    actions = _build_runtime_actions(item, "/api", "#table")
    text = str(actions)
    assert "请在账户行解除封控" in text


# ---------------------------------------------------------------------------
# build_risk_event_center_content / build_risk_event_center_card
# ---------------------------------------------------------------------------


def test_build_risk_event_center_content():
    with patch(
        "quantide.web.pages.system.runtime_support.strategy_runtime_manager"
    ) as mock_mgr:
        mock_mgr.risk_summary.return_value = {
            "blocked_accounts": 1,
            "blocked_strategies": 2,
            "open_events": 3,
            "event_count": 4,
        }
        mock_mgr.list_risk_events.return_value = []
        content = build_risk_event_center_content(limit=5)
    text = str(content)
    assert "风险事件中心" in text
    assert mock_mgr.risk_summary.called
    assert mock_mgr.list_risk_events.called


def test_build_risk_event_center_with_events():
    """When events present, table is populated."""
    events = [
        {"severity": "warning", "title": "E1", "message": "m",
         "scope": "scope-1", "created_at": "2024-01-01"}
    ]
    with patch(
        "quantide.web.pages.system.runtime_support.strategy_runtime_manager"
    ) as mock_mgr:
        mock_mgr.risk_summary.return_value = {
            "blocked_accounts": 0, "blocked_strategies": 0,
            "open_events": 0, "event_count": 1,
        }
        mock_mgr.list_risk_events.return_value = events
        content = build_risk_event_center_content(limit=5)
    text = str(content)
    assert "E1" in text


def test_build_risk_event_center_card_renders_div():
    card = build_risk_event_center_card("/refresh", limit=5)
    text = str(card)
    assert "risk-event-center" in text  # id attribute survives in Div repr


# ---------------------------------------------------------------------------
# build_runtime_table_content / build_runtime_table_card
# ---------------------------------------------------------------------------


def test_build_runtime_table_content():
    with patch(
        "quantide.web.pages.system.runtime_support.strategy_runtime_manager"
    ) as mock_mgr:
        mock_mgr.list_runtime_rows.return_value = []
        content = build_runtime_table_content("/api", "#table")
    text = str(content)
    assert "运行时监控" in text
    assert mock_mgr.list_runtime_rows.called


def test_build_runtime_table_content_with_runtimes():
    """With runtime rows, the table renders them."""
    items = [
        {
            "runtime_id": "r1",
            "mode": "paper",
            "portfolio_id": "p1",
            "strategy_name": "S",
            "strategy_id": "s1",
            "status": "running",
            "alert_text": "",
            "total": 100000.0,
            "positions": 0,
            "orders": 0,
            "updated_at": "2024-01-01 10:00",
            "can_stop": True,
            "can_start": False,
            "can_block_account": False,
            "can_unblock_account": False,
            "can_block_strategy": False,
            "can_unblock_strategy": False,
            "blocked_scope": "",
        }
    ]
    with patch(
        "quantide.web.pages.system.runtime_support.strategy_runtime_manager"
    ) as mock_mgr:
        mock_mgr.list_runtime_rows.return_value = items
        content = build_runtime_table_content("/api", "#table")
    text = str(content)
    assert "r1" in text


def test_build_runtime_table_card_renders_div():
    card = build_runtime_table_card("/refresh", "/api", "#table")
    text = str(card)
    # The id attribute is the target_selector with # stripped
    assert "table" in text

"""B08-runtime-monitor-2: Test stop/start/block/unblock routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.pages.system.runtime_monitor import (
    block,
    start,
    stop,
    unblock,
)


def _request(form_data=None):
    req = MagicMock()
    req.form = AsyncMock(return_value=form_data or {})
    return req


@pytest.mark.asyncio
async def test_stop_with_runtime_id():
    """stop route with valid runtime_id calls manager and returns response."""
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        mock_mgr.stop_strategy_runtime = MagicMock()
        resp = await stop(_request({"runtime_id": "r1"}))
    mock_mgr.stop_strategy_runtime.assert_called_once_with("r1")
    assert resp is not None


@pytest.mark.asyncio
async def test_stop_with_no_runtime_id_no_op():
    """stop route without runtime_id does nothing."""
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await stop(_request({}))
    mock_mgr.stop_strategy_runtime.assert_not_called()
    assert resp is not None


@pytest.mark.asyncio
async def test_stop_handles_exception():
    """stop route swallows manager exceptions."""
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        mock_mgr.stop_strategy_runtime.side_effect = RuntimeError("boom")
        resp = await stop(_request({"runtime_id": "r1"}))
    assert resp is not None


@pytest.mark.asyncio
async def test_start_with_runtime_id():
    """start route with runtime_id calls manager."""
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await start(_request({"runtime_id": "r1"}))
    mock_mgr.start_strategy_runtime.assert_called_once_with("r1")
    assert resp is not None


@pytest.mark.asyncio
async def test_start_handles_exception():
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        mock_mgr.start_strategy_runtime.side_effect = RuntimeError("boom")
        resp = await start(_request({"runtime_id": "r1"}))
    assert resp is not None


@pytest.mark.asyncio
async def test_block_account():
    """block with target_kind='account' calls block_account."""
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await block(_request({"target_kind": "account", "target_id": "a1"}))
    mock_mgr.block_account.assert_called_once_with("a1")
    mock_mgr.block_strategy.assert_not_called()
    assert resp is not None


@pytest.mark.asyncio
async def test_block_strategy():
    """block with target_kind='strategy' calls block_strategy."""
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await block(_request({"target_kind": "strategy", "target_id": "s1"}))
    mock_mgr.block_strategy.assert_called_once_with("s1")
    mock_mgr.block_account.assert_not_called()
    assert resp is not None


@pytest.mark.asyncio
async def test_block_unknown_kind_no_op():
    """block with unknown kind does nothing."""
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await block(_request({"target_kind": "other", "target_id": "x"}))
    mock_mgr.block_account.assert_not_called()
    mock_mgr.block_strategy.assert_not_called()
    assert resp is not None


@pytest.mark.asyncio
async def test_block_empty_target_no_op():
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await block(_request({"target_kind": "account"}))
    mock_mgr.block_account.assert_not_called()
    assert resp is not None


@pytest.mark.asyncio
async def test_unblock_account():
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await unblock(_request({"target_kind": "account", "target_id": "a1"}))
    mock_mgr.unblock_account.assert_called_once_with("a1")
    assert resp is not None


@pytest.mark.asyncio
async def test_unblock_strategy():
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await unblock(_request({"target_kind": "strategy", "target_id": "s1"}))
    mock_mgr.unblock_strategy.assert_called_once_with("s1")
    assert resp is not None


@pytest.mark.asyncio
async def test_unblock_unknown_kind_no_op():
    with patch(
        "quantide.web.pages.system.runtime_monitor.strategy_runtime_manager"
    ) as mock_mgr:
        resp = await unblock(_request({"target_kind": "other", "target_id": "x"}))
    mock_mgr.unblock_account.assert_not_called()
    mock_mgr.unblock_strategy.assert_not_called()
    assert resp is not None

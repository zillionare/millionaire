"""Wizard progress reflects durable tasks and waits for cancellation."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from quantide.web.pages import init_wizard as iw
from quantide.web.pages import wizard_state, wizard_sync


def _reset_sync_status():
    wizard_state._sync_status.update(
        is_running=True, progress=45, stage="pre-stage", message="pre-msg",
        completed=False, error=None,
    )
    wizard_state._download_error_message = None


def _make_request():
    return SimpleNamespace(query_params={})


@pytest.mark.parametrize("task", [None])
def test_missing_task_preserves_visible_progress(task):
    _reset_sync_status()
    wizard_sync._apply_task_progress(task)
    assert wizard_state._sync_status["progress"] == 45
    assert wizard_state._sync_status["error"] is None


def test_pipeline_error_persists_in_header():
    _reset_sync_status()
    wizard_sync._apply_task_progress(SimpleNamespace(error="boom-network"))
    assert wizard_state._download_error_message == "下载失败：boom-network"
    assert wizard_state._sync_status["error"] == "boom-network"
    assert wizard_state._sync_status["message"] == "同步失败: boom-network"
    assert wizard_state._sync_status["progress"] == 45
    assert wizard_state._sync_status["completed"] is False


@pytest.mark.parametrize("progress,expected", [(0, 0), (42, 42), (100, 99)])
@pytest.mark.parametrize("message", ["minute_bars 50/100", ""])
def test_persisted_progress_never_completes_initialization(progress, expected, message):
    _reset_sync_status()
    wizard_sync._apply_task_progress(SimpleNamespace(error="", progress=progress, message=message))
    assert wizard_state._sync_status["progress"] == expected
    assert wizard_state._sync_status["message"] == (message or "正在同步数据")
    assert wizard_state._sync_status["completed"] is False


async def test_shutdown_waits_for_sync_worker(monkeypatch):
    entered, stopped = threading.Event(), threading.Event()
    service = MagicMock()
    service.get_task.return_value = SimpleNamespace(error="", progress=25, message="daily_bars")

    def run(task_id):
        assert task_id == "owned"
        entered.set()
        assert stopped.wait(5)
        return False

    service.run.side_effect = run
    service.cancel.side_effect = stopped.set
    monkeypatch.setattr(wizard_sync, "data_sync_service", service)
    task = asyncio.create_task(wizard_sync._wait_for_pipeline("owned"))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    service.cancel.assert_called_once()


async def test_sync_progress_running_then_completes_emits_two_events(monkeypatch):
    """[B11] Lines 2073-2077: running status yields, sleeps, then breaks on completion.

    The first iteration emits a "running" event, then since completed/error are
    both falsy, hits ``await asyncio.sleep(0.5)`` (line 2077). The patched sleep
    flips ``completed`` to True so the second iteration emits a "completed"
    event and breaks via line 2074.
    """
    _reset_sync_status()
    wizard_state._sync_status["completed"] = False
    wizard_state._sync_status["error"] = None
    wizard_state._sync_status["progress"] = 30
    wizard_state._sync_status["message"] = "syncing"
    wizard_state._sync_status["stage"] = "running"

    call_count = {"n": 0}

    async def _fake_sleep(seconds: float) -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            wizard_state._sync_status["completed"] = True
            wizard_state._sync_status["progress"] = 100
            wizard_state._sync_status["message"] = "done"

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    resp = await iw.sync_progress(_make_request())

    chunks: list[str] = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)

    # Two yields: first while running, second after completed=True (then break).
    assert len(chunks) == 2
    assert call_count["n"] == 1  # sleep was called exactly once

    import json as _json

    first = _json.loads(chunks[0].removeprefix("data: ").strip())
    second = _json.loads(chunks[1].removeprefix("data: ").strip())
    assert first["completed"] is False
    assert first["progress"] == 30
    assert second["completed"] is True
    assert second["progress"] == 100
    assert second["message"] == "done"

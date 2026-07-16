"""B11-init-wizard: targeted coverage for ``quantide/web/pages/init_wizard.py``.

Drives the previously-uncovered ``_on_fetch_progress`` closure (defined inside
``_run_data_sync``) and the SSE generator's sleep/break loop in ``sync_progress``.

Strategy for the closure: run ``_run_data_sync`` once with every external
dependency mocked out, capturing the ``_on_fetch_progress`` callback via a
mocked ``msg_hub.subscribe``. The closure only references module globals and
the local ``stage_label``/``stage_offset`` dicts (kept alive by the closure
itself), so it remains callable after ``_run_data_sync`` returns. Each test
then resets ``_sync_status`` and invokes the captured callback with a crafted
payload to hit a specific branch.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any
from unittest.mock import MagicMock

import pytest

from quantide.web.pages import init_wizard as iw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_sync_status() -> None:
    """Reset the module-level ``_sync_status`` to a clean running state."""
    iw._sync_status.update(
        {
            "is_running": False,
            "current_task": "",
            "progress": 45,
            "stage": "pre-stage",
            "message": "pre-msg",
            "completed": False,
            "error": None,
        }
    )
    iw._download_error_message = None


def _capture_progress_callback(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run ``_run_data_sync`` with mocked deps; return the captured callback.

    All I/O collaborators (init_data, calendar, stock_list, daily_bars,
    msg_hub, init_wizard) are stubbed so the coroutine runs to completion
    quickly while still defining the ``_on_fetch_progress`` closure and
    registering it via ``msg_hub.subscribe``.
    """
    captured: dict[str, Any] = {}

    def _fake_subscribe(topic: str, callback: Any) -> None:
        if topic == "fetch_data_progress":
            captured["cb"] = callback

    fake_state = MagicMock()
    fake_state.app_home = "/tmp/data"
    fake_state.history_start_date = dt.date(2024, 1, 1)
    fake_state.epoch = dt.date(2024, 1, 1)

    monkeypatch.setattr(iw.msg_hub, "subscribe", _fake_subscribe)
    monkeypatch.setattr(iw.msg_hub, "unsubscribe", lambda topic, cb: None)
    monkeypatch.setattr(iw.init_wizard, "get_state", lambda force_refresh=False: fake_state)
    monkeypatch.setattr(iw.init_wizard, "complete_initialization", MagicMock())

    import quantide.data as data_mod

    monkeypatch.setattr(data_mod, "init_data", MagicMock())

    # Replace the model singletons wholesale so property-style attributes
    # (e.g. StockList.size) are mockable without fighting class-level descriptors.
    fake_calendar = MagicMock()
    fake_calendar.last_trade_date = lambda: dt.date(2024, 6, 17)
    monkeypatch.setattr(iw, "calendar", fake_calendar)

    fake_stock_list = MagicMock()
    fake_stock_list.size = 100
    monkeypatch.setattr(iw, "stock_list", fake_stock_list)

    monkeypatch.setattr(iw, "daily_bars", MagicMock())

    asyncio.run(iw._run_data_sync(dt.date(2024, 1, 1)))

    assert "cb" in captured, "fetch_data_progress callback was not captured"
    return captured["cb"]


def _make_request() -> MagicMock:
    req = MagicMock()
    req.query_params = {}
    return req


# ---------------------------------------------------------------------------
# _on_fetch_progress closure branches (lines 1740-1781)
# ---------------------------------------------------------------------------


def test_on_fetch_progress_ignores_non_dict_payload(monkeypatch):
    """[B11] Lines 1740-1741: non-dict payload returns early without raising."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()
    for payload in ("not-a-dict", None, ["list", "not", "dict"], 42):
        cb(payload)  # must not raise
    assert iw._sync_status["progress"] == 45
    assert iw._sync_status["stage"] == "pre-stage"
    assert iw._download_error_message is None


def test_on_fetch_progress_error_payload_sets_download_error(monkeypatch):
    """[B11] Lines 1742-1751: error payload records download error and fails sync."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()
    iw._sync_status["progress"] = 47

    cb({"error": "boom-network"})

    assert iw._download_error_message == "下载失败：boom-network"
    assert iw._sync_status["error"] == "boom-network"
    assert iw._sync_status["stage"] == "同步失败"
    assert iw._sync_status["message"] == "同步失败: boom-network"
    # Progress is preserved from the incoming _sync_status (not overwritten).
    assert iw._sync_status["progress"] == 47


def test_on_fetch_progress_msg_only_updates_stage_message(monkeypatch):
    """[B11] Lines 1752-1760: msg-only payload (no completed/total) updates stage+message."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()
    iw._sync_status["progress"] = 50

    cb({"msg": "  正在下载 XYZ  "})

    assert iw._sync_status["stage"] == "正在下载 XYZ"
    # message falls back to the existing message when not provided explicitly.
    assert iw._sync_status["message"] == "pre-msg"
    assert iw._sync_status["progress"] == 50  # unchanged


def test_on_fetch_progress_msg_only_blank_skips_update(monkeypatch):
    """[B11] Lines 1752-1754, 1760: blank msg payload skips the status update."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()
    iw._sync_status["stage"] = "unchanged-stage"
    iw._sync_status["message"] = "unchanged-msg"

    cb({"msg": "   "})

    # No update performed: state preserved.
    assert iw._sync_status["stage"] == "unchanged-stage"
    assert iw._sync_status["message"] == "unchanged-msg"


def test_on_fetch_progress_missing_completed_and_total_returns(monkeypatch):
    """[B11] Lines 1761-1762: payload without completed/total keys returns early."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()
    iw._sync_status["stage"] = "frozen-stage"

    cb({"unrelated": "value"})

    assert iw._sync_status["stage"] == "frozen-stage"
    assert iw._sync_status["progress"] == 45


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"completed": 5, "total": 0}, id="zero-total"),
        pytest.param({"completed": 0, "total": 5}, id="zero-completed"),
        pytest.param({"completed": -3, "total": 10}, id="negative-completed"),
    ],
)
def test_on_fetch_progress_nonpositive_counts_returns(monkeypatch, payload):
    """[B11] Lines 1763-1767: completed/total parsed but nonpositive -> early return."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()
    iw._sync_status["stage"] = "frozen-stage"

    cb(payload)

    assert iw._sync_status["stage"] == "frozen-stage"
    assert iw._sync_status["progress"] == 45


def test_on_fetch_progress_valid_payload_computes_progress(monkeypatch):
    """[B11] Lines 1768-1771, 1776-1781: valid payload computes progress and updates status."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()

    cb(
        {
            "completed": 3,
            "total": 10,
            "current_date": "2024-06-17",
            "phase": "bars",
        }
    )

    # progress = 45 + int((((max(3,1)-1) + 0.10) / max(10,1)) * 50)
    #        = 45 + int((2.1 / 10) * 50) = 45 + int(10.5) = 55
    assert iw._sync_status["progress"] == 55
    assert iw._sync_status["stage"] == "正在同步历史日线行情"
    assert iw._sync_status["message"] == "正在同步 2024年06月17日，当前进度 3/10"
    assert iw._sync_status["completed"] is False
    assert iw._sync_status["error"] is None


def test_on_fetch_progress_unparseable_date_falls_back_to_raw_string(monkeypatch):
    """[B11] Lines 1772-1773: unparseable current_date falls back to the raw string."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()

    cb(
        {
            "completed": 3,
            "total": 10,
            "current_date": "not-a-date",
            "phase": "adjust",
        }
    )

    # current_date_zh falls back to "not-a-date" (truthy) -> continues to update.
    assert iw._sync_status["message"] == "正在同步 not-a-date，当前进度 3/10"
    assert iw._sync_status["stage"] == "正在同步复权因子"
    # progress still computed: phase_ratio=0.35 -> 45 + int((2.35/10)*50) = 45 + 11 = 56
    assert iw._sync_status["progress"] == 56


def test_on_fetch_progress_empty_date_returns_early(monkeypatch):
    """[B11] Lines 1774-1775: when current_date_zh ends up empty, return early."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()
    iw._sync_status["stage"] = "frozen-stage"

    cb({"completed": 3, "total": 10, "current_date": ""})

    # strptime("") fails -> current_date_zh = "" -> falsy -> return.
    assert iw._sync_status["stage"] == "frozen-stage"
    assert iw._sync_status["progress"] == 45


def test_on_fetch_progress_unknown_phase_uses_default_label(monkeypatch):
    """[B11] Lines 1776, 1781: unknown phase falls back to default stage_offset/label."""
    cb = _capture_progress_callback(monkeypatch)
    _reset_sync_status()

    cb(
        {
            "completed": 5,
            "total": 10,
            "current_date": "2024-06-17",
            "phase": "mystery-phase",
        }
    )

    # phase_ratio default = 1.0 -> progress = 45 + int(((4 + 1.0)/10)*50) = 45 + 25 = 70
    assert iw._sync_status["progress"] == 70
    assert iw._sync_status["stage"] == "正在同步数据"
    assert iw._sync_status["message"] == "正在同步 2024年06月17日，当前进度 5/10"


# ---------------------------------------------------------------------------
# sync_progress SSE generator loop (lines 2073-2077)
# ---------------------------------------------------------------------------


async def test_sync_progress_running_then_completes_emits_two_events(monkeypatch):
    """[B11] Lines 2073-2077: running status yields, sleeps, then breaks on completion.

    The first iteration emits a "running" event, then since completed/error are
    both falsy, hits ``await asyncio.sleep(0.5)`` (line 2077). The patched sleep
    flips ``completed`` to True so the second iteration emits a "completed"
    event and breaks via line 2074.
    """
    _reset_sync_status()
    iw._sync_status["completed"] = False
    iw._sync_status["error"] = None
    iw._sync_status["progress"] = 30
    iw._sync_status["message"] = "syncing"
    iw._sync_status["stage"] = "running"

    call_count = {"n": 0}

    async def _fake_sleep(seconds: float) -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            iw._sync_status["completed"] = True
            iw._sync_status["progress"] = 100
            iw._sync_status["message"] = "done"

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

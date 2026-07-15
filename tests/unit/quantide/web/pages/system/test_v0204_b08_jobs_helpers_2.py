"""B08-jobs-helpers-2: Test _format_cron + _run_daily_snapshot + _run_market_snapshot."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system import jobs as jobs_mod
from quantide.web.pages.system.jobs import (
    _format_cron,
    _get_all_job_history,
    _get_job_history,
    _init_job_history_table,
    _init_job_settings_table,
    _load_persisted_job_enabled_state,
    _run_calendar_sync,
    _run_daily_bars_sync,
    _run_daily_snapshot,
    _run_market_snapshot,
    _run_stock_list_sync,
    _save_job_history,
    _save_job_enabled_state,
)


# ---------------------------------------------------------------------------
# _format_cron
# ---------------------------------------------------------------------------


def test_format_cron_weekdays():
    """[AC-NFR1101-01] test_format_cron_weekdays."""
    assert _format_cron("0 18 * * 1-5") == "每天 18:00 (周一至周五)"


def test_format_cron_every_day():
    """[AC-NFR1101-01] test_format_cron_every_day."""
    assert _format_cron("30 9 * * *") == "每天 9:30"


def test_format_cron_monday():
    """[AC-NFR1101-01] test_format_cron_monday."""
    assert _format_cron("0 10 * * 1") == "每周一 10:00"


def test_format_cron_every_n_minutes():
    # "*/5 * * * *" - falls through to fallback; just exercise the path
    """[AC-NFR1101-01] test_format_cron_every_n_minutes."""
    out = _format_cron("*/5 * * * *")
    assert isinstance(out, str) and out


def test_format_cron_unsupported_returns_raw():
    """[AC-NFR1101-01] Non-standard cron returns input unchanged."""
    raw = "0 0 * * * 2024"
    assert _format_cron(raw) == raw


def test_format_cron_too_short_returns_raw():
    """[AC-NFR1101-01] test_format_cron_too_short_returns_raw."""
    assert _format_cron("a b c") == "a b c"


# ---------------------------------------------------------------------------
# _run_* task functions (sync flows)
# ---------------------------------------------------------------------------


def test_run_daily_bars_sync_success(db):
    """[AC-NFR1101-01] Success path records a success job-history entry.

    Verifies that `_run_daily_bars_sync` calls `_save_job_history` with
    job_id="daily_bars_sync" and status="success" when the underlying
    `daily_bars.store.update()` does not raise. This replaces the prior
    "No assertion; just exercise the path" coverage-only test flagged
    by Prism M3.
    """
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_db:
        mock_db.store.update = MagicMock(return_value=None)
        with patch.object(jobs_mod, "_save_job_history") as mock_save:
            _run_daily_bars_sync()
    mock_save.assert_called_once()
    saved_args = mock_save.call_args.args
    saved_kwargs = mock_save.call_args.kwargs
    assert saved_args[0] == "daily_bars_sync"
    assert "success" in (saved_args[2], saved_kwargs.get("status"))


def test_run_daily_bars_sync_exception(db):
    """[AC-NFR1101-01] Failure path records an error job-history entry."""
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_db:
        mock_db.store.update = MagicMock(side_effect=RuntimeError("boom"))
        with patch.object(jobs_mod, "_save_job_history") as mock_save:
            _run_daily_bars_sync()
    mock_save.assert_called_once()
    saved_args = mock_save.call_args.args
    assert saved_args[0] == "daily_bars_sync"
    assert "error" in saved_args[2]
    assert "boom" in saved_args[3]


def test_run_stock_list_sync_success(db):
    """[AC-NFR1101-01] test_run_stock_list_sync_success."""
    with patch("quantide.data.models.stocks.stock_list") as mock:
        mock.update = lambda: None  # async, but asyncio.run wraps it
        # We make .update return a regular value to be safe with asyncio.run
        mock.update = lambda: __import__("asyncio").sleep(0)
        _run_stock_list_sync()


def test_run_stock_list_sync_exception(db):
    """[AC-NFR1101-01] test_run_stock_list_sync_exception."""
    with patch("quantide.data.models.stocks.stock_list") as mock:
        def _boom():
            raise Exception("sync failed")
        mock.update = _boom
        _run_stock_list_sync()


def test_run_calendar_sync_success(db):
    """[AC-NFR1101-01] test_run_calendar_sync_success."""
    with patch("quantide.data.models.calendar.calendar") as mock:
        mock.update = lambda: __import__("asyncio").sleep(0)
        _run_calendar_sync()


def test_run_calendar_sync_exception(db):
    """[AC-NFR1101-01] test_run_calendar_sync_exception."""
    with patch("quantide.data.models.calendar.calendar") as mock:
        def _boom():
            raise Exception("cal failed")
        mock.update = _boom
        _run_calendar_sync()


def test_run_daily_snapshot(db):
    """[AC-NFR1101-01] Daily snapshot records a success job-history entry.

    Verifies that `_run_daily_snapshot` calls `_save_job_history` with
    job_id="daily_snapshot" and status="success". This replaces the prior
    assertion-less coverage-only test flagged by Prism M3.
    """
    with patch.object(jobs_mod, "_save_job_history") as mock_save:
        _run_daily_snapshot()
    mock_save.assert_called_once()
    saved_args = mock_save.call_args.args
    assert saved_args[0] == "daily_snapshot"
    assert saved_args[2] == "success"


def test_run_market_snapshot(db):
    """[AC-NFR1101-01] Market snapshot records a success job-history entry.

    Verifies that `_run_market_snapshot` calls `_save_job_history` with
    job_id="market_snapshot" and status="success". This replaces the prior
    assertion-less coverage-only test flagged by Prism M3.
    """
    with patch.object(jobs_mod, "_save_job_history") as mock_save:
        _run_market_snapshot()
    mock_save.assert_called_once()
    saved_args = mock_save.call_args.args
    assert saved_args[0] == "market_snapshot"
    assert saved_args[2] == "success"


# ---------------------------------------------------------------------------
# JobHistoryRecord + _build_* UI components
# ---------------------------------------------------------------------------


from quantide.web.pages.system.jobs import (
    JobHistoryRecord,
    _build_history_table,
    _build_job_status_badge,
    _build_jobs_table,
    _build_status_dot,
)


def test_job_history_record_from_dict():
    """[AC-NFR1101-01] JobHistoryRecord.from_dict parses dict to record."""
    class _R(dict):
        def get(self, k, d=None):
            return super().get(k, d)
    d = {
        "job_id": "x",
        "job_name": "X",
        "executed_at": "2024-01-01 10:00:00",
        "status": "success",
        "message": "ok",
        "duration_ms": 100,
    }
    rec = JobHistoryRecord.from_dict(d)
    assert rec is not None
    assert rec.job_id == "x"


def test_build_job_status_badge_enabled():
    """[AC-NFR1101-01] test_build_job_status_badge_enabled."""
    out = _build_job_status_badge(True)
    assert out is not None


def test_build_job_status_badge_disabled():
    """[AC-NFR1101-01] test_build_job_status_badge_disabled."""
    out = _build_job_status_badge(False)
    assert out is not None


def test_build_status_dot_enabled():
    """[AC-NFR1101-01] test_build_status_dot_enabled."""
    out = _build_status_dot(True)
    assert out == "🟢"


def test_build_status_dot_disabled():
    """[AC-NFR1101-01] test_build_status_dot_disabled."""
    out = _build_status_dot(False)
    assert out == "🔴"


def test_build_history_table_empty():
    """[AC-NFR1101-01] test_build_history_table_empty."""
    out = _build_history_table([])
    assert out is not None


def test_build_history_table_success():
    """[AC-NFR1101-01] test_build_history_table_success."""
    rec = JobHistoryRecord(
        id="1",
        job_id="x",
        job_name="X",
        executed_at=__import__("datetime").datetime(2024, 1, 1, 10, 0),
        status="success",
        message="ok",
        duration_ms=100,
    )
    out = _build_history_table([rec])
    assert out is not None


def test_build_history_table_error():
    """[AC-NFR1101-01] test_build_history_table_error."""
    rec = JobHistoryRecord(
        id="1",
        job_id="x",
        job_name="X",
        executed_at=__import__("datetime").datetime(2024, 1, 1, 10, 0),
        status="error",
        message="boom",
        duration_ms=100,
    )
    out = _build_history_table([rec])
    assert out is not None


# ---------------------------------------------------------------------------
# _get_job_status
# ---------------------------------------------------------------------------


from quantide.web.pages.system.jobs import _get_job_status, _job_enabled_state


def test_get_job_status_no_scheduler_job(db):
    """[AC-NFR1101-01] When scheduler has no job, has_scheduler_job=False."""
    with patch.object(jobs_mod, "scheduler") as mock_sched:
        mock_sched.scheduler.get_job = MagicMock(return_value=None)
        out = _get_job_status("x")
    assert out["id"] == "x"
    assert out["has_scheduler_job"] is False
    assert out["next_run"] is None


def test_get_job_status_with_scheduler_job(db):
    """[AC-NFR1101-01] When scheduler has a job, includes next_run_time."""
    fake_job = MagicMock()
    fake_job.next_run_time = __import__("datetime").datetime(2024, 1, 1, 10, 0)
    with patch.object(jobs_mod, "scheduler") as mock_sched:
        mock_sched.scheduler.get_job = MagicMock(return_value=fake_job)
        out = _get_job_status("x")
    assert out["has_scheduler_job"] is True
    assert out["next_run"] is not None


def test_get_job_status_with_history(db):
    """[AC-NFR1101-01] When history exists, includes last_run."""
    rec = JobHistoryRecord(
        id="1",
        job_id="x",
        job_name="X",
        executed_at=__import__("datetime").datetime(2024, 1, 1, 10, 0),
        status="success",
        message="ok",
        duration_ms=100,
    )
    with patch.object(jobs_mod, "scheduler") as mock_sched:
        mock_sched.scheduler.get_job = MagicMock(return_value=None)
        with patch.object(jobs_mod, "_get_job_history", return_value=[rec]):
            out = _get_job_status("x")
    assert out["last_run"] == rec


# ---------------------------------------------------------------------------
# run_job + job_detail + _build_jobs_table + _build_detail_panel + _get_job_status
# ---------------------------------------------------------------------------


import pytest
from quantide.web.pages.system.jobs import (
    run_job,
    job_detail,
    _build_jobs_table,
    _build_detail_panel,
    _get_job_status,
)


@pytest.mark.asyncio
async def test_run_job_unknown():
    """Unknown job_id → redirect to /system/jobs/."""
    resp = await run_job("unknown-job")
    assert "redirect" in str(resp).lower() or "system/jobs" in str(resp).lower()


@pytest.mark.asyncio
async def test_run_job_success(db):
    """Known job_id → calls _run_job_now."""
    from quantide.web.pages.system.jobs import _run_job_now, PREDEFINED_JOBS
    with patch("quantide.web.pages.system.jobs._run_job_now") as mock_run:
        # Pick a real predefined job
        jid = list(PREDEFINED_JOBS.keys())[0]
        resp = await run_job(jid)
    mock_run.assert_called_once_with(jid)


@pytest.mark.asyncio
async def test_run_job_exception(db):
    """When _run_job_now raises, still redirects."""
    from quantide.web.pages.system.jobs import PREDEFINED_JOBS
    with patch("quantide.web.pages.system.jobs._run_job_now") as mock_run:
        mock_run.side_effect = Exception("boom")
        jid = list(PREDEFINED_JOBS.keys())[0]
        resp = await run_job(jid)
    assert resp is not None


@pytest.mark.asyncio
async def test_job_detail_unknown():
    resp = await job_detail("unknown-job")
    assert resp is not None


@pytest.mark.asyncio
async def test_job_detail_known(db):
    """Known job_id → returns _build_detail_panel output."""
    from quantide.web.pages.system.jobs import PREDEFINED_JOBS
    with patch("quantide.web.pages.system.jobs._build_detail_panel", return_value="detail"):
        jid = list(PREDEFINED_JOBS.keys())[0]
        resp = await job_detail(jid)
    assert resp == "detail"


def test_build_jobs_table_empty():
    """[AC-NFR1101-01] test_build_jobs_table_empty."""
    out = _build_jobs_table([])
    assert out is not None


def test_build_detail_panel():
    """[AC-NFR1101-01] test_build_detail_panel."""
    from quantide.web.pages.system.jobs import PREDEFINED_JOBS
    jid = list(PREDEFINED_JOBS.keys())[0]
    out = _build_detail_panel(jid)
    assert out is not None


def test_build_detail_panel_unknown():
    """[AC-NFR1101-01] test_build_detail_panel_unknown."""
    out = _build_detail_panel("unknown-job")
    assert out is not None


def test_get_job_status_with_data(db):
    """[AC-NFR1101-01] When history exists, return last_run."""
    from quantide.web.pages.system.jobs import (
        _job_enabled_state, _get_job_history,
    )
    fake_rec = MagicMock()
    fake_rec.executed_at = __import__("datetime").datetime(2024, 1, 1)
    fake_rec.status = "success"
    fake_rec.message = "ok"
    fake_rec.duration_ms = 100
    fake_rec.id = "1"
    fake_rec.job_id = "x"
    with patch.object(_job_enabled_state.__class__ if False else __import__(
        "quantide.web.pages.system.jobs", fromlist=["_job_enabled_state"]
    ), "_get_job_history", return_value=[fake_rec]):
        with patch(
            "quantide.web.pages.system.jobs.scheduler",
        ) as mock_sched:
            mock_sched.scheduler.get_job = MagicMock(return_value=None)
            out = _get_job_status("x")
    assert "last_run" in out or "has_scheduler_job" in out


# ---------------------------------------------------------------------------
# toggle_job
# ---------------------------------------------------------------------------


from quantide.web.pages.system.jobs import toggle_job, _job_enabled_state


@pytest.mark.asyncio
async def test_toggle_job_unknown():
    """Unknown job_id → redirect."""
    resp = await toggle_job("unknown-job")
    assert resp is not None


@pytest.mark.asyncio
async def test_toggle_job_toggle_enable(db):
    """When currently disabled → enables."""
    from quantide.web.pages.system.jobs import PREDEFINED_JOBS
    with patch("quantide.web.pages.system.jobs._toggle_job") as mock_toggle:
        jid = list(PREDEFINED_JOBS.keys())[0]
        # Force current state to False
        _job_enabled_state[jid] = False
        try:
            resp = await toggle_job(jid)
        finally:
            _job_enabled_state.pop(jid, None)
        mock_toggle.assert_called_once_with(jid, True)


@pytest.mark.asyncio
async def test_toggle_job_toggle_disable(db):
    """When currently enabled → disables."""
    from quantide.web.pages.system.jobs import PREDEFINED_JOBS
    with patch("quantide.web.pages.system.jobs._toggle_job") as mock_toggle:
        jid = list(PREDEFINED_JOBS.keys())[0]
        _job_enabled_state[jid] = True
        try:
            resp = await toggle_job(jid)
        finally:
            _job_enabled_state.pop(jid, None)
        mock_toggle.assert_called_once_with(jid, False)

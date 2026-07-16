"""B11-jobs: Coverage recovery tests for quantide/web/pages/system/jobs.py.

Targets 5 blocks of missing lines:
- _init_job_history_table create path (116, 128)
- _init_job_settings_table create path + _save_job_enabled_state (134, 142, 154, 155)
- _toggle_job resume/pause via scheduler (322-330)
- _run_job_now success path (335-347)
- _run_job_now error path (354-363)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system import jobs as jobs_mod


# ---------------------------------------------------------------------------
# _init_job_history_table create path (lines 116, 128)
# ---------------------------------------------------------------------------


def test_init_job_history_table_creates_when_missing():
    """[AC-NFR1101-01] When job_history table absent, _init_job_history_table creates it.

    Patches the module-level ``db`` so ``table_names()`` reports the table as
    missing; verifies ``db["job_history"].create(...)`` is invoked with pk="id".
    Covers the create branch (lines 116, 128) that the shared session-scoped
    db fixture would otherwise skip after first creation.
    """
    fake_db = MagicMock()
    fake_db.table_names.return_value = []
    fake_table = MagicMock()
    fake_db.__getitem__.return_value = fake_table
    with patch.object(jobs_mod, "db", fake_db):
        jobs_mod._init_job_history_table()
    fake_db.__getitem__.assert_called_with("job_history")
    fake_table.create.assert_called_once()
    assert fake_table.create.call_args.kwargs.get("pk") == "id"


# ---------------------------------------------------------------------------
# _init_job_settings_table create path + _save_job_enabled_state (134, 142, 154, 155)
# ---------------------------------------------------------------------------


def test_save_job_enabled_state_creates_table_and_upserts():
    """[AC-NFR1101-01] _save_job_enabled_state inits the settings table then upserts.

    With a mocked db whose ``table_names()`` reports no settings table, the call
    drives ``_init_job_settings_table`` to create it (lines 134, 142) and then
    performs the upsert (lines 154, 155) with enabled encoded as int.
    """
    fake_db = MagicMock()
    fake_db.table_names.return_value = []
    fake_table = MagicMock()
    fake_db.__getitem__.return_value = fake_table
    with patch.object(jobs_mod, "db", fake_db):
        jobs_mod._save_job_enabled_state("daily_bars_sync", True)
    # _init_job_settings_table create branch
    fake_db.__getitem__.assert_any_call(jobs_mod.JOB_SETTINGS_TABLE)
    fake_table.create.assert_called_once()
    assert fake_table.create.call_args.kwargs.get("pk") == "job_id"
    # upsert persisted enabled=True as 1
    fake_table.upsert.assert_called_once()
    upsert_row = fake_table.upsert.call_args.args[0]
    assert upsert_row["job_id"] == "daily_bars_sync"
    assert upsert_row["enabled"] == 1


# ---------------------------------------------------------------------------
# _toggle_job resume/pause (lines 322-330)
# ---------------------------------------------------------------------------


def test_toggle_job_resume_and_pause_through_scheduler():
    """[AC-NFR1101-01] _toggle_job resumes when enabling, pauses when disabling.

    With an existing scheduler job, enabling routes to ``resume_job`` (327-328)
    and disabling routes to ``pause_job`` (329-330); state is persisted (322-323)
    and the scheduler job is fetched (325-326).
    """
    try:
        with patch.object(jobs_mod, "scheduler") as mock_sched, \
                patch.object(jobs_mod, "_save_job_enabled_state") as mock_save:
            mock_sched.scheduler.get_job.return_value = MagicMock()

            jobs_mod._toggle_job("daily_bars_sync", True)
            mock_sched.scheduler.resume_job.assert_called_once_with("daily_bars_sync")
            mock_sched.scheduler.pause_job.assert_not_called()
            assert jobs_mod._job_enabled_state.get("daily_bars_sync") is True

            jobs_mod._toggle_job("daily_bars_sync", False)
            mock_sched.scheduler.pause_job.assert_called_once_with("daily_bars_sync")
            assert jobs_mod._job_enabled_state.get("daily_bars_sync") is False
        assert mock_save.call_count == 2
        mock_save.assert_any_call("daily_bars_sync", True)
        mock_save.assert_any_call("daily_bars_sync", False)
    finally:
        jobs_mod._job_enabled_state.pop("daily_bars_sync", None)


# ---------------------------------------------------------------------------
# _run_job_now success path (lines 335-347)
# ---------------------------------------------------------------------------


def test_run_job_now_success_path_records_success(db):
    """[AC-NFR1101-01] _run_job_now runs the sync function and records success.

    Replaces the job function with a sync MagicMock (so the ``else: func()`` path
    at line 345 is taken) and intercepts ``_save_job_history``; verifies a
    success record is written with the job_id and duration. Covers lines 335-347.
    """
    sync_func = MagicMock()
    with patch.dict(jobs_mod.JOB_FUNCTIONS, {"daily_bars_sync": sync_func}, clear=False), \
            patch.object(jobs_mod, "_save_job_history") as mock_save:
        jobs_mod._run_job_now("daily_bars_sync")
    sync_func.assert_called_once_with()
    mock_save.assert_called_once()
    saved = mock_save.call_args
    assert saved.args[0] == "daily_bars_sync"
    assert saved.args[2] == "success"
    assert saved.args[3] == "手动执行成功"
    assert isinstance(saved.args[4], int)


# ---------------------------------------------------------------------------
# _run_job_now error path (lines 354-363)
# ---------------------------------------------------------------------------


def test_run_job_now_error_path_records_error_and_reraises(db):
    """[AC-NFR1101-01] _run_job_now records an error record and re-raises.

    The job function raises RuntimeError; the except branch (354-356) records an
    error history entry with the exception message, then re-raises (363).
    """
    sync_func = MagicMock(side_effect=RuntimeError("boom"))
    with patch.dict(jobs_mod.JOB_FUNCTIONS, {"daily_bars_sync": sync_func}, clear=False), \
            patch.object(jobs_mod, "_save_job_history") as mock_save:
        with pytest.raises(RuntimeError, match="boom"):
            jobs_mod._run_job_now("daily_bars_sync")
    sync_func.assert_called_once_with()
    mock_save.assert_called_once()
    saved = mock_save.call_args
    assert saved.args[0] == "daily_bars_sync"
    assert saved.args[2] == "error"
    assert "boom" in saved.args[3]
    assert isinstance(saved.args[4], int)

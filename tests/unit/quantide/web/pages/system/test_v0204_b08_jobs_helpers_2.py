"""B08-jobs-helpers-2: Test _format_cron + _run_daily_snapshot + _run_market_snapshot."""

from __future__ import annotations

from unittest.mock import patch

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
    assert _format_cron("0 18 * * 1-5") == "每天 18:00 (周一至周五)"


def test_format_cron_every_day():
    assert _format_cron("30 9 * * *") == "每天 9:30"


def test_format_cron_monday():
    assert _format_cron("0 10 * * 1") == "每周一 10:00"


def test_format_cron_every_n_minutes():
    # "*/5 * * * *" - falls through to fallback; just exercise the path
    out = _format_cron("*/5 * * * *")
    assert isinstance(out, str) and out


def test_format_cron_unsupported_returns_raw():
    """Non-standard cron returns input unchanged."""
    raw = "0 0 * * * 2024"
    assert _format_cron(raw) == raw


def test_format_cron_too_short_returns_raw():
    assert _format_cron("a b c") == "a b c"


# ---------------------------------------------------------------------------
# _run_* task functions (sync flows)
# ---------------------------------------------------------------------------


def test_run_daily_bars_sync_success(db):
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_db:
        mock_db.store.update = lambda: None
        _run_daily_bars_sync()
    # No assertion; just exercise the path.


def test_run_daily_bars_sync_exception(db):
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_db:
        def _boom():
            raise RuntimeError("boom")
        mock_db.store.update = _boom
        _run_daily_bars_sync()


def test_run_stock_list_sync_success(db):
    with patch("quantide.data.models.stocks.stock_list") as mock:
        mock.update = lambda: None  # async, but asyncio.run wraps it
        # We make .update return a regular value to be safe with asyncio.run
        mock.update = lambda: __import__("asyncio").sleep(0)
        _run_stock_list_sync()


def test_run_stock_list_sync_exception(db):
    with patch("quantide.data.models.stocks.stock_list") as mock:
        def _boom():
            raise Exception("sync failed")
        mock.update = _boom
        _run_stock_list_sync()


def test_run_calendar_sync_success(db):
    with patch("quantide.data.models.calendar.calendar") as mock:
        mock.update = lambda: __import__("asyncio").sleep(0)
        _run_calendar_sync()


def test_run_calendar_sync_exception(db):
    with patch("quantide.data.models.calendar.calendar") as mock:
        def _boom():
            raise Exception("cal failed")
        mock.update = _boom
        _run_calendar_sync()


def test_run_daily_snapshot(db):
    _run_daily_snapshot()


def test_run_market_snapshot(db):
    _run_market_snapshot()

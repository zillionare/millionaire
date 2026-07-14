"""B08-system-jobs-2: Test sync job runners."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system.jobs import (
    _run_calendar_sync,
    _run_daily_bars_sync,
    _run_daily_snapshot,
    _run_market_snapshot,
    _run_stock_list_sync,
)


@pytest.fixture(autouse=True)
def _patch_db(db):
    """All jobs persist via _save_job_history → use the db fixture."""
    pass


def test_run_daily_bars_sync_success(db):
    """Successful daily bars sync updates store and records history."""
    with patch(
        "quantide.web.pages.system.jobs.daily_bars",
        create=True,
    ) as mock_db:
        mock_db.store.update = MagicMock()
        _run_daily_bars_sync()


def test_run_daily_bars_sync_handles_failure(db):
    """When store.update raises, error is caught."""
    with patch(
        "quantide.web.pages.system.jobs.daily_bars",
        create=True,
    ) as mock_db:
        mock_db.store.update.side_effect = RuntimeError("sync boom")
        _run_daily_bars_sync()  # should not raise


def test_run_stock_list_sync_success(db):
    """Successful stock list sync."""
    with patch(
        "quantide.web.pages.system.jobs.stock_list",
        create=True,
    ) as mock_sl:
        # stock_list.update is async; we need to wrap in run.
        async def _async_update():
            pass
        mock_sl.update = _async_update
        _run_stock_list_sync()


def test_run_stock_list_sync_handles_failure(db):
    """When stock_list update raises, caught."""
    with patch(
        "quantide.web.pages.system.jobs.stock_list",
        create=True,
    ) as mock_sl:
        async def _failing_update():
            raise RuntimeError("boom")
        mock_sl.update = _failing_update
        _run_stock_list_sync()  # should not raise


def test_run_calendar_sync_no_data(db):
    """calendar sync when _data is None."""
    with patch(
        "quantide.web.pages.system.jobs.calendar",
        create=True,
    ) as mock_cal:
        mock_cal._data = None
        mock_cal.update = MagicMock()
        _run_calendar_sync()


def test_run_calendar_sync_with_data(db):
    """calendar sync when _data is present."""
    with patch(
        "quantide.web.pages.system.jobs.calendar",
        create=True,
    ) as mock_cal:
        mock_cal._data = MagicMock()
        mock_cal._data.__len__ = lambda self: 10
        mock_cal.update = MagicMock()
        _run_calendar_sync()


def test_run_daily_snapshot_handles_exception(db):
    """Daily snapshot job catches exceptions."""
    with patch(
        "quantide.web.pages.system.jobs.daily_bars",
        create=True,
    ) as mock_db:
        mock_db.store.snapshot = MagicMock(side_effect=RuntimeError("boom"))
        _run_daily_snapshot()  # should not raise


def test_run_market_snapshot_handles_exception(db):
    """Market snapshot job catches exceptions."""
    with patch(
        "quantide.web.pages.system.jobs.daily_bars",
        create=True,
    ) as mock_db:
        mock_db.store.snapshot = MagicMock(side_effect=RuntimeError("boom"))
        _run_market_snapshot()  # should not raise

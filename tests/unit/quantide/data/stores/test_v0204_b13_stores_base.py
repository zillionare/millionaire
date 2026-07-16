"""B13 batch: cover missing branches in quantide.data.stores.base.

Targets specific missing lines reported by /tmp/gg.json:
  - fetch() _update_dates exception swallow (lines 367-368)
  - fetch() final msg_hub.publish exception swallow (lines 379-380)
  - fetch_with_daily_progress _phase_callback msg_hub exception (lines 437-438)
  - fetch_with_daily_progress error msg_hub exception (lines 467-468)
  - fetch_with_daily_progress progress msg_hub exception (lines 497-498)
  - fetch_with_daily_progress outer exception handler (lines 500-514)
  - fetch_with_daily_progress final msg_hub exception (lines 518-519)
  - _group_dates else/unknown-partition branch (line 754)
"""
from __future__ import annotations

import datetime
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import polars as pl
import pytest

from quantide.data.models.calendar import Calendar
from quantide.data.stores import base as base_module
from quantide.data.stores.base import ParquetStorage


@pytest.fixture
def calendar(asset_dir):
    cal = Calendar()
    cal.load(asset_dir / "baseline_calendar.parquet")
    return cal


@pytest.fixture
def tmp_store_path():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _stub_fetch(chunk, calls_log=None):
    if calls_log is not None:
        calls_log.append(list(chunk))
    df = pd.DataFrame(
        {
            "date": chunk,
            "asset": ["000001.SZ"] * len(chunk),
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 1000.0,
            "amount": 10000.0,
        }
    )
    return df, []


# --- _group_dates else branch ------------------------------------------------


def test_group_dates_uses_month_key_for_unknown_partition(calendar, tmp_store_path):
    """Line 754: unknown _partition_by value falls back to month grouping."""
    store = ParquetStorage(
        "unknown", tmp_store_path / "u.parquet", calendar
    )
    store._partition_by = "partition_key_quarter"
    dates = [
        datetime.date(2024, 1, 5),
        datetime.date(2024, 1, 10),
        datetime.date(2024, 2, 15),
    ]
    groups = store._group_dates(dates)
    assert len(groups) == 2
    assert groups[0] == [datetime.date(2024, 1, 5), datetime.date(2024, 1, 10)]
    assert groups[1] == [datetime.date(2024, 2, 15)]


# --- fetch() exception swallow paths ----------------------------------------


def test_fetch_swallows_update_dates_exception(calendar, tmp_store_path, monkeypatch):
    """Lines 367-368: _update_dates raising inside try block is swallowed.

    append_data also calls _update_dates (outside the try), so we raise only
    on the second invocation (the one inside the try/except at lines 364-368).
    """
    store_path = tmp_store_path / "exc.parquet"
    store = ParquetStorage(
        "exc", store_path, calendar, fetch_data_func=_stub_fetch
    )

    original = store._update_dates
    call_count = {"n": 0}

    def selective_raise(dates):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom")
        return original(dates)

    monkeypatch.setattr(store, "_update_dates", selective_raise)

    # Should not raise despite _update_dates failing inside the try block.
    store.fetch(datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True)
    assert call_count["n"] >= 2


def test_fetch_swallows_final_msg_hub_exception(calendar, tmp_store_path, monkeypatch):
    """Lines 379-380: final msg_hub.publish raising is caught and swallowed."""
    store_path = tmp_store_path / "msg.parquet"
    store = ParquetStorage(
        "msg", store_path, calendar, fetch_data_func=_stub_fetch
    )

    call_count = {"n": 0}

    def failing_publish(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 3:
            raise RuntimeError("msg_hub down")

    monkeypatch.setattr(base_module.msg_hub, "publish", failing_publish)

    # Should not raise despite msg_hub.publish failing on the final call.
    store.fetch(datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True)


def test_fetch_swallows_msg_hub_when_no_missing_dates(calendar, tmp_store_path, monkeypatch):
    """Lines 349-350 (no-missing msg_hub path) also swallow publish errors."""
    store_path = tmp_store_path / "none.parquet"
    store = ParquetStorage(
        "none", store_path, calendar, fetch_data_func=_stub_fetch
    )
    # Populate data first.
    store.fetch(datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True)

    monkeypatch.setattr(
        base_module.msg_hub, "publish", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("down"))
    )
    # Second fetch with no missing dates -> hits the "already up to date" branch.
    store.fetch(datetime.date(2024, 1, 2), datetime.date(2024, 1, 2))


# --- fetch_with_daily_progress exception paths ------------------------------


def test_daily_progress_swallows_phase_callback_msg_hub_exception(
    calendar, tmp_store_path, monkeypatch
):
    """Lines 437-438: msg_hub.publish in _phase_callback raises -> swallowed."""
    store_path = tmp_store_path / "phase.parquet"

    monkeypatch.setattr(
        base_module.msg_hub, "publish", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("down"))
    )

    def fetch_with_phase(chunk, phase_callback=None):
        if phase_callback:
            phase_callback("start")
        df = pd.DataFrame(
            {"date": chunk, "asset": ["A"] * len(chunk), "close": [10.0] * len(chunk)}
        )
        return df, []

    store = ParquetStorage(
        "phase", store_path, calendar, fetch_data_func=fetch_with_phase
    )
    n = store.fetch_with_daily_progress(
        datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True
    )
    assert n == 1


def test_daily_progress_swallows_error_msg_hub_exception(
    calendar, tmp_store_path, monkeypatch
):
    """Lines 467-468: msg_hub.publish on error-path raises -> swallowed."""
    store_path = tmp_store_path / "err.parquet"

    call_count = {"n": 0}

    def failing_publish(*args, **kwargs):
        call_count["n"] += 1
        raise RuntimeError("msg_hub down")

    monkeypatch.setattr(base_module.msg_hub, "publish", failing_publish)

    def fetch_returning_errors(chunk, **kwargs):
        return None, [["error_detail"]]

    store = ParquetStorage(
        "err", store_path, calendar, fetch_data_func=fetch_returning_errors
    )
    n = store.fetch_with_daily_progress(
        datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True
    )
    assert n == 0


def test_daily_progress_swallows_progress_msg_hub_exception(
    calendar, tmp_store_path, monkeypatch
):
    """Lines 497-498: msg_hub.publish on progress raises -> swallowed."""
    store_path = tmp_store_path / "prog.parquet"

    call_count = {"n": 0}

    def failing_publish(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise RuntimeError("msg_hub down")
        # First call (phase_callback) succeeds to get past phase.

    monkeypatch.setattr(base_module.msg_hub, "publish", failing_publish)

    store = ParquetStorage(
        "prog", store_path, calendar, fetch_data_func=_stub_fetch
    )
    n = store.fetch_with_daily_progress(
        datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True
    )
    assert n == 1


def test_daily_progress_handles_fetch_exception_per_date(
    calendar, tmp_store_path, monkeypatch
):
    """Lines 500-514: fetch_data_func raising -> outer except logs + publishes error."""
    store_path = tmp_store_path / "outer.parquet"

    monkeypatch.setattr(
        base_module.msg_hub,
        "publish",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("hub down")),
    )

    def raising_fetch(chunk, **kwargs):
        raise RuntimeError("fetch blew up")

    store = ParquetStorage(
        "outer", store_path, calendar, fetch_data_func=raising_fetch
    )
    n = store.fetch_with_daily_progress(
        datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True
    )
    assert n == 0


def test_daily_progress_swallows_final_msg_hub_exception(
    calendar, tmp_store_path, monkeypatch
):
    """Lines 518-519: final msg_hub.publish raising -> swallowed."""
    store_path = tmp_store_path / "final.parquet"

    call_count = {"n": 0}

    def failing_publish(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise RuntimeError("hub down")

    monkeypatch.setattr(base_module.msg_hub, "publish", failing_publish)

    store = ParquetStorage(
        "final", store_path, calendar, fetch_data_func=_stub_fetch
    )
    n = store.fetch_with_daily_progress(
        datetime.date(2024, 1, 2), datetime.date(2024, 1, 2), force=True
    )
    assert n == 1

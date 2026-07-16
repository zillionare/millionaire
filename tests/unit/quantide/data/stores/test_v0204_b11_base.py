"""B11-stores-base: remaining gaps in quantide/data/stores/base.py.

Targets uncovered branches not addressed by B04/B09 test files:
- ``__len__`` returns 0 via line 115 when ``_scan_store`` returns ``None``
- ``_save_single`` falls back to ``[lf]`` only (line 298) when the path
  exists but ``_scan_store`` returns ``None``
- ``fetch`` swallows ``msg_hub.publish`` exceptions on the no-missing-dates
  early-return path (lines 349-350)
- ``fetch_with_daily_progress`` invokes the inner ``_phase_callback`` and
  the 4-arg ``progress_callback`` signature (lines 426, 432-433, 439-441, 450)
- ``fetch_with_daily_progress`` falls back to the 3-arg ``progress_callback``
  signature inside ``_phase_callback`` when the 4-arg call raises ``TypeError``
  (lines 442-443)
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
from quantide.data.stores.base import ParquetStorage, msg_hub


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


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


def _bars_for_chunk(chunk: list[datetime.date]) -> pd.DataFrame:
    """One-row-per-date bars DataFrame with ``datetime64[ms]`` date column."""
    df = pd.DataFrame({
        "date": pd.to_datetime(chunk).astype("datetime64[ms]"),
        "asset": ["000001.SZ"] * len(chunk),
        "close": [10.0] * len(chunk),
    })
    return df


# ---------------------------------------------------------------------------
# __len__ returns 0 via line 115 when _scan_store returns None (no file)
# ---------------------------------------------------------------------------


def test_len_returns_zero_when_scan_store_returns_none(tmp_store_path, calendar):
    """[AC-FR0700-B11] __len__ returns 0 via line 115 when store file does not exist."""
    store_file = tmp_store_path / "missing.parquet"
    store = ParquetStorage("missing", store_file, calendar)
    assert not store_file.exists()
    # _scan_store returns None because the file does not exist; hits line 115.
    assert len(store) == 0


# ---------------------------------------------------------------------------
# _save_single: line 298 (path exists but _scan_store returns None)
# ---------------------------------------------------------------------------


def test_save_single_uses_lf_only_when_existing_scan_returns_none(
    tmp_store_path, calendar
):
    """[AC-FR0700-B11] _save_single builds group=[lf] when path exists but scan returns None."""
    store_file = tmp_store_path / "exists.parquet"
    store = ParquetStorage("exists", store_file, calendar)
    # Create an empty placeholder file so store_path.exists() is True while
    # _scan_store is forced to return None (simulating a corrupt/empty file).
    store_file.touch()
    store._scan_store = MagicMock(return_value=None)

    lf = pl.DataFrame({
        "date": [datetime.datetime(2024, 1, 2)],
        "asset": ["000001.SZ"],
        "close": [10.0],
    }).lazy()
    # Should not raise; should overwrite the placeholder with a valid parquet.
    store._save_single(lf)

    df = pl.read_parquet(store_file)
    assert len(df) == 1
    assert df["asset"].to_list() == ["000001.SZ"]


# ---------------------------------------------------------------------------
# fetch: lines 349-350 (msg_hub.publish raises on no-missing-dates branch)
# ---------------------------------------------------------------------------


def test_fetch_swallows_msg_hub_publish_exception_when_no_missing_dates(
    tmp_store_path, calendar, monkeypatch
):
    """[AC-FR0700-B11] fetch() swallows msg_hub.publish exception on no-missing-dates branch."""
    store_file = tmp_store_path / "fresh.parquet"
    # No fetch_data_func: if missing_dates were non-empty, fetch would raise
    # ValueError. A clean return proves the no-missing-dates branch was taken.
    store = ParquetStorage("fresh", store_file, calendar)
    store._dates = pl.Series([datetime.date(2024, 1, 2)], dtype=pl.Date)

    # Force msg_hub.publish to raise so the except branch (lines 349-350) runs.
    monkeypatch.setattr(
        msg_hub, "publish", MagicMock(side_effect=RuntimeError("hub down"))
    )

    # Should not raise; exception is swallowed by the try/except.
    store.fetch(
        datetime.date(2024, 1, 2),
        datetime.date(2024, 1, 2),
        use_calendar=True,
    )


# ---------------------------------------------------------------------------
# fetch_with_daily_progress: lines 426, 432-433, 439-441, 450
# (phase_callback + 4-arg progress_callback happy path)
# ---------------------------------------------------------------------------


def test_fetch_with_daily_progress_invokes_phase_callback_with_4arg_progress(
    tmp_store_path, calendar
):
    """[AC-FR0700-B11] phase_callback is invoked and 4-arg progress_callback receives phase."""
    store_file = tmp_store_path / "phase.parquet"
    progress_calls: list[tuple] = []

    def fetch_func(chunk, phase_callback=None):
        if phase_callback is not None:
            phase_callback("start")
        return _bars_for_chunk(list(chunk)), []

    def progress_callback(date, i, total, phase):
        progress_calls.append((date, i, total, phase))

    store = ParquetStorage("phase", store_file, calendar, fetch_data_func=fetch_func)
    completed = store.fetch_with_daily_progress(
        datetime.date(2024, 1, 2),
        datetime.date(2024, 1, 2),
        progress_callback=progress_callback,
        force=True,
    )

    assert completed == 1
    phases = [pc[3] for pc in progress_calls]
    # _phase_callback path: progress_callback called with phase="start"
    assert "start" in phases
    # outer path: progress_callback called with phase="done"
    assert "done" in phases


# ---------------------------------------------------------------------------
# fetch_with_daily_progress: lines 442-443
# (TypeError fallback to 3-arg progress_callback inside _phase_callback)
# ---------------------------------------------------------------------------


def test_fetch_with_daily_progress_falls_back_to_3arg_on_typeerror(
    tmp_store_path, calendar
):
    """[AC-FR0700-B11] _phase_callback catches TypeError and calls 3-arg progress_callback."""
    store_file = tmp_store_path / "3arg_fallback.parquet"
    progress_3arg: list[tuple] = []

    def fetch_func(chunk, phase_callback=None):
        if phase_callback is not None:
            phase_callback("start")
        return _bars_for_chunk(list(chunk)), []

    def progress_callback_3arg(date, i, total):  # noqa: ANN001 - test stub
        progress_3arg.append((date, i, total))

    store = ParquetStorage(
        "3arg", store_file, calendar, fetch_data_func=fetch_func
    )
    completed = store.fetch_with_daily_progress(
        datetime.date(2024, 1, 2),
        datetime.date(2024, 1, 2),
        progress_callback=progress_callback_3arg,
        force=True,
    )

    assert completed == 1
    # The 3-arg fallback inside _phase_callback must have been invoked at
    # least once (for phase="start").
    assert len(progress_3arg) >= 1

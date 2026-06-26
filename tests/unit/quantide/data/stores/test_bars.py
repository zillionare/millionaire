import datetime

import pytest

from quantide.data.models.daily_bars import DailyBars


@pytest.fixture
def store(asset_dir, tmp_path):
    """Create a DailyBars instance connected to test fixtures."""
    data = asset_dir / "2024_bars_ext_cols.parquet"
    calendar_path = asset_dir / "baseline_calendar.parquet"

    bars = DailyBars()
    bars.connect(data, calendar_path)
    return bars


def test_rec_counts_per_date(store):
    result = store.rec_counts_per_date()

    dt = datetime.date(2024, 3, 26)
    actual = result.get(dt)
    assert actual is not None
    assert actual > 0

    assert len(result) == 242

    start = datetime.date(2024, 3, 26)
    end = datetime.date(2024, 3, 27)
    result = store.rec_counts_per_date(start, end)

    assert len(result) == 2


def test_daily_bars_has_fetch_bars_ext(store):
    """DailyBars should have _fetch_bars_ext method (migrated from DailyBarsStore)."""
    assert hasattr(store, "_fetch_bars_ext")


def test_daily_bars_store_returns_self(store):
    """.store property should return self for backward compat."""
    assert store.store is store


def test_daily_bars_no_getattr_recursion(store):
    """ParquetStorage properties should be accessible without __getattr__ recursion."""
    # These were previously delegated via __getattr__ to self.store
    # After merge, they come from ParquetStorage directly
    assert store.start is None or isinstance(store.start, datetime.date)
    assert store.end is None or isinstance(store.end, datetime.date)
    assert isinstance(store.total_dates, int)
    assert isinstance(store.size, int)

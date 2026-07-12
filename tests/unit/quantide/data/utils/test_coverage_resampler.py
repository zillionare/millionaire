"""FR-0304 AC-3/4: weekly/monthly OHLCV aggregation and moving averages."""

import datetime as dt

import polars as pl
import pytest

from quantide.data.utils.resampler import Resampler


def _daily_bars() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "dt": [dt.date(2024, 1, 29), dt.date(2024, 1, 31), dt.date(2024, 2, 1)],
            "open": [10.0, 11.0, 20.0],
            "high": [12.0, 15.0, 22.0],
            "low": [9.0, 10.0, 18.0],
            "close": [11.0, 14.0, 21.0],
            "volume": [100.0, 200.0, 300.0],
            "amount": [1000.0, 2000.0, 3000.0],
            "adjust": [1.0, 1.5, 2.0],
        }
    )


def test_monthly_resample_uses_first_last_extrema_sums_and_last_adjust():
    """FR-0304 AC-3: monthly aggregation follows the OHLCV and adjustment contract."""
    january = Resampler.daily_to_monthly(_daily_bars()).filter(pl.col("dt") == dt.date(2024, 1, 1)).row(0, named=True)

    assert january == {"dt": dt.date(2024, 1, 1), "open": 10.0, "high": 15.0, "low": 9.0, "close": 14.0, "volume": 300.0, "amount": 3000.0, "adjust": 1.5}


def test_resampler_handles_empty_unknown_frequency_and_rolling_means():
    """FR-0304 AC-3/4: empty data, invalid frequency and MA columns are deterministic."""
    assert Resampler.daily_to_weekly(pl.DataFrame()).is_empty()
    with pytest.raises(ValueError, match="不支持"):
        Resampler.resample(_daily_bars(), "quarter")

    result = Resampler.calculate_ma(pl.DataFrame({"close": [1.0, 2.0, 3.0]}), [2])

    assert result["ma2"].to_list() == [None, 1.5, 2.5]

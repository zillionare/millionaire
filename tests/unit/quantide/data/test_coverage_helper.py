"""FR-0304 AC-1/2: adjustment formulas and time-series split contracts."""

import datetime as dt

import pandas as pd
import polars as pl

from quantide.data.helper import hfq_adjustment, qfq_adjustment, train_test_split


def _adjustment_fixture() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "asset": ["A", "A"],
            "date": [dt.date(2024, 1, 1), dt.date(2024, 1, 2)],
            "open": [10.0, 10.0],
            "high": [12.0, 12.0],
            "low": [8.0, 8.0],
            "close": [11.0, 11.0],
            "volume": [100.0, 100.0],
            "adjust": [1.0, 2.0],
        }
    )


def test_qfq_and_hfq_match_independent_adjustment_formulae():
    """FR-0304 AC-1: qfq uses latest factor; hfq uses first factor."""
    qfq = qfq_adjustment(_adjustment_fixture())
    hfq = hfq_adjustment(_adjustment_fixture())

    assert qfq["close"].to_list() == [5.5, 11.0]
    assert qfq["volume"].to_list() == [200.0, 100.0]
    assert hfq["close"].to_list() == [11.0, 22.0]
    assert hfq["volume"].to_list() == [100.0, 100.0]


def test_train_test_split_preserves_input_type_and_group_time_order():
    """FR-0304 AC-2: grouped splits retain type, every row, and chronological order."""
    frame = pd.DataFrame(
        {
            "asset": ["A"] * 5 + ["B"] * 5,
            "date": list(pd.date_range("2024-01-01", periods=5)) * 2,
            "value": list(range(10)),
        }
    )

    train, valid, test = train_test_split(frame, cuts=(0.6, 0.2))

    assert all(isinstance(part, pd.DataFrame) for part in (train, valid, test))
    assert len(train) + len(valid) + len(test) == len(frame)
    assert train.groupby("asset")["date"].max().le(valid.groupby("asset")["date"].min()).all()
    assert valid.groupby("asset")["date"].max().le(test.groupby("asset")["date"].min()).all()


def test_train_test_split_keeps_lazyframe_lazy():
    """FR-0304 AC-2: lazy input yields three lazy, non-overlapping result frames."""
    source = pl.DataFrame({"date": [dt.date(2024, 1, 1), dt.date(2024, 1, 2), dt.date(2024, 1, 3)], "value": [1, 2, 3]}).lazy()

    train, valid, test = train_test_split(source, group_id=None, cuts=(0.34, 0.33))

    assert all(isinstance(part, pl.LazyFrame) for part in (train, valid, test))
    assert sum(part.collect().height for part in (train, valid, test)) == 3

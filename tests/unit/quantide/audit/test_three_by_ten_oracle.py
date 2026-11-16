"""Independent 3x10 oracle for labels, Rank IC and T+1 account facts."""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import polars as pl
import pytest

from quantide.audit.account import AccountLedger
from quantide.factors.research import HorizonRequest, daily_rank_ic, study_horizon


def _fixture() -> pl.DataFrame:
    path = Path(__file__).resolve().parents[3] / "assets" / "audit" / "three_by_ten.csv"
    frame = pl.read_csv(
        path, try_parse_dates=True, schema_overrides={"asset": pl.Utf8}
    ).with_columns((pl.col("close") / pl.col("open") - 1).alias("intraday"))
    return frame.sort(["asset", "date"])


def _average_rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        rank = (position + end) / 2 + 1
        for item in order[position : end + 1]:
            ranks[item] = rank
        position = end + 1
    return ranks


def _correlation(left: list[float], right: list[float]) -> float:
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((a - mean_left) ** 2 for a in left) * sum((b - mean_right) ** 2 for b in right)
    )
    return numerator / denominator


def test_labels_and_rank_ic_match_manual_table() -> None:
    frame = _fixture()
    dates = sorted(frame["date"].unique().to_list())
    manual_ic: dict[dt.date, float] = {}
    manual_forward: dict[tuple[dt.date, str], float] = {}
    for index in range(len(dates) - 2):
        day = dates[index]
        entry_day = dates[index + 1]
        exit_day = dates[index + 2]
        factors = []
        forwards = []
        for asset in ("000001", "000002", "000003"):
            factor = frame.filter((pl.col("date") == day) & (pl.col("asset") == asset))[
                "intraday"
            ].item()
            entry = frame.filter((pl.col("date") == entry_day) & (pl.col("asset") == asset))[
                "open"
            ].item()
            exit_price = frame.filter((pl.col("date") == exit_day) & (pl.col("asset") == asset))[
                "open"
            ].item()
            forward = exit_price / entry - 1
            manual_forward[(day, asset)] = forward
            factors.append(float(factor))
            forwards.append(float(forward))
        manual_ic[day] = _correlation(_average_rank(factors), _average_rank(forwards))

    pairs = pl.DataFrame(
        [
            {
                "date": day,
                "intraday": frame.filter((pl.col("date") == day) & (pl.col("asset") == asset))[
                    "intraday"
                ].item(),
                "forward": manual_forward[(day, asset)],
            }
            for day in dates[:-2]
            for asset in ("000001", "000002", "000003")
        ]
    )
    points = daily_rank_ic(pairs, "intraday", 3)
    assert [point.date for point in points] == dates[:-2]
    assert [point.ic for point in points] == pytest.approx(list(manual_ic.values()))

    result = study_horizon(
        frame,
        HorizonRequest(
            "intraday",
            1,
            dates[0],
            dates[-1],
            dates[-1],
            min_cross_section=3,
        ),
    )
    assert result.diagnostics.as_of_date == dates[-3]
    assert result.diagnostics.n_valid_pairs == 24
    assert [point.ic for point in result.daily_ic] == pytest.approx(list(manual_ic.values()))


def test_t_plus_one_and_fees_match_manual_account() -> None:
    ledger = AccountLedger(10_000)
    buy_day = dt.date(2024, 1, 3)
    settle_day = dt.date(2024, 1, 4)
    ledger.buy("000001", 100, 10.1, buy_day, settle_day, fee=5)
    with pytest.raises(ValueError):
        ledger.sell("000001", 100, 10.3, fee=5)
    ledger.settle(settle_day)
    ledger.sell("000001", 100, 10.3, fee=5)
    snapshot = ledger.snapshot(settle_day)
    assert snapshot["cash"] == pytest.approx(10_010)
    assert snapshot["equity"] == pytest.approx(10_010)
    assert snapshot["nav"] == pytest.approx(1.001)
    assert snapshot["realized_pnl"] == pytest.approx(20)
    assert snapshot["fees_paid"] == pytest.approx(10)
    assert ledger.validate() == []

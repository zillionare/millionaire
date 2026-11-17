"""Complete 3 x 10 ML training targets against a rational independent oracle."""

from __future__ import annotations

import datetime as dt
from fractions import Fraction
from types import SimpleNamespace

import polars as pl
import pytest

_DAYS = tuple(dt.date(2024, 1, 2) + dt.timedelta(days=i) for i in range(10))
_PRICES = {
    "A": (10, 11, 12, 13, 14, 15, 16, 17, 18, 19),
    "B": (20, 19, 18, 17, 16, 15, 14, 13, 12, 11),
    "C": (5, 5, 5, 6, 6, 6, 7, 7, 7, 8),
}
_INELIGIBLE = {("A", 2), ("B", 4), ("C", 1)}
# These are frozen raw-return fractions, independent of any production helper.
_RAW_ORACLE = {
    1: {
        "A": tuple(Fraction(1, n) for n in (10, 11, 12, 13, 14, 15, 16, 17, 18)),
        "B": tuple(Fraction(-1, n) for n in (20, 19, 18, 17, 16, 15, 14, 13, 12)),
        "C": (0, 0, Fraction(1, 5), 0, 0, Fraction(1, 6), 0, 0, Fraction(1, 7)),
    },
    3: {
        "A": tuple(Fraction(3, n) for n in (10, 11, 12, 13, 14, 15, 16)),
        "B": tuple(Fraction(-3, n) for n in (20, 19, 18, 17, 16, 15, 14)),
        "C": (Fraction(1, 5),) * 3 + (Fraction(1, 6),) * 3 + (Fraction(1, 7),),
    },
}


def _oracle(horizon, kind):
    expected = {}
    for index, day in enumerate(_DAYS[:-horizon]):
        values = {
            asset: Fraction(_RAW_ORACLE[horizon][asset][index])
            for asset in _PRICES
            if (asset, index) not in _INELIGIBLE
        }
        mean = sum(values.values()) / len(values)
        for asset, value in values.items():
            if kind == "excess_mean":
                value -= mean
            elif kind == "cs_rank":
                less = sum(peer < value for peer in values.values())
                equal = sum(peer == value for peer in values.values())
                rank = less + Fraction(equal + 1, 2)
                value = rank / len(values) - Fraction(1, 2)
            expected[day, asset] = float(value)
    return expected


@pytest.mark.parametrize("horizon", [1, 3])
@pytest.mark.parametrize("kind", ["raw_return", "excess_mean", "cs_rank"])
def test_every_mature_training_label_matches_rational_3_by_10_oracle(monkeypatch, horizon, kind):
    from quantide.strategies.example import _ml_support

    monkeypatch.setattr(
        _ml_support,
        "calendar",
        SimpleNamespace(
            day_frames=_DAYS,
            get_trade_dates=lambda start, end: [day for day in _DAYS if start <= day <= end],
        ),
    )
    frame = pl.DataFrame(
        [
            {
                "date": day,
                "asset": asset,
                "close": float(prices[index]),
                "ma20_slope_z": 0.0,
                "_eligible": (asset, index) not in _INELIGIBLE,
            }
            for asset, prices in _PRICES.items()
            for index, day in enumerate(_DAYS)
        ]
    )
    _, training = _ml_support._training_feature_panel(
        ["ma20_slope"], None, frame, horizon, 45, kind
    )
    observed = {
        (row["date"], row["asset"]): row["label_y"] for row in training.iter_rows(named=True)
    }
    expected = _oracle(horizon, kind)
    assert observed.keys() == expected.keys()
    for key, value in expected.items():
        assert observed[key] == pytest.approx(value, rel=0, abs=1e-12), key


def test_training_cs_rank_uses_real_ties_and_average_ranks(monkeypatch):
    from quantide.strategies.example import _ml_support

    days = _DAYS[:2]
    monkeypatch.setattr(
        _ml_support,
        "calendar",
        SimpleNamespace(day_frames=days, get_trade_dates=lambda start, end: list(days)),
    )
    # A and B both return exactly 10%; C returns -10%.
    frame = pl.DataFrame(
        [
            {"date": day, "asset": asset, "close": price, "ma20_slope_z": 0.0}
            for asset, prices in {"A": (10.0, 11.0), "B": (20.0, 22.0), "C": (30.0, 27.0)}.items()
            for day, price in zip(days, prices, strict=True)
        ]
    )
    _, training = _ml_support._training_feature_panel(["ma20_slope"], None, frame, 1, 45, "cs_rank")
    observed = {row["asset"]: row["label_y"] for row in training.iter_rows(named=True)}
    assert observed == pytest.approx({"A": 1 / 3, "B": 1 / 3, "C": -1 / 6}, rel=0, abs=1e-12)

import datetime as dt
import json

import polars as pl
import pytest

from quantide.factors.research import (
    HorizonRequest,
    common_cohort,
    daily_rank_ic,
    decile_profile,
    study_horizon,
    study_panel,
    summarize_ic,
)


def test_maturity_cutoff_and_availability():
    dates = [dt.date(2024, 1, i) for i in range(1, 6)]
    panel = pl.DataFrame(
        {
            "date": dates,
            "asset": ["a"] * 5,
            "f": [1.0] * 5,
            "open": [999.0, 10.0, 12.0, 15.0, 20.0],
            "close": [999.0, 20.0, 30.0, 40.0, 50.0],
            "available_at": [dates[0], dates[1], dates[3], dates[3], dates[4]],
        }
    )
    early = study_horizon(
        panel,
        HorizonRequest("f", 1, dates[0], dates[0], dates[1], min_cross_section=2),
    )
    late = study_horizon(
        panel,
        HorizonRequest("f", 1, dates[0], dates[0], dates[2], min_cross_section=2),
    )
    ready = study_horizon(
        panel,
        HorizonRequest("f", 1, dates[0], dates[0], dates[3], price="close", min_cross_section=2),
    )
    assert early.diagnostics.as_of_date is None
    assert late.diagnostics.as_of_date is None
    assert late.diagnostics.exclusion_counts["unavailable_price"] == 1
    assert ready.diagnostics.n_valid_pairs == 1
    assert ready.diagnostics.as_of_date == dates[0]
    assert ready.diagnostics.latest_valid_signal_date is None
    assert ready.diagnostics.min_cross_section == 2
    json.dumps(ready.as_dict(), allow_nan=False)


def test_factor_available_after_entry_is_excluded():
    dates = [dt.date(2024, 1, i) for i in range(1, 6)]
    panel = pl.DataFrame(
        {
            "date": dates,
            "asset": ["a"] * 5,
            "f": [1.0] * 5,
            "open": [10.0, 11.0, 12.0, 13.0, 14.0],
            "available_at": [dates[2], dates[1], dates[2], dates[3], dates[4]],
        }
    )
    result = study_horizon(
        panel,
        HorizonRequest("f", 1, dates[0], dates[0], dates[4], min_cross_section=2),
    )
    assert result.diagnostics.n_valid_pairs == 0
    assert result.diagnostics.exclusion_counts["late_factor"] == 1


def test_entry_time_controls_same_day_availability():
    d0, d1, d2 = (dt.date(2024, 1, 2) + dt.timedelta(days=index) for index in range(3))
    rows = []
    for asset in ("a", "b", "c"):
        for day, price in ((d0, 10.0), (d1, 11.0), (d2, 12.0)):
            rows.append(
                {
                    "date": day,
                    "asset": asset,
                    "f": 1.0,
                    "open": price,
                    "close": price * 1.01,
                    "available_at": dt.datetime.combine(d1, dt.time(14, 0)),
                }
            )
    panel = pl.DataFrame(rows)
    late_open = study_horizon(
        panel,
        HorizonRequest("f", 1, d0, d0, d2, price="open", min_cross_section=2),
    )
    available_close = study_horizon(
        panel,
        HorizonRequest("f", 1, d0, d0, d2, price="close", min_cross_section=2),
    )
    assert late_open.diagnostics.n_valid_pairs == 0
    assert late_open.diagnostics.exclusion_counts["late_factor"] == 3
    assert available_close.diagnostics.n_valid_pairs == 3

    date_rows = []
    for asset in ("a", "b", "c"):
        for day, price in ((d0, 10.0), (d1, 11.0), (d2, 12.0)):
            date_rows.append(
                {
                    "date": day,
                    "asset": asset,
                    "f": 1.0,
                    "open": price,
                    "available_at": d1 if day == d0 else day,
                }
            )
    date_only = study_horizon(
        pl.DataFrame(date_rows),
        HorizonRequest("f", 1, d0, d0, d2, price="open", min_cross_section=2),
    )
    assert date_only.diagnostics.exclusion_counts["late_factor"] == 3


def test_timezone_aware_availability_uses_exchange_time():
    d0 = dt.date(2024, 1, 2)
    d1 = dt.date(2024, 1, 3)
    d2 = dt.date(2024, 1, 4)
    early = dt.datetime(2024, 1, 3, 1, 0, tzinfo=dt.UTC)
    late = dt.datetime(2024, 1, 3, 2, 0, tzinfo=dt.UTC)
    rows = []
    for asset in ("a", "b", "c"):
        for day, price in ((d0, 10.0), (d1, 11.0), (d2, 12.0)):
            available = early if asset == "a" else late
            rows.append(
                {
                    "date": day,
                    "asset": asset,
                    "f": 1.0,
                    "open": price,
                    "available_at": available,
                }
            )
    result = study_horizon(
        pl.DataFrame(rows),
        HorizonRequest("f", 1, d0, d0, d2, price="open", min_cross_section=2),
    )
    assert result.diagnostics.n_valid_pairs == 1
    assert result.diagnostics.exclusion_counts["late_factor"] == 2


def test_authoritative_calendar_blocks_compressed_holding_window():
    d0, d1, d2, d3, d4 = (dt.date(2024, 1, i) for i in range(1, 6))
    rows = [
        {"date": day, "asset": asset, "f": 1.0, "open": 10.0 + index}
        for index, day in enumerate([d0, d1, d3, d4])
        for asset in ("a", "b", "c")
    ]
    panel = pl.DataFrame(rows)
    without = study_horizon(
        panel,
        HorizonRequest("f", 1, d0, d0, d4, min_cross_section=2),
    )
    with_calendar = study_horizon(
        panel,
        HorizonRequest(
            "f",
            1,
            d0,
            d0,
            d4,
            min_cross_section=2,
            calendar=(d0, d1, d2, d3, d4),
        ),
    )
    assert without.diagnostics.n_valid_pairs == 3
    assert with_calendar.diagnostics.n_valid_pairs == 0
    assert with_calendar.diagnostics.exclusion_counts["missing_price_or_calendar"] == 3


def test_ic_ties_and_t_status():
    d = dt.date(2024, 1, 1)
    frame = pl.DataFrame(
        {"date": [d] * 4, "f": [0.0, 0.0, 1.0, 1.0], "forward": [1.0, 2.0, 3.0, 4.0]}
    )
    point = daily_rank_ic(frame, "f", 2)[0]
    assert point.date == d
    assert point.ic == pytest.approx(2 / (5**0.5))
    assert summarize_ic([1.0]).t_status == "insufficient_days"
    assert summarize_ic([1.0, 1.0]).t_status == "zero_variance"
    assert summarize_ic([1.0, 1.0]).t_naive is None


def test_equal_day_and_common_endpoints():
    d1, d2, d3 = (dt.date(2024, 1, i) for i in range(1, 4))
    frame = pl.DataFrame(
        {
            "date": [d1] * 10 + [d2] * 20 + [d3] * 10,
            "f": list(range(10)) + list(range(20)) + [0] * 10,
            "forward": [0.0] * 10 + [10.0] * 20 + [100.0] * 10,
        }
    )
    profile = decile_profile(frame, "f", 2)
    assert profile.buckets[0].mean_forward == 5
    assert profile.buckets[0].n_samples == 3
    assert profile.n_common_days == 2
    assert profile.d1_mean_common == 5
    assert profile.d1_minus_d10 == 0
    assert profile.buckets[4].n_days == 3


def test_as_of_survives_missing_factor_values_but_not_missing_prices():
    dates = [dt.date(2024, 1, i) for i in range(1, 5)]
    panel = pl.DataFrame(
        {
            "date": dates,
            "asset": ["a"] * 4,
            "f": [None, 1.0, 2.0, 3.0],
            "open": [10.0, 11.0, 12.0, 13.0],
        }
    )
    result = study_horizon(
        panel,
        HorizonRequest("f", 1, dates[0], dates[0], dates[2], min_cross_section=2),
    )
    assert result.diagnostics.as_of_date == dates[0]
    assert result.diagnostics.latest_valid_signal_date is None


def test_common_cohort_nonempty():
    dates = [dt.date(2024, 1, i) for i in range(1, 9)]
    rows = []
    for asset in range(120):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "f": float(asset + index),
                    "open": 10.0 + asset * 0.1 + index * 0.05,
                }
            )
    panel = pl.DataFrame(rows)
    results = [
        study_horizon(
            panel,
            HorizonRequest("f", h, dates[0], dates[-1], dates[-1]),
        )
        for h in (1, 2)
    ]
    cohort = common_cohort(results)
    assert cohort.n_days > 0
    assert cohort.status == "ok"
    assert set(cohort.per_horizon) == {1, 2}


def test_common_cohort_empty():
    dates = [dt.date(2024, 1, i) for i in range(1, 5)]
    panel = pl.DataFrame({"date": dates, "asset": ["a"] * 4, "f": [1.0] * 4, "open": [1.0] * 4})
    results = [
        study_horizon(
            panel,
            HorizonRequest("f", h, dates[0], dates[-1], dates[-1], min_cross_section=2),
        )
        for h in (1, 2)
    ]
    cohort = common_cohort(results)
    assert cohort.dates == []
    assert cohort.status == "insufficient_common_sample"


def test_pearson_and_icir_summaries_are_separate_and_defined():
    dates = [dt.date(2024, 1, day) for day in range(1, 6)]
    rows = []
    for asset in range(6):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "f": float(asset),
                    "forward": float(asset) ** 2 if asset < 5 else 100.0,
                    "open": 10.0 + index + asset * 0.1,
                }
            )
    panel = pl.DataFrame(rows)
    result = study_horizon(
        panel,
        HorizonRequest("f", 1, dates[0], dates[-2], dates[-1], min_cross_section=2),
    )
    assert result.rank_ic.mean != result.pearson_ic.mean
    assert result.pearson_ic.n_days == result.rank_ic.n_days
    summary = summarize_ic([0.1, 0.2, 0.3])
    assert summary.std is not None and summary.std > 0
    assert summary.icir == pytest.approx(0.2 / summary.std)
    assert summary.annualized_icir == pytest.approx(summary.icir * (252**0.5))


def test_explicit_bar_interval_uses_holding_bars_without_day_conversion():
    start = dt.datetime(2024, 1, 2, 10, 0)
    bars = [start + dt.timedelta(minutes=30 * index) for index in range(8)]
    rows = []
    for asset in range(4):
        for index, moment in enumerate(bars):
            rows.append(
                {
                    "date": moment,
                    "asset": f"{asset:06d}",
                    "f": float(asset),
                    "open": 10.0 + index + asset * 0.1,
                    "available_at": moment - dt.timedelta(minutes=30),
                }
            )
    panel = pl.DataFrame(rows)
    result = study_horizon(
        panel,
        HorizonRequest(
            "f",
            1,
            bars[0],
            bars[2],
            bars[-1],
            interval="30m",
            holding_bars=2,
            min_cross_section=2,
            calendar=tuple(bars),
        ),
    )
    assert result.interval == "30m"
    assert result.holding_bars == 2
    assert result.diagnostics.n_valid_days == 3
    with pytest.raises(ValueError):
        HorizonRequest("f", 1, bars[0], bars[1], bars[-1], interval="30m").effective_holding


def test_batch_study_keeps_each_factor_sample_independent():
    dates = [dt.date(2024, 1, day) for day in range(1, 6)]
    rows = []
    for asset in range(6):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "good": float(asset),
                    "partial": None if asset == 0 else float(asset),
                    "open": 10.0 + index + asset * 0.1,
                }
            )
    panel = pl.DataFrame(rows)
    request = HorizonRequest("good", 1, dates[0], dates[0], dates[-1], min_cross_section=2)
    results = study_panel(panel, ["good", "partial", "missing"], request)
    assert set(results) == {"good", "partial"}
    assert results["good"].diagnostics.n_valid_pairs == 6
    assert results["partial"].diagnostics.n_valid_pairs == 5
    assert results["good"].rank_ic.mean is not None


def test_study_panel_missing_factor_does_not_change_good_factor():
    dates = [dt.date(2024, 1, day) for day in range(1, 5)]
    rows = []
    for asset in range(4):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "good": float(asset),
                    "open": 10.0 + index,
                }
            )
    panel = pl.DataFrame(rows)
    request = HorizonRequest("good", 1, dates[0], dates[0], dates[-1], min_cross_section=2)
    alone = study_panel(panel, ["good"], request)["good"]
    together = study_panel(panel, ["good", "missing"], request)["good"]
    assert alone.as_dict() == together.as_dict()

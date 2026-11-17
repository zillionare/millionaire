"""Independent hand-calculated oracles for WP-3 PIT filtering and labels."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.factors.universe import UniverseFilterConfig, filter_universe_for_date
from quantide.strategies.example._ml_support import compute_future_close_return_labels


class _Calendar:
    def __init__(self, start: dt.date, end: dt.date) -> None:
        days = []
        day = start
        while day <= end:
            if day.weekday() < 5:
                days.append(day)
            day += dt.timedelta(days=1)
        self.days = days

    def get_trade_dates(self, start: dt.date, end: dt.date) -> tuple[dt.date, ...]:
        return tuple(day for day in self.days if start <= day <= end)


def _row(day: dt.date, asset: str, close: float, volume: float = 1000.0) -> dict[str, object]:
    return {
        "date": day,
        "asset": asset,
        "open": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": volume,
        "amount": close * volume,
        "up_limit": close * 1.1,
        "down_limit": close * 0.9,
    }


def test_pit_filter_does_not_use_future_st_delisting_or_listing_state() -> None:
    t1, t2, t3 = dt.date(2024, 1, 2), dt.date(2024, 4, 1), dt.date(2024, 4, 2)
    rows = [
        _row(t1, "A", 10.0),
        _row(t1, "B", 10.0),
        _row(t1, "C", 10.0),
        _row(t1, "D", 10.0),
        _row(t2, "A", 11.0),
        _row(t2, "B", 11.0),
        _row(t2, "C", 12.0),
        _row(t2, "D", 11.0),
        _row(t3, "A", 10.0),
        _row(t3, "B", 12.0),
        _row(t3, "C", 10.0),
    ]
    # C is locked at the up limit with a one-word candle only on t2.
    rows = [
        {
            **row,
            "close": 11.0,
            "high": 11.0,
            "low": 11.0,
            "up_limit": 11.0,
        }
        if row["date"] == t2 and row["asset"] == "C"
        else row
        for row in rows
    ]
    panel = pl.DataFrame(rows)
    status = pl.DataFrame(
        {"date": [t2], "asset": ["A"], "is_st": [True]}
    )
    meta = pl.DataFrame(
        {
            "asset": ["A", "B", "C", "D"],
            "list_date": [dt.date(2020, 1, 2), dt.date(2023, 12, 12)] + [dt.date(2020, 1, 2)] * 2,
            "delist_date": [None, None, None, t3],
        }
    )
    config = UniverseFilterConfig(
        exclude_st=True,
        min_listing_days=60,
        exclude_suspended=True,
        exclude_limit_locked_on_close=True,
        max_universe_size=None,
    )
    calendar = _Calendar(dt.date(2019, 12, 1), dt.date(2024, 4, 30))

    t1_result = filter_universe_for_date(
        panel, t1, config, status_frame=status, stock_meta=meta, calendar_obj=calendar
    )
    t2_result = filter_universe_for_date(
        panel, t2, config, status_frame=status, stock_meta=meta, calendar_obj=calendar
    )
    t3_result = filter_universe_for_date(
        panel, t3, config, status_frame=status, stock_meta=meta, calendar_obj=calendar
    )

    # A is not ST yet at t1; B is still short of 60 sessions; D is not delisted yet.
    assert t1_result.assets == ("A", "C", "D")
    # A is ST, C is locked, B is now old enough, D still alive.
    assert t2_result.assets == ("B", "D")
    assert t2_result.exclusion_counts["st"] == 1
    assert t2_result.exclusion_counts["limit_locked_close"] == 1
    # D has delisted, so t1's future state must not be used retroactively.
    assert t3_result.assets == ("A", "B", "C")
    assert "A" in t1_result.assets


def test_missing_historical_st_table_is_explicitly_warned() -> None:
    day = dt.date(2024, 1, 2)
    panel = pl.DataFrame([_row(day, "A", 10.0), _row(day, "B", 11.0)])

    result = filter_universe_for_date(
        panel,
        day,
        UniverseFilterConfig(exclude_st=True, min_listing_days=0),
        calendar_obj=_Calendar(day - dt.timedelta(days=10), day),
    )

    assert "st_history_unavailable" in result.warnings


def _forward_panel() -> pl.DataFrame:
    days = [dt.date(2024, 1, 2) + dt.timedelta(days=i) for i in range(10)]
    closes = {
        "A": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        "B": [20, 19, 18, 17, 16, 15, 14, 13, 12, 11],
        "C": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
    }
    return pl.DataFrame(
        [
            _row(day, asset, float(close))
            for asset, values in closes.items()
            for day, close in zip(days, values, strict=True)
        ]
    ).sort(["asset", "date"])


def test_raw_return_label_hand_calculated() -> None:
    labeled = compute_future_close_return_labels(_forward_panel(), horizon=3)
    first_day = labeled.filter(pl.col("date") == dt.date(2024, 1, 2)).sort("asset")

    assert first_day["future_n_trading_day_close_return"].to_list() == pytest.approx(
        [0.3, -0.15, 0.6]
    )
    # Only the final three signal days per asset are immature.
    assert labeled.filter(
        pl.col("future_n_trading_day_close_return").is_null()
    ).height == 9


def test_excess_mean_label_is_within_signal_date() -> None:
    labeled = compute_future_close_return_labels(
        _forward_panel(), horizon=3, label_kind="excess_mean"
    )
    first_day = labeled.filter(pl.col("date") == dt.date(2024, 1, 2)).sort("asset")

    assert first_day["future_n_trading_day_close_return"].to_list() == pytest.approx(
        [0.05, -0.40, 0.35]
    )
    second_day = labeled.filter(pl.col("date") == dt.date(2024, 1, 3)).sort("asset")
    values = second_day["future_n_trading_day_close_return"].to_list()
    assert sum(values) == pytest.approx(0.0)


def test_cs_rank_label_uses_average_rank_within_signal_date() -> None:
    labeled = compute_future_close_return_labels(
        _forward_panel(), horizon=3, label_kind="cs_rank"
    )
    first_day = labeled.filter(pl.col("date") == dt.date(2024, 1, 2)).sort("asset")

    assert first_day["future_n_trading_day_close_return"].to_list() == pytest.approx(
        [1 / 6, -1 / 6, 1 / 2]
    )


def test_any_immature_asset_excludes_the_whole_signal_date() -> None:
    days = [dt.date(2024, 1, 2) + dt.timedelta(days=i) for i in range(5)]
    rows = [_row(day, "A", 10.0 + i) for i, day in enumerate(days)]
    rows += [_row(day, "B", 20.0 + i) for i, day in enumerate(days[:4])]
    panel = pl.DataFrame(rows)

    labeled = compute_future_close_return_labels(
        panel, horizon=3, label_kind="excess_mean"
    )
    day1 = labeled.filter(pl.col("date") == days[1])

    assert day1["future_n_trading_day_close_return"].to_list() == [None, None]


def test_unknown_label_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported label_kind"):
        compute_future_close_return_labels(_forward_panel(), label_kind="future_leak")


def test_model_key_changes_with_label_kind_and_pit_rules() -> None:
    from quantide.service.model_store import model_key

    base = {"label_kind": "raw_return", "fill_timing": "auction_close"}
    assert model_key("ML", base) != model_key("ML", {**base, "label_kind": "cs_rank"})
    assert model_key("ML", base) != model_key(
        "ML",
        {**base, "universe_filter": {"exclude_st": True, "min_listing_days": 60}},
    )


def test_training_target_uses_the_selected_label_without_reranking() -> None:
    from quantide.strategies.example._ml_support import _training_feature_panel

    panel = _forward_panel().with_columns(pl.lit(0.0).alias("ma20_slope_z"))
    for label_kind in ("raw_return", "excess_mean", "cs_rank"):
        _z_cols, train = _training_feature_panel(
            ["ma20_slope"],
            None,
            panel,
            horizon=3,
            train_window=20,
            label_kind=label_kind,
        )
        expected = compute_future_close_return_labels(
            panel, horizon=3, label_kind=label_kind
        ).filter(pl.col("future_n_trading_day_close_return").is_not_null())
        joined = train.select(
            "date",
            "asset",
            pl.col("label_y").alias("actual"),
        ).join(
            expected.select(
                "date",
                "asset",
                pl.col("future_n_trading_day_close_return").alias("expected"),
            ),
            on=["date", "asset"],
            how="inner",
        )

        assert joined.height > 0
        assert joined.filter(
            ~(pl.col("actual") - pl.col("expected")).abs().le(1e-12)
        ).is_empty(), label_kind


def test_panel_filter_drops_an_asset_only_on_its_st_date() -> None:
    from quantide.factors.universe import filter_universe_panel

    days = [dt.date(2024, 1, 2), dt.date(2024, 1, 3), dt.date(2024, 1, 4)]
    panel = pl.DataFrame(
        [_row(day, asset, 10.0) for day in days for asset in ("A", "B")]
    )
    status = pl.DataFrame(
        {"date": [days[1]], "asset": ["A"], "is_st": [True]}
    )

    filtered, result = filter_universe_panel(
        panel,
        UniverseFilterConfig(max_universe_size=None),
        status_frame=status,
        calendar_obj=_Calendar(dt.date(2023, 12, 1), dt.date(2024, 1, 5)),
    )

    assert set(result.assets) == {"A", "B"}
    assert filtered.filter(
        (pl.col("asset") == "A") & (pl.col("date") == days[1])
    ).is_empty()
    assert filtered.filter(
        (pl.col("asset") == "A") & (pl.col("date") == days[0])
    ).height == 1
    assert filtered.filter(pl.col("asset") == "B").height == 3


def test_labels_use_authoritative_exit_session_and_never_skip_a_gap(monkeypatch):
    from types import SimpleNamespace

    from quantide.strategies.example import _ml_support

    days = [dt.date(2024, 1, day) for day in (2, 3, 4, 5, 8, 9, 10)]
    index = {day: position for position, day in enumerate(days)}
    monkeypatch.setattr(
        _ml_support,
        "calendar",
        SimpleNamespace(
            day_frames=object(),
            day_shift=lambda day, offset: days[min(len(days) - 1, index[day] + offset)],
            get_trade_dates=lambda start, end: [day for day in days if start <= day <= end],
        ),
    )
    rows = []
    for asset in ("A", "B", "C"):
        for position, day in enumerate(days):
            if asset == "A" and day == dt.date(2024, 1, 3):
                continue
            rows.append(
                {"date": day, "asset": asset, "close": 10.0 + position, "f_z": float(position)}
            )
    panel = pl.DataFrame(rows).sort(["asset", "date"])

    raw = compute_future_close_return_labels(panel, horizon=1, label_kind="raw_return")
    a_first = raw.filter(
        (pl.col("asset") == "A") & (pl.col("date") == dt.date(2024, 1, 2))
    )

    assert a_first["future_n_trading_day_close_return"].to_list() == [None]
    from quantide.strategies.example._ml_support import _training_feature_panel

    _z_cols, training = _training_feature_panel(
        ["f"], None, panel, 1, 45, "cs_rank"
    )
    assert training.filter(pl.col("date") == dt.date(2024, 1, 2)).is_empty()

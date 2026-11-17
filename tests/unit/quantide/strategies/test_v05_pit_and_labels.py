"""Independent hand-calculated oracles for WP-3 PIT filtering and labels."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import polars as pl
import pytest

from quantide.factors.universe import UniverseFilterConfig, filter_universe_for_date
from quantide.strategies.example import _ml_support
from quantide.strategies.example._ml_support import (
    _format_candidate_rows,
    compute_future_close_return_labels,
)


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


class _SyntheticCalendar:
    """Explicitly declares every calendar day as a session for synthetic panels."""

    day_frames = object()

    def __init__(self, start: dt.date, end: dt.date) -> None:
        self.days = [start + dt.timedelta(days=index) for index in range((end - start).days + 1)]

    def get_trade_dates(self, start: dt.date, end: dt.date) -> tuple[dt.date, ...]:
        return tuple(day for day in self.days if start <= day <= end)


@pytest.fixture(autouse=True)
def _explicit_synthetic_calendar(monkeypatch):
    from quantide.strategies.example import _ml_support

    monkeypatch.setattr(
        _ml_support,
        "calendar",
        _SyntheticCalendar(dt.date(2019, 1, 1), dt.date(2025, 12, 31)),
    )


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
    status = pl.DataFrame({"date": [t2], "asset": ["A"], "is_st": [True]})
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
    assert labeled.filter(pl.col("future_n_trading_day_close_return").is_null()).height == 9


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
    labeled = compute_future_close_return_labels(_forward_panel(), horizon=3, label_kind="cs_rank")
    first_day = labeled.filter(pl.col("date") == dt.date(2024, 1, 2)).sort("asset")

    assert first_day["future_n_trading_day_close_return"].to_list() == pytest.approx(
        [1 / 6, -1 / 6, 1 / 2]
    )


def test_any_immature_asset_excludes_the_whole_signal_date() -> None:
    days = [dt.date(2024, 1, 2) + dt.timedelta(days=i) for i in range(5)]
    rows = [_row(day, "A", 10.0 + i) for i, day in enumerate(days)]
    rows += [_row(day, "B", 20.0 + i) for i, day in enumerate(days[:4])]
    panel = pl.DataFrame(rows)

    labeled = compute_future_close_return_labels(panel, horizon=3, label_kind="excess_mean")
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
        assert joined.filter(~(pl.col("actual") - pl.col("expected")).abs().le(1e-12)).is_empty(), (
            label_kind
        )


def test_panel_filter_drops_an_asset_only_on_its_st_date() -> None:
    from quantide.factors.universe import filter_universe_panel

    days = [dt.date(2024, 1, 2), dt.date(2024, 1, 3), dt.date(2024, 1, 4)]
    panel = pl.DataFrame([_row(day, asset, 10.0) for day in days for asset in ("A", "B")])
    status = pl.DataFrame({"date": [days[1]], "asset": ["A"], "is_st": [True]})

    filtered, result = filter_universe_panel(
        panel,
        UniverseFilterConfig(max_universe_size=None),
        status_frame=status,
        calendar_obj=_Calendar(dt.date(2023, 12, 1), dt.date(2024, 1, 5)),
    )

    assert set(result.assets) == {"A", "B"}
    assert filtered.filter((pl.col("asset") == "A") & (pl.col("date") == days[1])).is_empty()
    assert filtered.filter((pl.col("asset") == "A") & (pl.col("date") == days[0])).height == 1
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
    a_first = raw.filter((pl.col("asset") == "A") & (pl.col("date") == dt.date(2024, 1, 2)))

    assert a_first["future_n_trading_day_close_return"].to_list() == [None]
    from quantide.strategies.example._ml_support import _training_feature_panel

    _z_cols, training = _training_feature_panel(["f"], None, panel, 1, 45, "cs_rank")
    assert training.filter(pl.col("date") == dt.date(2024, 1, 2)).is_empty()


def test_shared_st_contract_conflict_and_explicit_disabled_filter(monkeypatch) -> None:
    day = dt.date(2024, 1, 2)
    frame = pl.DataFrame([_row(day, "A", 10.0), _row(day, "B", 11.0)]).with_columns(
        pl.Series("is_st", [False, False])
    )
    status = pl.DataFrame({"date": [day, day], "asset": ["A", "B"], "is_st": [True, False]})
    monkeypatch.setattr(_ml_support, "load_st_status_frame", lambda: status)
    strategy = SimpleNamespace(
        universe_filter=UniverseFilterConfig(
            exclude_st=True, min_listing_days=0, max_universe_size=None
        ),
        fill_timing="close",
        _universe_diagnostics={},
    )

    eligible = _ml_support._attach_historical_eligibility(strategy, frame)
    flags = {row["asset"]: row["_eligible"] for row in eligible.iter_rows(named=True)}
    assert flags == {"A": False, "B": True}
    assert (
        "st_status_conflict" in strategy._universe_diagnostics["historical_eligibility"]["warnings"]
    )

    canonical = filter_universe_for_date(
        frame,
        day,
        strategy.universe_filter,
        status_frame=status,
        calendar_obj=_Calendar(day - dt.timedelta(days=10), day),
    )
    assert canonical.assets == ("B",)
    assert "st_status_conflict" in canonical.warnings

    relaxed = UniverseFilterConfig(exclude_st=False, min_listing_days=0, max_universe_size=None)
    strategy.universe_filter = relaxed
    strategy._universe_diagnostics = {}
    eligible_relaxed = _ml_support._attach_historical_eligibility(strategy, frame)
    assert set(eligible_relaxed.filter(pl.col("_eligible"))["asset"].to_list()) == {"A", "B"}
    canonical_relaxed = filter_universe_for_date(
        frame,
        day,
        relaxed,
        status_frame=status,
        calendar_obj=_Calendar(day - dt.timedelta(days=10), day),
    )
    assert canonical_relaxed.assets == ("A", "B")

    scored = pl.DataFrame(
        {
            "asset": ["A"],
            "close": [10.0],
            "volume": [1000.0],
            "is_st": [True],
            "up_limit": [11.0],
            "ml_score": [1.0],
            "_eligible": [True],
        }
    )
    picks = _format_candidate_rows(scored, day, "Prior-Ridge", limit=1)
    assert [item["asset"] for item in picks] == ["A"]


def test_shared_st_contract_reports_unknown_input_without_sidecar(monkeypatch) -> None:
    from quantide.factors.universe import attach_status_contract

    day = dt.date(2024, 1, 2)
    frame = pl.DataFrame(
        [{"date": day, "asset": "A", "is_st": None}, {"date": day, "asset": "B", "is_st": False}]
    )
    warnings: list[str] = []
    counts: dict[str, int] = {}
    out = attach_status_contract(frame, None, warnings, counts)
    assert out["is_st"].to_list() == [False, False]
    assert "st_history_unavailable" in warnings
    assert counts["st_history_incomplete"] == 1

    status = pl.DataFrame({"date": [day], "asset": ["A"], "is_st": [True]})
    warnings = []
    counts = {}
    out = attach_status_contract(frame, status, warnings, counts)
    assert out["is_st"].to_list() == [True, False]
    assert "st_history_unavailable" not in warnings
    assert "st_history_incomplete" not in warnings


def test_listing_zero_and_boundary_contract_matches_canonical_filter() -> None:
    day = dt.date(2024, 3, 1)
    panel = pl.DataFrame([_row(day, "A", 10.0), _row(day, "B", 11.0), _row(day, "C", 12.0)])
    panel = pl.concat([panel, pl.DataFrame([_row(day, "D", 13.0)])], how="vertical")
    meta = pl.DataFrame(
        {
            "asset": ["A", "B", "C", "D"],
            "list_date": [
                day - dt.timedelta(days=30),
                day,
                day - dt.timedelta(days=30),
                day + dt.timedelta(days=5),
            ],
            "delist_date": [None, None, day, None],
        }
    )
    calendar = _Calendar(day - dt.timedelta(days=60), day)
    zero = filter_universe_for_date(
        panel,
        day,
        UniverseFilterConfig(min_listing_days=0, max_universe_size=None),
        stock_meta=meta,
        calendar_obj=calendar,
    )
    assert zero.assets == ("A", "B")

    one = filter_universe_for_date(
        panel,
        day,
        UniverseFilterConfig(min_listing_days=1, max_universe_size=None),
        stock_meta=meta,
        calendar_obj=calendar,
    )
    assert one.assets == ("A", "B")

    two = filter_universe_for_date(
        panel,
        day,
        UniverseFilterConfig(min_listing_days=2, max_universe_size=None),
        stock_meta=meta,
        calendar_obj=calendar,
    )
    assert two.assets == ("A",)

    class _NoCalendar:
        def get_trade_dates(self, *_args):
            raise RuntimeError("calendar unavailable")

    degraded = filter_universe_for_date(
        panel,
        day,
        UniverseFilterConfig(min_listing_days=2, max_universe_size=None),
        stock_meta=meta,
        calendar_obj=_NoCalendar(),
    )
    assert degraded.assets == ("A", "B")
    assert "calendar_unavailable" in degraded.warnings


def test_listing_contract_applies_known_dates_when_calendar_is_missing(monkeypatch) -> None:
    from quantide.strategies.example import _ml_listing

    day = dt.date(2024, 3, 1)
    frame = pl.DataFrame(
        [_row(day, "A", 10.0), _row(day, "B", 11.0), _row(day, "C", 12.0), _row(day, "D", 13.0)]
    )
    meta = pl.DataFrame(
        {
            "asset": ["A", "B", "C", "D"],
            "list_date": [
                day - dt.timedelta(days=30),
                day,
                day - dt.timedelta(days=30),
                day + dt.timedelta(days=5),
            ],
            "delist_date": [None, None, day, None],
        }
    )
    monkeypatch.setattr(_ml_listing.stock_list, "_data", meta)
    diagnostics: dict[str, object] = {}
    filtered = _ml_listing._apply_listing_eligibility(frame, 0, diagnostics)
    assert set(filtered["asset"].to_list()) == {"A", "B"}

    class _NoCalendar:
        def get_trade_dates(self, *_args):
            raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(_ml_listing, "calendar", _NoCalendar())
    diagnostics = {}
    filtered = _ml_listing._apply_listing_eligibility(frame, 2, diagnostics)
    assert set(filtered["asset"].to_list()) == {"A", "B"}
    assert diagnostics["historical_listing"]["warnings"] == ["calendar_unavailable"]


def test_authoritative_calendar_tail_keeps_middle_gap_null(monkeypatch) -> None:
    from types import SimpleNamespace

    from quantide.strategies.example import _ml_labels

    sessions = [dt.date(2024, 1, 2), dt.date(2024, 1, 3), dt.date(2024, 1, 4)]
    monkeypatch.setattr(
        _ml_labels,
        "_calendar_module",
        lambda: SimpleNamespace(
            day_frames=object(),
            get_trade_dates=lambda _start, _end: sessions,
        ),
    )
    panel = pl.DataFrame(
        [
            {"date": sessions[0], "asset": "A", "close": 10.0},
            {"date": sessions[2], "asset": "A", "close": 30.0},
        ]
    )
    for label_kind in ("raw_return", "excess_mean", "cs_rank"):
        labeled = compute_future_close_return_labels(panel, horizon=1, label_kind=label_kind)
        assert labeled["future_n_trading_day_close_return"].to_list() == [None, None]


def test_unavailable_calendar_fails_closed_without_row_shift(monkeypatch) -> None:
    from types import SimpleNamespace

    from quantide.strategies.example import _ml_support
    from quantide.strategies.example._ml_support import InsufficientTrainingDataError

    monkeypatch.setattr(
        _ml_support,
        "calendar",
        SimpleNamespace(day_frames=None, get_trade_dates=lambda *_args: ()),
    )
    panel = _forward_panel().with_columns(pl.lit(0.0).alias("ma20_slope_z"))
    labeled = compute_future_close_return_labels(panel, horizon=1)
    assert labeled["future_n_trading_day_close_return"].is_null().all()
    with pytest.raises(InsufficientTrainingDataError):
        _ml_support._training_feature_panel(["ma20_slope"], None, panel, 1, 20, "raw_return")


@pytest.mark.parametrize(
    "filename",
    ["calendar.parquet", "stock_list.parquet", "daily_basic.parquet", "stock_status_pit.parquet"],
)
def test_panel_cache_fingerprint_tracks_all_pit_input_files(
    tmp_path, monkeypatch, filename
) -> None:
    from quantide.strategies.example import _ml_support

    data = tmp_path / "data"
    data.mkdir()
    for name in (
        "calendar.parquet",
        "stock_list.parquet",
        "daily_basic.parquet",
        "stock_status_pit.parquet",
    ):
        (data / name).write_bytes(b"x")
    monkeypatch.setattr(_ml_support, "get_data_home", lambda: str(tmp_path))
    before = _ml_support._pit_fingerprint()
    (data / filename).write_bytes(b"xx")
    after = _ml_support._pit_fingerprint()
    assert before != after


def test_label_cache_identity_tracks_prices_and_eligibility(monkeypatch) -> None:
    from types import SimpleNamespace

    from quantide.strategies.example import _ml_support

    days = [dt.date(2024, 1, 2) + dt.timedelta(days=index) for index in range(6)]
    monkeypatch.setattr(
        _ml_support,
        "calendar",
        SimpleNamespace(
            day_frames=days,
            get_trade_dates=lambda start, end: [day for day in days if start <= day <= end],
        ),
    )
    closes = [10, 11, 12, 13, 14, 15]
    base = pl.DataFrame(
        [
            {
                "date": day,
                "asset": "A",
                "close": float(close),
                "ma20_slope": 1.0,
                "ma20_slope_z": 0.0,
                "_eligible": True,
            }
            for day, close in zip(days, closes, strict=True)
        ]
    )
    key = ("same",)
    _, first = _ml_support._training_feature_panel(["ma20_slope"], key, base, 1, 20)
    amended = base.with_columns(
        pl.when(pl.col("date") == days[-1]).then(28.0).otherwise(pl.col("close")).alias("close")
    )
    _, second = _ml_support._training_feature_panel(["ma20_slope"], key, amended, 1, 20)
    first_labels = {row["date"]: row["label_y"] for row in first.iter_rows(named=True)}
    second_labels = {row["date"]: row["label_y"] for row in second.iter_rows(named=True)}
    assert second_labels[days[-2]] == pytest.approx(1.0)
    assert second_labels[days[-2]] != first_labels[days[-2]]
    for day in days[:-2]:
        assert second_labels[day] == pytest.approx(first_labels[day])

    ineligible = amended.with_columns(
        pl.when(pl.col("date") == days[-2])
        .then(False)
        .otherwise(pl.col("_eligible"))
        .alias("_eligible")
    )
    _, third = _ml_support._training_feature_panel(["ma20_slope"], key, ineligible, 1, 20)
    assert days[-2] not in {row["date"] for row in third.iter_rows(named=True)}

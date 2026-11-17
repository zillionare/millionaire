"""Regression tests for the shared wind-tunnel service."""

from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path

import polars as pl

from quantide.factors import plugins
from quantide.service.factor_wind_tunnel import run_factor_wind_tunnel


def _frame(days: int = 40, assets: int = 5) -> pl.DataFrame:
    rows = []
    start = dt.date(2025, 1, 2)
    for index in range(days):
        for asset in range(assets):
            close = 10.0 + asset + index * 0.1
            rows.append(
                {
                    "date": start + dt.timedelta(days=index),
                    "asset": f"{asset:06d}.SZ",
                    "open": close - 0.05,
                    "high": close + 0.2,
                    "low": close - 0.2,
                    "close": close,
                    "volume": 1000.0 + index,
                    "amount": 10_000.0 + index,
                    "adjust": 1.0,
                }
            )
    return pl.DataFrame(rows).sort(["asset", "date"])


def _bad_plugin(directory: Path) -> None:
    (directory / "ai_bad.py").write_text(
        textwrap.dedent(
            """
            from quantide.factors.plugins import FactorPlugin

            FACTOR_PLUGIN = FactorPlugin(
                factor_id="ai_bad",
                display_name="bad",
                compute=lambda panel: panel["close"] * float("nan"),
                required_columns=("close",),
            )
            """
        ),
        encoding="utf-8",
    )


def test_failed_audit_returns_result_without_crashing(tmp_path: Path, monkeypatch) -> None:
    _bad_plugin(tmp_path)
    monkeypatch.setattr("quantide.config.settings.get_factor_dir", lambda: str(tmp_path))
    plugins.clear_plugin_cache()
    frame = _frame()
    dates = sorted(frame["date"].unique().to_list())

    result = run_factor_wind_tunnel(
        "ai_bad",
        frame=frame,
        cutoffs=(dates[10], dates[20], dates[30]),
        save=False,
    )

    assert result.status == "FAIL"
    assert result.report.status.value == "FAIL"
    assert result.orthogonality.status == "INCONCLUSIVE"
    assert result.orthogonality.max_abs_rank_corr is None
    plugins.clear_plugin_cache()


def test_monthly_hfq_ohlc_uses_each_day_adjustment_and_month_end_availability(monkeypatch):
    import datetime as dt

    import polars as pl

    from quantide.data.models.calendar import calendar
    from quantide.factors.plugins import FactorPlugin, compute_plugin
    from quantide.service.factor_wind_tunnel import _monthly_frame

    monkeypatch.setattr(
        calendar, "day_shift", lambda start, offset: start + dt.timedelta(days=offset)
    )

    daily = pl.DataFrame(
        {
            "asset": ["A", "A", "A"],
            "date": [dt.date(2024, 1, 2), dt.date(2024, 1, 15), dt.date(2024, 1, 31)],
            "open": [10.0, 8.0, 6.0],
            "high": [11.0, 9.0, 7.0],
            "low": [9.0, 7.0, 5.0],
            "close": [10.0, 8.0, 6.0],
            "volume": [100.0, 100.0, 100.0],
            "amount": [1000.0, 800.0, 600.0],
            "adjust": [1.0, 1.5, 2.0],
        }
    )
    frame = _monthly_frame(daily)
    plugin = FactorPlugin(
        factor_id="monthly_probe",
        display_name="monthly",
        bar_interval="1M",
        required_columns=("close",),
        warmup_bars=0,
        compute=lambda panel: panel["close"],
    )

    output = compute_plugin(frame, plugin)
    row = frame.row(0, named=True)

    assert row["dt"] == dt.date(2024, 1, 31)
    assert row["open"] == 10.0
    assert row["high"] == 14.0
    assert row["low"] == 9.0
    assert row["close"] == 12.0
    assert output["monthly_probe"].to_list() == [12.0]


def test_monthly_partial_month_is_filtered_per_security(monkeypatch):
    import datetime as dt

    import polars as pl

    from quantide.data.models.calendar import calendar
    from quantide.service.factor_wind_tunnel import _monthly_frame

    monkeypatch.setattr(
        calendar, "day_shift", lambda start, offset: start + dt.timedelta(days=offset)
    )
    daily = pl.DataFrame(
        {
            "asset": ["A", "A", "B", "B"],
            "date": [
                dt.date(2024, 1, 2),
                dt.date(2024, 1, 31),
                dt.date(2024, 1, 2),
                dt.date(2024, 1, 15),
            ],
            "open": [1.0, 1.0, 2.0, 2.0],
            "high": [1.0, 1.0, 2.0, 2.0],
            "low": [1.0, 1.0, 2.0, 2.0],
            "close": [1.0, 1.0, 2.0, 2.0],
            "volume": [1.0] * 4,
            "amount": [1.0] * 4,
            "adjust": [1.0] * 4,
        }
    )

    frame = _monthly_frame(daily)

    assert frame.filter(pl.col("asset") == "A")["dt"].to_list() == [dt.date(2024, 1, 31)]
    assert frame.filter(pl.col("asset") == "B").is_empty()


def test_monthly_raw_preserves_source_adjustment(monkeypatch):
    import datetime as dt

    import polars as pl

    from quantide.data.models.calendar import calendar
    from quantide.service.factor_wind_tunnel import _monthly_frame

    monkeypatch.setattr(
        calendar, "day_shift", lambda start, offset: start + dt.timedelta(days=offset)
    )
    daily = pl.DataFrame(
        {
            "asset": ["A", "A"],
            "date": [dt.date(2024, 1, 2), dt.date(2024, 1, 31)],
            "open": [10.0, 10.0],
            "high": [10.0, 10.0],
            "low": [10.0, 10.0],
            "close": [10.0, 10.0],
            "volume": [1.0, 1.0],
            "amount": [1.0, 1.0],
            "adjust": [1.0, 2.0],
        }
    )

    frame = _monthly_frame(daily, "raw")

    assert frame.row(0, named=True)["adjust"] == 2.0
    assert frame.row(0, named=True)["close"] == 10.0


def test_monthly_unknown_calendar_is_inconclusive(monkeypatch):
    import datetime as dt

    import polars as pl

    from quantide.data.models.calendar import calendar
    from quantide.service.factor_wind_tunnel import (
        MonthlyCalendarUnavailable,
        _inconclusive_calendar_result,
        _monthly_frame,
    )

    def unavailable(start, offset):
        raise ValueError("calendar not loaded")

    monkeypatch.setattr(calendar, "day_shift", unavailable)
    daily = pl.DataFrame(
        {
            "asset": ["A"],
            "date": [dt.date(2024, 1, 31)],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
            "amount": [1.0],
            "adjust": [1.0],
        }
    )

    try:
        _monthly_frame(daily)
    except MonthlyCalendarUnavailable:
        pass
    else:
        raise AssertionError("unknown calendar must not be treated as closed")
    result = _inconclusive_calendar_result("demo", "calendar unavailable")
    assert result.status == "INCONCLUSIVE"
    assert result.orthogonality.status == "INCONCLUSIVE"

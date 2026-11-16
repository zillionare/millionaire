"""Custom factor study tests."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.service import factor_study


def _panel() -> pl.DataFrame:
    dates = [dt.date(2024, 1, 2) + dt.timedelta(days=index) for index in range(12)]
    rows = []
    for asset in range(120):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "bias_5": float(asset + index),
                    "open": 10.0 + asset * 0.1 + index * 0.05,
                    "close": 10.0 + asset * 0.1 + index * 0.06,
                }
            )
    return pl.DataFrame(rows)


def _trading_days(start, end):
    return tuple(day for day in _panel()["date"].unique().sort().to_list() if start <= day <= end)


def test_custom_study_is_marked_temporary(monkeypatch) -> None:
    monkeypatch.setattr(factor_study, "load_factor_panel", lambda start, end: _panel())
    monkeypatch.setattr(factor_study, "trading_days", _trading_days)
    study = factor_study.run_custom_study(
        "bias_5",
        dt.date(2024, 1, 2),
        dt.date(2024, 1, 8),
        [1, 3],
        "open",
    )

    assert study.study_id
    assert study.holding_days == (1, 3)
    assert len(study.results) == 2
    assert study.cohort.n_days > 0
    assert study.calendar_version.startswith("2024-01-02")
    payload = study.as_dict()
    assert payload["kind"] == "custom_study"
    assert payload["start"] == "2024-01-02"
    assert payload["calendar_version"] == study.calendar_version
    assert len(payload["results"]) == 2


def test_calendar_version_is_content_sensitive() -> None:
    first = (dt.date(2026, 11, 2), dt.date(2026, 11, 3), dt.date(2026, 11, 6))
    second = (dt.date(2026, 11, 2), dt.date(2026, 11, 4), dt.date(2026, 11, 6))
    assert factor_study.calendar_version(first) != factor_study.calendar_version(second)


def test_custom_study_rejects_invalid_input(monkeypatch) -> None:
    monkeypatch.setattr(factor_study, "load_factor_panel", lambda start, end: _panel())
    monkeypatch.setattr(factor_study, "trading_days", _trading_days)
    with pytest.raises(KeyError):
        factor_study.run_custom_study("missing", dt.date(2024, 1, 2), dt.date(2024, 1, 8), [1])
    with pytest.raises(ValueError):
        factor_study.run_custom_study("bias_5", dt.date(2024, 1, 8), dt.date(2024, 1, 2), [1])
    with pytest.raises(ValueError):
        factor_study.run_custom_study("bias_5", dt.date(2024, 1, 2), dt.date(2024, 1, 8), [4])

"""Raw source version contract tests for factor tracking."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.data.models.calendar import calendar
from quantide.data.models.stocks import stock_list
from quantide.service import factor_sources


class _Frames:
    def __init__(self, days: list[dt.date]) -> None:
        self._days = days

    def __len__(self) -> int:
        return len(self._days)

    def to_pylist(self) -> list[dt.date]:
        return self._days


@pytest.fixture(autouse=True)
def reset_source_cache(monkeypatch):
    monkeypatch.setattr(factor_sources, "_SOURCE_CACHE", None)
    yield


def test_calendar_version_tracks_content_not_just_bounds(monkeypatch) -> None:
    first = [dt.date(2024, 1, day) for day in (2, 3, 4)]
    second = [dt.date(2024, 1, day) for day in (2, 4, 5)]
    monkeypatch.setattr(calendar, "day_frames", _Frames(first))
    left = factor_sources._calendar_version()
    monkeypatch.setattr(calendar, "day_frames", _Frames(second))
    right = factor_sources._calendar_version()
    assert left is not None and right is not None
    assert left != right


def test_universe_version_tracks_security_master_and_constituents(monkeypatch) -> None:
    class _Weights:
        signature = "weights-1"

        def _storage_signature(self) -> str:
            return self.signature

    weights = _Weights()
    monkeypatch.setattr(stock_list, "_data", pl.DataFrame({"asset": ["000001", "000002"]}))
    monkeypatch.setattr("quantide.data.get_index_weight_store", lambda: weights)
    left = factor_sources._universe_version()
    weights.signature = "weights-2"
    right = factor_sources._universe_version()
    assert left is not None and right is not None
    assert left != right

    monkeypatch.setattr(stock_list, "_data", pl.DataFrame({"asset": ["000001", "000003"]}))
    assert factor_sources._universe_version() != right


def test_source_versions_are_cached_until_refreshed(monkeypatch) -> None:
    calls = []

    def _market() -> str:
        calls.append("market")
        return "market-1"

    monkeypatch.setattr(factor_sources, "_store_token", lambda: (1.0, "2024-01-13"))
    monkeypatch.setattr(factor_sources, "_market_version", lambda token: _market())
    monkeypatch.setattr(factor_sources, "_calendar_version", lambda: "calendar-1")
    monkeypatch.setattr(factor_sources, "_universe_version", lambda: "universe-1")
    monkeypatch.setattr(factor_sources, "_dependency_version", lambda: "dependency-1")

    assert factor_sources.source_versions()["source_market_version"] == "market-1"
    assert factor_sources.source_versions()["source_market_version"] == "market-1"
    assert len(calls) == 1
    factor_sources.source_versions(refresh=True)
    assert len(calls) == 2


def test_market_version_reads_dates_signature_and_cutoff(monkeypatch, tmp_path) -> None:
    index = tmp_path / "daily-dates.pq"
    index.write_bytes(b"")
    marker = tmp_path / "daily-dates.signature.json"
    marker.write_text('{"sha256": "sig-1"}', encoding="utf-8")
    monkeypatch.setattr(factor_sources, "_dates_index_path", lambda: index)
    assert factor_sources._market_version((1.0, "2024-01-13")) == "sig-1:2024-01-13"
    marker.unlink()
    assert factor_sources._market_version((2.0, "2024-01-13")) == "2:2024-01-13"
    assert factor_sources._market_version(None) is None


def test_store_token_uses_dates_index_instead_of_walking_partitions(monkeypatch, tmp_path) -> None:
    class _Bars:
        end = dt.date(2024, 1, 13)

        def _dates_file_path(self):
            return index

    index = tmp_path / "daily-dates.pq"
    index.write_bytes(b"")
    monkeypatch.setattr("quantide.data.models.daily_bars.daily_bars", _Bars())
    assert factor_sources._store_token() == (float(index.stat().st_mtime_ns), "2024-01-13")


def test_latest_market_day_comes_from_the_source_token(monkeypatch) -> None:
    monkeypatch.setattr(
        factor_sources,
        "source_versions",
        lambda **_: {"source_token": [1.0, "2024-01-13"]},
    )
    assert factor_sources.latest_market_day() == dt.date(2024, 1, 13)
    monkeypatch.setattr(factor_sources, "source_versions", lambda **_: {"source_token": None})
    assert factor_sources.latest_market_day() is None


def test_source_contract_requires_every_version() -> None:
    complete = {
        "source_token": [1.0, "2024-01-13"],
        "source_market_version": "m",
        "source_calendar_version": "c",
        "source_universe_version": "u",
        "source_dependency_version": "d",
    }
    assert factor_sources.source_complete(complete)
    assert factor_sources.source_complete({**complete, "source_calendar_version": None}) is False
    assert factor_sources.source_fields_match(complete, dict(complete))
    assert not factor_sources.source_fields_match(
        complete, {**complete, "source_market_version": "x"}
    )
    assert not factor_sources.source_fields_match(
        complete, {**complete, "source_market_version": None}
    )


def test_source_advanced_detects_fields_and_token_order() -> None:
    base = {
        "source_token": [1.0, "2024-01-13"],
        "source_market_version": "m",
        "source_calendar_version": "c",
        "source_universe_version": "u",
        "source_dependency_version": "d",
    }
    assert factor_sources.source_advanced(base, {**base, "source_calendar_version": "c2"})
    assert factor_sources.source_advanced(base, {**base, "source_token": [2.0, "2024-01-13"]})
    assert not factor_sources.source_advanced(base, {**base, "source_token": [0.5, "2024-01-13"]})
    assert not factor_sources.source_advanced(base, dict(base))

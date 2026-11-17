"""Final study/tracking ingress contracts with persisted PIT status inputs."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import polars as pl
import pytest

from quantide.service import factor_study, factor_tracking, factor_tracking_inputs
from tests.unit.quantide.service.test_factor_tracking import _DAYS, _SOURCE, _days, _panel


@pytest.fixture
def source_environment(tmp_path, monkeypatch):
    from quantide.config import settings
    from quantide.data.models import stocks

    home = tmp_path / "market"
    data = home / "data"
    data.mkdir(parents=True)
    assets = _panel()["asset"].unique().sort().to_list()
    metadata = pl.DataFrame(
        {
            "asset": assets,
            "list_date": [dt.date(2020, 1, 2)] * len(assets),
            "delist_date": [None] * len(assets),
        }
    )
    monkeypatch.setattr(settings, "get_data_home", lambda: str(home))
    monkeypatch.setattr(stocks, "stock_list", SimpleNamespace(size=len(assets), data=metadata))
    monkeypatch.setattr(factor_tracking, "_root", lambda: tmp_path / "tracking")
    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: dict(_SOURCE))
    monkeypatch.setattr(factor_tracking, "trading_days", _days)
    monkeypatch.setattr(factor_tracking, "_latest_market_day", lambda: None)
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    monkeypatch.setattr(factor_study, "load_factor_panel", lambda start, end: _panel())
    monkeypatch.setattr(factor_study, "trading_days", _days)
    return data, assets


def _save_profile(factor_id, *, exclude_st=True):
    return factor_tracking.save_profile(
        factor_id,
        lookback="3y",
        primary_holding_days=1,
        comparison_holding_days=[1],
        price_field="open",
        enabled=True,
        universe_filter={
            "exclude_st": exclude_st,
            "min_listing_days": 0,
            "max_universe_size": None,
        },
    )


def test_real_status_sidecar_applies_per_profile_in_shared_refresh(source_environment):
    data, assets = source_environment
    pl.DataFrame(
        [
            {"date": day, "asset": asset, "is_st": asset == assets[0]}
            for day in _DAYS
            for asset in assets
        ]
    ).write_parquet(data / "stock_status_pit.parquet")
    _save_profile("bias_5", exclude_st=True)
    _save_profile("rs_board_5d", exclude_st=False)

    factor_tracking._refresh_group(["bias_5", "rs_board_5d"], "3y")
    strict = factor_tracking.load_state("bias_5")["current"]
    relaxed = factor_tracking.load_state("rs_board_5d")["current"]
    assert strict is not None and relaxed is not None
    for day in _DAYS:
        strict_day = strict["universe_diagnostics"]["by_date"][day.isoformat()]
        relaxed_day = relaxed["universe_diagnostics"]["by_date"][day.isoformat()]
        assert assets[0] not in strict_day["assets"]
        assert assets[0] in relaxed_day["assets"]
        assert strict_day["exclusion_counts"]["st"] == 1
    assert strict["universe_filter"]["exclude_st"] is True
    assert relaxed["universe_filter"]["exclude_st"] is False
    assert (
        strict["primary_metrics"]["diagnostics"]["n_valid_pairs"]
        < relaxed["primary_metrics"]["diagnostics"]["n_valid_pairs"]
    )


def test_missing_history_diagnostics_survive_study_and_persisted_tracking(source_environment):
    _data, assets = source_environment
    config = {"exclude_st": True, "min_listing_days": 0, "max_universe_size": None}
    study = factor_study.run_custom_study(
        "bias_5", _DAYS[0], _DAYS[-1], [1], universe_filter=config
    )
    first = study.as_dict()["universe_diagnostics"]["by_date"][_DAYS[0].isoformat()]
    assert "st_history_unavailable" in first["warnings"]
    assert set(first["assets"]) == set(assets)
    _save_profile("bias_5")
    state = factor_tracking.refresh_factor("bias_5")
    assert state["last_attempt"]["status"] == "succeeded"
    persisted = factor_tracking.load_state("bias_5")["current"]
    assert persisted is not None
    diagnostic = persisted["universe_diagnostics"]["by_date"][_DAYS[0].isoformat()]
    assert "st_history_unavailable" in diagnostic["warnings"]
    assert persisted["universe_filter"]["min_listing_days"] == 0


def test_mixed_native_group_uses_each_factors_signal_panel(source_environment, monkeypatch):
    plugins = {"rs_board_5d": SimpleNamespace(bar_interval="1M")}
    monkeypatch.setattr(
        factor_tracking_inputs,
        "discover_factor_plugins",
        lambda: SimpleNamespace(by_id=lambda factor_id: plugins.get(factor_id)),
    )
    seen = []

    def native_panel(factor_id, plugin, start, end):
        seen.append(factor_id)
        return _panel().select("date", "asset", "open", "close", factor_id)

    monkeypatch.setattr(factor_study, "load_native_daily_panel", native_panel)
    _save_profile("bias_5")
    _save_profile("rs_board_5d")
    factor_tracking._refresh_group(["bias_5", "rs_board_5d"], "3y")
    assert seen == ["bias_5", "rs_board_5d"]
    for factor_id in seen:
        state = factor_tracking.load_state(factor_id)
        assert state["last_attempt"]["status"] == "succeeded"
        assert state["current"]["primary_metrics"]["rank_ic"]["n_days"] > 0


def test_unknown_status_in_persisted_sidecar_remains_missing(source_environment):
    data, assets = source_environment
    pl.DataFrame(
        [
            {"date": day, "asset": asset, "is_st": None if asset == assets[0] else False}
            for day in _DAYS
            for asset in assets
        ],
        schema={"date": pl.Date, "asset": pl.String, "is_st": pl.Boolean},
    ).write_parquet(data / "stock_status_pit.parquet")
    _save_profile("bias_5")
    state = factor_tracking.refresh_factor("bias_5")
    assert state["current"] is not None
    warning = state["current"]["universe_diagnostics"]["by_date"][_DAYS[0].isoformat()]
    assert "st_history_incomplete" in warning["warnings"]


@pytest.mark.parametrize(
    "filename",
    ["stock_status_pit.parquet", "stock_list.parquet", "daily_basic.parquet", "calendar.parquet"],
)
def test_tracking_source_identity_detects_auxiliary_file_revision(
    source_environment, monkeypatch, filename
):
    from quantide import data
    from quantide.service.factor_sources import _universe_version

    directory, _assets = source_environment
    monkeypatch.setattr(
        data,
        "get_index_weight_store",
        lambda: SimpleNamespace(_storage_signature=lambda: "fixed-index-version"),
    )
    path = directory / filename
    pl.DataFrame({"revision": [1]}).write_parquet(path)
    before = _universe_version()
    assert before is not None
    pl.DataFrame({"revision": [1, 2]}).write_parquet(path)
    after = _universe_version()
    assert after != before, f"tracking must invalidate amended {filename} even with the same assets"


def test_ai_study_summary_keeps_compact_universe_diagnostics(source_environment):
    from quantide.service.ai_factor_tools import _study_summary

    _data, _assets = source_environment
    config = {"exclude_st": True, "min_listing_days": 0, "max_universe_size": None}
    study = factor_study.run_custom_study(
        "bias_5", _DAYS[0], _DAYS[-1], [1], universe_filter=config
    )
    summary = _study_summary(study.as_dict())
    assert summary["universe_filter"]["min_listing_days"] == 0
    assert summary["universe"]["dates"] == len(_DAYS)
    assert "st_history_unavailable" in summary["universe"]["warnings"]
    assert summary["universe"]["effective_rows"] > 0
    assert "by_date" not in summary["universe"]

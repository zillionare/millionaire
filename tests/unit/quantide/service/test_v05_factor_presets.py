"""Factor preset, ablation lock and CLI payload contracts for WP-3."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from quantide.service import factor_presets, research_cli, research_backtest
from quantide.service.factor_presets import (
    delete_preset,
    load_preset,
    save_preset,
    validate_preset,
)
from quantide.service.research_backtest import AblationStudySpec, run_ablation


@pytest.fixture
def preset_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(factor_presets, "ensure_app_config_dir", lambda: tmp_path)
    return tmp_path


def test_preset_roundtrip_keeps_stable_hash_and_atomic_payload(preset_home: Path) -> None:
    first = save_preset(
        "demo_preset",
        "Demo",
        ["ma20_slope", "bias_5"],
        label_kind="cs_rank",
        strategy_params={"top_k": 10},
    )
    second = save_preset(
        "demo_preset",
        "Demo",
        ["ma20_slope", "bias_5"],
        label_kind="cs_rank",
        strategy_params={"top_k": 10},
    )

    loaded = load_preset("demo_preset")
    assert loaded.features == ("ma20_slope", "bias_5")
    assert loaded.label_kind == "cs_rank"
    assert loaded.strategy_params == {"top_k": 10}
    assert loaded.preset_hash == first.preset_hash == second.preset_hash
    assert (preset_home / "presets" / "demo_preset.json").is_file()
    assert delete_preset("demo_preset") is True
    assert delete_preset("demo_preset") is False
    with pytest.raises(KeyError, match="预设不存在"):
        load_preset("demo_preset")


def test_preset_rejects_missing_factor(preset_home: Path) -> None:
    with pytest.raises(ValueError, match="缺失因子"):
        save_preset("bad_preset", "Bad", ["not_a_real_factor"])


def test_preset_rejects_wind_tunnel_fail(
    preset_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        factor_presets,
        "factor_wind_tunnel_badge",
        lambda _factor_id: SimpleNamespace(badge_status="FAIL"),
    )
    with pytest.raises(ValueError, match="风洞 FAIL"):
        save_preset("bad_preset", "Bad", ["ma20_slope"])


def test_preset_rejects_unknown_label_kind(preset_home: Path) -> None:
    with pytest.raises(ValueError, match="label_kind"):
        save_preset("bad_preset", "Bad", ["ma20_slope"], label_kind="oops")


def test_preset_tampered_hash_is_rejected(preset_home: Path) -> None:
    save_preset("demo_preset", "Demo", ["ma20_slope"])
    path = preset_home / "presets" / "demo_preset.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["name"] = "Tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="指纹不匹配"):
        load_preset("demo_preset")


def test_validate_preset_rejects_strategy_interval_mismatch(preset_home: Path) -> None:
    preset = save_preset("demo_preset", "Demo", ["ma20_slope"])
    mismatch = factor_presets.FactorPreset(
        preset_id=preset.preset_id,
        name=preset.name,
        description=preset.description,
        strategy_id=preset.strategy_id,
        bar_interval="30m",
        features=preset.features,
        label_kind=preset.label_kind,
        strategy_params=preset.strategy_params,
    )
    with pytest.raises(ValueError, match="周期"):
        validate_preset(mismatch)


def test_ablation_locks_all_shared_conditions(
    preset_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_preset("baseline", "Baseline", ["ma20_slope"], label_kind="raw_return")
    save_preset("variant", "Variant", ["ma20_slope", "bias_5"], label_kind="cs_rank")
    calls: list[dict[str, Any]] = []

    def fake_run(strategy_id: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"strategy_id": strategy_id, **kwargs})
        annual = 0.10 if kwargs["preset"].preset_id == "baseline" else 0.13
        return {
            "portfolio_id": kwargs["preset"].preset_id,
            "preset_id": kwargs["preset"].preset_id,
            "metrics": {
                "annual_return": annual,
                "max_drawdown": -0.20 if annual == 0.10 else -0.15,
                "sharpe": 1.0,
                "calmar": 0.5,
            },
            "turnover": 2.0,
            "total_fees": 100.0,
            "equity_curve": [{"date": "2024-01-02", "total": 1.0}],
            "shap_top_features": [],
        }

    monkeypatch.setattr(research_backtest, "run_single_backtest", fake_run)
    spec = AblationStudySpec(
        baseline_preset_id="baseline",
        variant_preset_ids=("variant",),
        start=dt.date(2024, 1, 2),
        end=dt.date(2024, 12, 31),
        principal=2_000_000.0,
        commission=0.0002,
        stamp_tax=0.0006,
        transfer_fee=0.00002,
        min_commission=6.0,
        seed=7,
        universe_filter={"exclude_st": True, "min_listing_days": 60},
    )

    report = run_ablation(spec)

    assert len(calls) == 2
    first, second = calls
    assert first["start"] == second["start"] == spec.start
    assert first["end"] == second["end"] == spec.end
    assert first["initial_cash"] == second["initial_cash"] == 2_000_000.0
    assert first["fixed"] == second["fixed"] == spec.fixed_config()
    assert first["fixed"]["commission"] == 0.0002
    assert first["fixed"]["stamp_duty"] == 0.0006
    assert first["fixed"]["seed"] == 7
    assert first["fixed"]["universe_filter"]["min_listing_days"] == 60
    variant = report["variants"][0]
    assert variant["annual_excess"] == pytest.approx(0.03)
    assert variant["max_drawdown_delta"] == pytest.approx(0.05)


def test_cli_preset_payloads_use_the_same_validation(
    preset_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = research_cli.preset_save_payload(
        "cli_preset", "CLI", ["ma20_slope"], params={"top_k": 12}
    )
    listed = research_cli.preset_list_payload()

    assert saved["preset_id"] == "cli_preset"
    assert listed["presets"][0]["preset_id"] == "cli_preset"
    assert listed["presets"][0]["strategy_params"] == {"top_k": 12}


def test_ablation_spec_rejects_duplicate_or_too_many_variants() -> None:
    day = dt.date(2024, 1, 2)
    with pytest.raises(ValueError, match="1~5"):
        AblationStudySpec("baseline", (), day, day)
    with pytest.raises(ValueError, match="不能重复"):
        AblationStudySpec("baseline", ("variant", "variant"), day, day)
    with pytest.raises(ValueError, match="Baseline"):
        AblationStudySpec("baseline", ("baseline",), day, day)
    with pytest.raises(ValueError, match="开始日期"):
        AblationStudySpec("baseline", ("variant",), day, day - dt.timedelta(days=1))


def test_shap_summary_averages_absolute_contributions_across_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import polars as pl

    trades = pl.DataFrame(
        {
            "asset": ["A", "A", "B"],
            "tm": [
                dt.datetime(2024, 1, 3, 10, 0),
                dt.datetime(2024, 1, 3, 10, 0),
                dt.datetime(2024, 1, 4, 10, 0),
            ],
        }
    )
    explanations = {
        "A": {"features": [{"name": "x", "total": 3.0}, {"name": "y", "total": -1.0}]},
        "B": {"features": [{"name": "x", "total": 1.0}, {"name": "z", "total": 5.0}]},
    }
    monkeypatch.setattr(research_backtest.db, "trades_all", lambda _run_id: trades)
    monkeypatch.setattr(
        research_backtest,
        "explain_prediction",
        lambda _run_id, asset, _date, **_kwargs: explanations[asset],
    )

    features, diagnostics = research_backtest._shap_top_features(
        "run", dt.date(2024, 1, 3), dt.date(2024, 1, 4)
    )

    assert diagnostics == []
    by_name = {item["feature"]: item for item in features}
    assert by_name["x"]["mean_abs_shap"] == pytest.approx(2.0)
    assert by_name["z"]["share"] == pytest.approx(0.5)
    assert by_name["y"]["share"] == pytest.approx(0.1)


def test_shap_summary_is_diagnostic_when_no_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import polars as pl

    monkeypatch.setattr(research_backtest.db, "trades_all", lambda _run_id: pl.DataFrame())
    features, diagnostics = research_backtest._shap_top_features(
        "run", dt.date(2024, 1, 3), dt.date(2024, 1, 4)
    )
    assert features == []
    assert diagnostics == ["shap_unavailable"]


def test_ablation_variant_shap_keeps_only_changed_features() -> None:
    baseline = {
        "features": ["ma20_slope", "bias_5"],
        "shap_top_features": [
            {"feature": "ma20_slope", "share": 0.4},
            {"feature": "bias_5", "share": 0.2},
            {"feature": "new_factor", "share": 0.4},
        ],
    }
    variant = {
        "features": ["ma20_slope", "bias_5", "new_factor"],
        "shap_top_features": baseline["shap_top_features"],
    }

    assert research_backtest._variant_shap(baseline, variant) == [
        {"feature": "new_factor", "share": 0.4}
    ]


def test_shap_summary_falls_back_to_strategy_class_without_loader_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import polars as pl

    class FakeStrategy:
        ATTRIBUTION = "shap"

        def __init__(self, _broker: Any, _config: dict[str, Any]) -> None:
            pass

        def explain_prediction(
            self,
            _asset: str,
            _signal_date: dt.date,
            _bt_start: dt.date | None,
            _bt_end: dt.date | None,
        ) -> dict[str, Any]:
            return {"features": [{"name": "new_factor", "total": 2.0}]}

    trades = pl.DataFrame(
        {"asset": ["A"], "tm": [dt.datetime(2024, 1, 3, 10, 0)]}
    )
    monkeypatch.setattr(research_backtest.db, "trades_all", lambda _run_id: trades)
    monkeypatch.setattr(research_backtest, "explain_prediction", lambda *_a, **_k: None)

    features, diagnostics = research_backtest._shap_top_features(
        "run",
        dt.date(2024, 1, 3),
        dt.date(2024, 1, 4),
        FakeStrategy,
        {"features": ["new_factor"]},
    )

    assert diagnostics == []
    assert features == [
        {"feature": "new_factor", "name": "new_factor", "mean_abs_shap": 2.0, "share": 1.0}
    ]

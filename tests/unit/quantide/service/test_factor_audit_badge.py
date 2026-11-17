"""Five-state wind-tunnel badge and persisted record contracts."""

from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path

import polars as pl
import pytest

from quantide.config.paths import set_app_config_dir_override
from quantide.factors import plugins
from quantide.service import factor_audit
from quantide.service.factor_wind_tunnel import run_factor_wind_tunnel


def _write(directory: Path, factor_id: str, expression: str = 'pl.col("close").shift(1).over("asset")') -> Path:
    path = directory / f"{factor_id}.py"
    path.write_text(
        textwrap.dedent(
            f"""
            import polars as pl
            from quantide.factors.plugins import FactorPlugin

            FACTOR_PLUGIN = FactorPlugin(
                factor_id="{factor_id}",
                display_name="test",
                compute=lambda panel: panel.select({expression}).to_series(),
                required_columns=("close",),
                warmup_bars=1,
            )
            """
        ),
        encoding="utf-8",
    )
    return path


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


def _cutoffs(frame: pl.DataFrame) -> tuple[dt.date, ...]:
    dates = sorted(frame["date"].unique().to_list())
    return (dates[10], dates[20], dates[30])


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch):
    previous = set_app_config_dir_override(tmp_path / "config")
    monkeypatch.setattr("quantide.config.settings.get_factor_dir", lambda: str(tmp_path))
    plugins.clear_plugin_cache()
    yield
    plugins.clear_plugin_cache()
    set_app_config_dir_override(previous)


def test_unverified_then_pass_then_stale_on_source_change(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path, "ai_badge")
    frame = _frame()

    assert factor_audit.factor_wind_tunnel_badge("ai_badge").badge_status == "UNVERIFIED"

    result = run_factor_wind_tunnel(
        "ai_badge", frame=frame, cutoffs=_cutoffs(frame), save=True
    )
    badge = factor_audit.factor_wind_tunnel_badge("ai_badge")

    assert result.status == "PASS"
    assert badge.badge_status == "PASS"
    assert badge.run_id == result.report.run_id
    assert badge.recorded_source_hash == result.report.spec.source_hash

    path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    plugins.clear_plugin_cache()

    assert factor_audit.factor_wind_tunnel_badge("ai_badge").badge_status == "STALE"


def test_bound_backtest_badge_uses_recorded_factor_version(
    tmp_path: Path, monkeypatch
) -> None:
    """历史回测徽章绑定审计时的因子版本，不随当前插件源码漂移。"""
    from quantide.service.strategy_runtime import strategy_runtime_manager

    path = _write(tmp_path, "ai_bound")
    frame = _frame()
    result = run_factor_wind_tunnel(
        "ai_bound", frame=frame, cutoffs=_cutoffs(frame), save=True
    )
    bound = result.report.spec.source_hash
    monkeypatch.setitem(
        strategy_runtime_manager._runtime_specs,
        "backtest:p-bound",
        {
            "feature_audit": {
                "features": ["ai_bound"],
                "factor_versions": {"ai_bound": bound},
                "audit_run_ids": {"ai_bound": result.report.run_id},
            }
        },
    )

    path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    plugins.clear_plugin_cache()

    assert factor_audit.factor_wind_tunnel_badge("ai_bound").badge_status == "STALE"
    bound_badge = factor_audit.factor_wind_tunnel_badge(
        "ai_bound", bound_source_hash=bound, bound_run_id=result.report.run_id
    )
    assert bound_badge.badge_status == "PASS"
    assert factor_audit.backtest_wind_tunnel_badge("p-bound").badge_status == "PASS"


def test_legacy_backtest_without_binding_is_stale(tmp_path: Path, monkeypatch) -> None:
    """缺少不可变身份旧记录不能沿用当前因子状态冒充历史证据。"""
    from quantide.service.strategy_runtime import strategy_runtime_manager

    _write(tmp_path, "ai_legacy")
    monkeypatch.setitem(
        strategy_runtime_manager._runtime_specs,
        "backtest:p-legacy",
        {"config": {"features": ["ai_legacy"]}},
    )

    badge = factor_audit.backtest_wind_tunnel_badge("p-legacy")

    assert badge.badge_status == "STALE"
    assert "不可变" in badge.message


def test_data_fingerprint_change_downgrades_pass_to_stale(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path, "ai_data")
    frame = _frame()
    run_factor_wind_tunnel("ai_data", frame=frame, cutoffs=_cutoffs(frame), save=True)
    assert factor_audit.factor_wind_tunnel_badge("ai_data").badge_status == "PASS"

    monkeypatch.setattr(factor_audit, "_data_signature", lambda: "changed-data")

    assert factor_audit.factor_wind_tunnel_badge("ai_data").badge_status == "STALE"


def test_failed_audit_keeps_fail_badge_and_first_difference(tmp_path: Path, monkeypatch) -> None:
    _write(
        tmp_path,
        "ai_bad_badge",
        'pl.col("close").shift(-1).over("asset")',
    )
    frame = _frame()

    result = run_factor_wind_tunnel(
        "ai_bad_badge", frame=frame, cutoffs=_cutoffs(frame), save=True
    )
    badge = factor_audit.factor_wind_tunnel_badge("ai_bad_badge")

    assert result.status == "FAIL"
    assert badge.badge_status == "FAIL"
    assert badge.first_difference_summary
    assert any(item["status"] == "FAIL" for item in badge.check_items)

    from quantide.factors.registry import resolve_feature_selection

    assert "ai_bad_badge" not in resolve_feature_selection(None)
    with pytest.raises(ValueError, match="风洞 FAIL"):
        resolve_feature_selection(["ai_bad_badge"])


def test_bound_evidence_without_run_id_never_falls_back_to_latest(
    tmp_path: Path, monkeypatch
) -> None:
    from quantide.service.strategy_runtime import strategy_runtime_manager

    _write(tmp_path, "ai_no_run")
    frame = _frame()
    result = run_factor_wind_tunnel(
        "ai_no_run", frame=frame, cutoffs=_cutoffs(frame), save=True
    )
    bound = result.report.spec.source_hash
    monkeypatch.setitem(
        strategy_runtime_manager._runtime_specs,
        "backtest:p-no-run",
        {
            "feature_audit": {
                "features": ["ai_no_run"],
                "factor_versions": {"ai_no_run": bound},
                "audit_run_ids": {},
            }
        },
    )

    badge = factor_audit.backtest_wind_tunnel_badge("p-no-run")

    assert badge.badge_status == "UNVERIFIED"
    assert badge.run_id is None


def test_reaudit_same_source_does_not_rewrite_frozen_binding(tmp_path: Path, monkeypatch) -> None:
    from quantide.service.strategy_runtime import strategy_runtime_manager

    _write(tmp_path, "ai_frozen")
    frame = _frame()
    first = run_factor_wind_tunnel(
        "ai_frozen", frame=frame, cutoffs=_cutoffs(frame), save=True
    )
    binding = {
        "features": ["ai_frozen"],
        "factor_versions": {"ai_frozen": first.report.spec.source_hash},
        "audit_run_ids": {"ai_frozen": first.report.run_id},
    }
    monkeypatch.setitem(
        strategy_runtime_manager._runtime_specs,
        "backtest:p-frozen",
        {"feature_audit": dict(binding)},
    )
    run_factor_wind_tunnel(
        "ai_frozen",
        frame=frame.filter(pl.col("date") <= frame["date"].unique().sort()[20]),
        cutoffs=_cutoffs(frame),
        save=True,
    )

    assert factor_audit.bind_backtest_audit_records("p-frozen") == binding
    assert factor_audit.backtest_wind_tunnel_badge("p-frozen").run_id == first.report.run_id


def test_experiment_freezes_audit_evidence_before_model_is_known(
    tmp_path: Path, monkeypatch
) -> None:
    from quantide.service import factor_audit
    from quantide.service.factor_wind_tunnel import run_factor_wind_tunnel
    from quantide.service.strategy_runtime import strategy_runtime_manager

    _write(tmp_path, "ai_pre_freeze")
    frame = _frame()
    result = run_factor_wind_tunnel(
        "ai_pre_freeze", frame=frame, cutoffs=_cutoffs(frame), save=True
    )
    config = {"features": ["ai_pre_freeze"]}
    start = frame["date"].min().isoformat()
    end = frame["date"].max().isoformat()
    monkeypatch.setattr(
        factor_audit, "_range_data_hash", lambda *_args: result.report.spec.data_hash
    )
    frozen = factor_audit.feature_audit_binding(
        config, "1d", start_date=start, end_date=end, run_id="bt:pre-freeze"
    )
    assert frozen["audit_run_ids"] == {"ai_pre_freeze": result.report.run_id}
    monkeypatch.setitem(
        strategy_runtime_manager._runtime_specs,
        "backtest:pre-freeze",
        {"feature_audit": dict(frozen)},
    )
    factor_audit.record_backtest_audit_binding(
        "pre-freeze", config, "1d", run_id="bt:pre-freeze", binding=frozen
    )
    factor_audit.record_backtest_audit_binding(
        "pre-freeze",
        config,
        "1d",
        run_id="bt:pre-freeze",
        model_ref="Demo/model-1",
        diagnostics={"universe": "ok"},
    )

    stored = factor_audit.backtest_audit_binding("pre-freeze")

    assert stored is not None
    assert stored["audit_run_ids"] == frozen["audit_run_ids"]
    assert stored["model_ref"] == "Demo/model-1"


def test_data_signature_tracks_minute_and_pit_dependency_revisions(tmp_path, monkeypatch):
    from quantide.service import factor_audit

    monkeypatch.setattr("quantide.config.settings.get_data_home", lambda: str(tmp_path))
    minute = tmp_path / "data/bars/minute30/partition_key_year=2024/part.parquet"
    minute.parent.mkdir(parents=True)
    minute.write_bytes(b"first")
    first = factor_audit._data_signature()
    minute.write_bytes(b"second")
    second = factor_audit._data_signature()
    status = tmp_path / "data/stock_status_pit.parquet"
    status.write_bytes(b"st-history")
    third = factor_audit._data_signature()

    assert first != second != third

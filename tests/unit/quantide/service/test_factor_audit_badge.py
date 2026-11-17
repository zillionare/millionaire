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

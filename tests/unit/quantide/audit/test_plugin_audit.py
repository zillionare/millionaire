"""Wind-tunnel audit for external factor plugins."""

from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path

import polars as pl
import pytest

from quantide.audit.models import AuditStatus
from quantide.audit.plugin_factor import audit_factor_plugin
from quantide.factors import plugins


@pytest.fixture(autouse=True)
def _clear_plugin_cache():
    plugins.clear_plugin_cache()
    yield
    plugins.clear_plugin_cache()


def _write_plugin(directory: Path, compute: str, factor_id: str = "ai_plugin") -> None:
    (directory / f"{factor_id}.py").write_text(
        textwrap.dedent(
            f"""
            import polars as pl
            from quantide.factors.plugins import FactorPlugin

            FACTOR_PLUGIN = FactorPlugin(
                factor_id="{factor_id}",
                display_name="AI plugin",
                compute={compute},
                required_columns=("close",),
                warmup_bars=1,
                formula="test",
                principle="test",
            )
            """
        ),
        encoding="utf-8",
    )


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


def _plugin(tmp_path: Path, compute: str):
    _write_plugin(tmp_path, compute)
    return plugins.discover_factor_plugins(tmp_path).plugins[0]


def test_good_plugin_passes_wind_tunnel(tmp_path: Path) -> None:
    plugin = _plugin(
        tmp_path, 'lambda panel: panel.select(pl.col("close").shift(1).over("asset")).to_series()'
    )
    frame = _frame()

    report = audit_factor_plugin(plugin, frame, cutoffs=_cutoffs(frame))

    assert report.status is AuditStatus.PASS
    assert all(
        check.status in {AuditStatus.PASS, AuditStatus.NOT_APPLICABLE} for check in report.checks
    )


def test_missing_over_asset_fails_cross_section_isolation(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, 'lambda panel: panel.select(pl.col("close").shift(1)).to_series()')
    frame = _frame()

    report = audit_factor_plugin(plugin, frame, cutoffs=_cutoffs(frame))

    assert report.status is AuditStatus.FAIL
    failed = next(
        check
        for check in report.checks
        if check.status is AuditStatus.FAIL and check.check_id == "plugin.cross_section_isolation"
    )
    assert failed.first_difference is not None


def test_future_shift_fails_future_invariance(tmp_path: Path) -> None:
    plugin = _plugin(
        tmp_path, 'lambda panel: panel.select(pl.col("close").shift(-1).over("asset")).to_series()'
    )
    frame = _frame()

    report = audit_factor_plugin(plugin, frame, cutoffs=_cutoffs(frame))

    assert report.status is AuditStatus.FAIL
    failed = next(
        check
        for check in report.checks
        if check.status is AuditStatus.FAIL and check.check_id == "plugin.future_invariance"
    )
    assert failed.first_difference is not None
    assert failed.first_difference.kind == "future_dependency"


def test_stateful_global_cache_cannot_hide_future_dependency(tmp_path: Path) -> None:
    plugin_path = tmp_path / "ai_plugin.py"
    plugin_path.write_text(
        textwrap.dedent(
            """
            import polars as pl
            from quantide.factors.plugins import FactorPlugin

            _STATE = {"mean": None}

            def _compute(panel):
                if _STATE["mean"] is None:
                    _STATE["mean"] = float(panel["close"].mean())
                return panel["close"] / _STATE["mean"]

            FACTOR_PLUGIN = FactorPlugin(
                factor_id="ai_plugin",
                display_name="AI plugin",
                compute=_compute,
                required_columns=("close",),
                warmup_bars=0,
                formula="test",
                principle="test",
            )
            """
        ),
        encoding="utf-8",
    )
    plugins.clear_plugin_cache()
    plugin = plugins.discover_factor_plugins(tmp_path).plugins[0]
    frame = _frame()

    report = audit_factor_plugin(plugin, frame, cutoffs=_cutoffs(frame))

    assert report.status is AuditStatus.FAIL
    check = next(item for item in report.checks if item.check_id == "plugin.future_invariance")
    assert check.status is AuditStatus.FAIL
    assert check.details["executed_branches"] == ["cold", "warm"]


def test_source_less_plugin_cannot_claim_cold_warm_evidence(tmp_path: Path) -> None:
    def _compute(panel: pl.DataFrame) -> pl.Series:
        return panel.select(pl.col("close").shift(1).over("asset")).to_series()

    plugin = plugins.FactorPlugin(
        factor_id="ai_source_less",
        display_name="source-less",
        compute=_compute,
        required_columns=("close",),
        warmup_bars=1,
    )
    frame = _frame()

    report = audit_factor_plugin(plugin, frame, cutoffs=_cutoffs(frame))

    check = next(item for item in report.checks if item.check_id == "plugin.future_invariance")
    assert check.status is AuditStatus.INCONCLUSIVE
    assert check.details["executed_branches"] == ["cold"]
    assert check.details["warm_branch"] == "unavailable"


def test_contract_rejects_non_finite_values(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, 'lambda panel: panel["close"] / (panel["close"] - panel["close"])')
    frame = _frame()

    report = audit_factor_plugin(plugin, frame, cutoffs=_cutoffs(frame))

    assert report.status is AuditStatus.FAIL
    assert report.checks[0].check_id == "plugin.contract"


def test_warmup_window_must_be_null(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, 'lambda panel: panel["close"]')
    frame = _frame()

    report = audit_factor_plugin(plugin, frame, cutoffs=_cutoffs(frame))

    contract = next(check for check in report.checks if check.check_id == "plugin.contract")
    assert contract.status is AuditStatus.FAIL
    assert contract.first_difference is not None
    assert contract.first_difference.kind == "warmup_violation"

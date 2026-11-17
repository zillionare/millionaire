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

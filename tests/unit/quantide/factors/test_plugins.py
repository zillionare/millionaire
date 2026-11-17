"""External factor plugin discovery and computation contracts."""

from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path

import polars as pl
import pytest

from quantide.factors import plugins
from quantide.factors.registry import compute_feature_panel, feature_groups
from quantide.service.backtest_params import default_backtest_params


@pytest.fixture(autouse=True)
def _clear_plugin_cache():
    plugins.clear_plugin_cache()
    yield
    plugins.clear_plugin_cache()


def _write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _valid_plugin(factor_id: str = "ai_close_open") -> str:
    return f"""
from quantide.factors.plugins import FactorPlugin

FACTOR_PLUGIN = FactorPlugin(
    factor_id="{factor_id}",
    display_name="AI close/open",
    compute=lambda panel: panel["close"] / panel["open"],
    required_columns=("open", "close"),
    formula="close / open",
    principle="demonstration plugin",
    example="close/open",
)
"""


def test_discovers_valid_plugin_and_source_hash(tmp_path: Path) -> None:
    _write(tmp_path, "ai_close_open.py", _valid_plugin())

    result = plugins.discover_factor_plugins(tmp_path)

    assert result.plugins[0].factor_id == "ai_close_open"
    assert result.plugins[0].source_hash
    assert result.skipped == ()


def test_bad_files_are_isolated_with_structured_reasons(tmp_path: Path) -> None:
    _write(tmp_path, "valid.py", _valid_plugin())
    _write(tmp_path, "syntax.py", "def broken(:\n    pass\n")
    _write(tmp_path, "missing.py", "VALUE = 1\n")
    _write(tmp_path, "builtin.py", _valid_plugin("ma20_slope"))
    _write(tmp_path, "dupe_a.py", _valid_plugin("ai_dupe"))
    _write(tmp_path, "dupe_b.py", _valid_plugin("ai_dupe"))

    result = plugins.discover_factor_plugins(tmp_path)

    assert sorted(plugin.factor_id for plugin in result.plugins) == ["ai_close_open", "ai_dupe"]
    reasons = {Path(item.file_path).name: item.reason for item in result.skipped}
    assert reasons["syntax.py"] is plugins.SkippedFactorReason.SYNTAX_ERROR
    assert reasons["missing.py"] is plugins.SkippedFactorReason.MISSING_PLUGIN_DECLARATION
    assert reasons["builtin.py"] is plugins.SkippedFactorReason.BUILTIN_ID_CONFLICT
    assert reasons["dupe_b.py"] is plugins.SkippedFactorReason.DUPLICATE_PLUGIN_ID


def test_source_checkout_directory_is_rejected() -> None:
    result = plugins.discover_factor_plugins(Path.cwd() / "quantide")

    assert result.plugins == ()
    assert result.skipped[0].reason is plugins.SkippedFactorReason.SOURCE_CHECKOUT_REJECTED


def test_source_change_invalidates_cache_and_hash(tmp_path: Path) -> None:
    path = _write(tmp_path, "ai_close_open.py", _valid_plugin())
    first = plugins.discover_factor_plugins(tmp_path)

    _write(tmp_path, "ai_close_open.py", _valid_plugin() + "\n# changed\n")
    second = plugins.discover_factor_plugins(tmp_path)

    assert first.plugins[0].source_hash != second.plugins[0].source_hash
    assert path.exists()


def test_compute_applies_hfq_only_when_declared() -> None:
    plugin = plugins.FactorPlugin(
        factor_id="ai_close",
        display_name="AI close",
        compute=lambda panel: panel["close"],
        required_columns=("close",),
    )
    panel = pl.DataFrame(
        {
            "date": [dt.date(2025, 1, 2)],
            "asset": ["600001.SH"],
            "open": [5.0],
            "close": [10.0],
            "adjust": [2.0],
        }
    )

    computed = plugins.compute_plugin(panel, plugin)
    raw = plugins.compute_plugin(
        panel,
        plugins.FactorPlugin(
            factor_id=plugin.factor_id,
            display_name=plugin.display_name,
            compute=plugin.compute,
            required_columns=plugin.required_columns,
            price_adjustment="raw",
        ),
    )

    assert computed["ai_close"][0] == pytest.approx(20.0)
    assert raw["ai_close"][0] == pytest.approx(10.0)


def test_registry_merges_plugin_into_feature_panel(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path, "ai_close_open.py", _valid_plugin())
    monkeypatch.setattr("quantide.config.settings.get_factor_dir", lambda: str(tmp_path))
    plugins.clear_plugin_cache()
    panel = pl.DataFrame(
        {
            "date": [dt.date(2025, 1, 2)],
            "asset": ["600001.SH"],
            "open": [5.0],
            "high": [11.0],
            "low": [4.0],
            "close": [10.0],
            "volume": [100.0],
            "amount": [1000.0],
            "adjust": [1.0],
        }
    )

    result = compute_feature_panel(panel, ["ai_close_open"])

    assert "ai_close_open" in result.columns
    assert result["ai_close_open"][0] == pytest.approx(2.0)
    assert "自定义因子" in feature_groups()
    assert "ai_close_open" in default_backtest_params()["features"]


def test_compute_feature_panel_applies_adjust_once(tmp_path: Path, monkeypatch) -> None:
    _write(
        tmp_path,
        "ai_hfq_close.py",
        """
        from quantide.factors.plugins import FactorPlugin

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="ai_hfq_close",
            display_name="hfq close",
            compute=lambda panel: panel["close"],
            required_columns=("close",),
            price_adjustment="hfq",
        )
        """,
    )
    _write(
        tmp_path,
        "ai_raw_close.py",
        """
        from quantide.factors.plugins import FactorPlugin

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="ai_raw_close",
            display_name="raw close",
            compute=lambda panel: panel["close"],
            required_columns=("close",),
            price_adjustment="raw",
        )
        """,
    )
    monkeypatch.setattr("quantide.config.settings.get_factor_dir", lambda: str(tmp_path))
    plugins.clear_plugin_cache()
    start = dt.date(2025, 1, 2)
    rows = []
    for index in range(12):
        close = 10.0 + index
        rows.append(
            {
                "date": start + dt.timedelta(days=index),
                "asset": "600001.SH",
                "open": close - 0.5,
                "high": close + 0.5,
                "low": close - 0.8,
                "close": close,
                "volume": 1000.0,
                "amount": 10000.0,
                "adjust": 2.0,
            }
        )

    result = compute_feature_panel(pl.DataFrame(rows)).sort(["asset", "date"])

    assert result["ai_hfq_close"].to_list() == pytest.approx([row["close"] * 2.0 for row in rows])
    assert result["ai_raw_close"].to_list() == pytest.approx([row["close"] for row in rows])

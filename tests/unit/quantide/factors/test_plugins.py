"""External factor plugin discovery and computation contracts."""

from __future__ import annotations

import datetime as dt
import os
import py_compile
import textwrap
from pathlib import Path

import polars as pl
import pytest

from quantide.factors import plugins
from quantide.factors.registry import (
    compute_feature_panel,
    feature_groups,
    resolve_feature_selection,
)
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


def test_discovery_isolates_system_exit(tmp_path: Path) -> None:
    _write(tmp_path, "valid.py", _valid_plugin())
    _write(tmp_path, "exit.py", "raise SystemExit(7)\n")

    result = plugins.discover_factor_plugins(tmp_path)

    assert [plugin.factor_id for plugin in result.plugins] == ["ai_close_open"]
    skipped = {Path(item.file_path).name: item for item in result.skipped}
    assert skipped["exit.py"].reason is plugins.SkippedFactorReason.IMPORT_ERROR
    assert "SystemExit" in skipped["exit.py"].detail


def test_discovery_enforces_import_timeout(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path, "slow.py", "import time\ntime.sleep(30)\n")
    monkeypatch.setenv("QUANTIDE_FACTOR_PLUGIN_TIMEOUT", "0.5")

    result = plugins.discover_factor_plugins(tmp_path)

    assert result.plugins == ()
    assert result.skipped[0].reason is plugins.SkippedFactorReason.IMPORT_TIMEOUT


def test_source_checkout_directory_is_rejected() -> None:
    result = plugins.discover_factor_plugins(Path.cwd() / "quantide")

    assert result.plugins == ()
    assert result.skipped[0].reason is plugins.SkippedFactorReason.SOURCE_CHECKOUT_REJECTED


def test_interval_filtering_rejects_cross_period_factor(
    tmp_path: Path, monkeypatch
) -> None:
    _write(
        tmp_path,
        "ai_intraday.py",
        """
        from quantide.factors.plugins import FactorPlugin

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="ai_intraday",
            display_name="intraday",
            compute=lambda panel: panel["close"],
            required_columns=("close",),
            bar_interval="30m",
        )
        """,
    )

    monkeypatch.setattr("quantide.config.settings.get_factor_dir", lambda: str(tmp_path))
    plugins.clear_plugin_cache()
    discovery = plugins.discover_factor_plugins(tmp_path)
    assert "ai_intraday" in feature_groups("30m")["自定义因子"]
    intraday_ids = [name for names in feature_groups("30m").values() for name in names]
    assert "ma20_slope" not in intraday_ids
    assert resolve_feature_selection(["ai_intraday"], "30m") == ["ai_intraday"]
    with pytest.raises(ValueError, match="周期"):
        resolve_feature_selection(["ma20_slope"], "30m")
    assert discovery.plugins[0].bar_interval == "30m"


class _IntradayStrategy:
    BAR_INTERVAL = "30m"


def test_default_backtest_params_follow_strategy_interval() -> None:
    defaults = default_backtest_params(_IntradayStrategy)

    assert defaults["features"] == []


def test_hfq_plugin_cannot_request_reserved_adjust_column(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ai_bad_adjust.py",
        """
        from quantide.factors.plugins import FactorPlugin

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="ai_bad_adjust",
            display_name="bad",
            compute=lambda panel: panel["adjust"],
            required_columns=("adjust",),
            price_adjustment="hfq",
            warmup_bars=0,
        )
        """,
    )
    plugin = plugins.discover_factor_plugins(tmp_path).plugins[0]
    panel = pl.DataFrame(
        {
            "date": [dt.date(2025, 1, 2)],
            "asset": ["600001.SH"],
            "close": [10.0],
            "adjust": [2.0],
        }
    )

    with pytest.raises(plugins.PluginContractError, match="adjust"):
        plugins.compute_plugin(panel, plugin)


def test_compute_receives_adjusted_prices_without_adjust_column(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ai_adjust_aware.py",
        """
        from quantide.factors.plugins import FactorPlugin

        def _compute(panel):
            assert "adjust" not in panel.columns
            return panel["close"]

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="ai_adjust_aware",
            display_name="adjust aware",
            compute=_compute,
            required_columns=("close",),
            price_adjustment="hfq",
            warmup_bars=0,
        )
        """,
    )
    panel = pl.DataFrame(
        {
            "date": [dt.date(2025, 1, 2)],
            "asset": ["600001.SH"],
            "close": [10.0],
            "adjust": [2.0],
        }
    )

    plugin = plugins.discover_factor_plugins(tmp_path).plugins[0]
    computed = plugins.compute_plugin(panel, plugin)

    assert computed["ai_adjust_aware"][0] == pytest.approx(20.0)


def test_compute_rejects_partial_dataframe_keys(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ai_partial.py",
        """
        import polars as pl

        from quantide.factors.plugins import FactorPlugin

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="ai_partial",
            display_name="partial",
            compute=lambda panel: (
                panel.select("asset", "date")
                .head(1)
                .with_columns(pl.lit(1.0).alias("ai_partial"))
            ),
            required_columns=("close",),
            warmup_bars=0,
        )
        """,
    )
    panel = pl.DataFrame(
        {
            "date": [dt.date(2025, 1, 2), dt.date(2025, 1, 3)],
            "asset": ["600001.SH", "600001.SH"],
            "close": [10.0, 11.0],
        }
    )

    plugin = plugins.discover_factor_plugins(tmp_path).plugins[0]
    with pytest.raises(plugins.PluginContractError, match="行数"):
        plugins.compute_plugin(panel, plugin)


def test_verified_source_bytes_beat_stale_adjacent_pyc(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "ai_pyc.py",
        """
        import polars as pl
        from quantide.factors.plugins import FactorPlugin

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="ai_pyc",
            display_name="pyc",
            compute=lambda panel: panel["close"] * 1,
            required_columns=("close",),
            warmup_bars=0,
        )
        """,
    )
    py_compile.compile(str(path), doraise=True)
    before = plugins.load_factor_plugin(path)
    old_mtime = path.stat().st_mtime_ns
    path.write_text(path.read_text().replace("* 1", "* 2"), encoding="utf-8")
    os.utime(path, ns=(old_mtime, old_mtime))
    plugins.clear_plugin_cache()
    after = plugins.load_factor_plugin(path)
    frame = pl.DataFrame({"date": [dt.date(2025, 1, 2)], "asset": ["A"], "close": [10.0]})

    assert before.source_hash != after.source_hash
    assert plugins.compute_plugin(frame, after)["ai_pyc"][0] == pytest.approx(20.0)


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

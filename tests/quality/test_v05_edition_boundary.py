"""CE/pro boundary and open-extension checks for AC-5022 and AC-5023."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import polars as pl

from quantide.config.features import supports_live_trading
from quantide.factors.registry import FEATURE_COLS
from quantide.factors.universe import UniverseFilterConfig
from quantide.service.risk_programs import RiskProgramRegistry, risk_program_registry
from quantide.strategies.example.ml_momentum_reversal import MLMomentumReversalStrategy

ROOT = Path(__file__).resolve().parents[2]


class CeBoundaryTest(unittest.TestCase):
    def test_official_ce_surface_does_not_bundle_pro_only_controls(self) -> None:
        config = MLMomentumReversalStrategy.default_config()
        self.assertFalse({"hold_buffer", "buffer_k", "stop_loss", "take_profit"} & set(config))
        self.assertFalse({"pe_ttm", "pb", "turnover_rate", "industry"} & set(FEATURE_COLS))
        self.assertEqual(RiskProgramRegistry().list(), [])
        self.assertEqual(risk_program_registry.list(), [])
        universe = UniverseFilterConfig.from_mapping({}).as_dict()
        self.assertFalse({"industry", "industry_neutralize", "neutralize"} & set(universe))
        with patch("quantide.config.features.get_runtime_edition", lambda: "millionaire"):
            self.assertFalse(supports_live_trading())

    def test_daily_basic_fetch_keeps_official_capability_columns_only(self) -> None:
        import quantide.data.fetchers.tushare as tushare

        seen: list[str] = []

        class _Pro:
            @staticmethod
            def daily_basic(trade_date: str, fields: str) -> pd.DataFrame:
                seen.append(fields)
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ"],
                        "trade_date": [trade_date],
                        "total_mv": [100.0],
                        "circ_mv": [80.0],
                        "pe_ttm": [12.0],
                        "turnover_rate": [0.03],
                    }
                )

        with (
            patch.object(tushare, "_ensure_tushare_token", lambda: None),
            patch.object(tushare.ts, "pro_api", lambda: _Pro()),
        ):
            frame, errors = tushare.fetch_daily_basic(__import__("datetime").date(2024, 1, 2))
        self.assertEqual(seen, ["ts_code,trade_date,total_mv,circ_mv"])
        self.assertEqual(list(frame.columns), ["asset", "date", "total_mv", "circ_mv"])
        self.assertEqual(errors, [])


class OpenExtensionTest(unittest.TestCase):
    def test_external_panel_columns_are_not_blacklisted(self) -> None:
        from quantide.factors.plugins import compute_plugin, discover_factor_plugins

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "custom_valuation.py").write_text(
                "import polars as pl\n"
                "from quantide.factors.plugins import FactorPlugin\n"
                "def compute(frame):\n"
                "    return frame.with_columns(\n"
                "        (pl.col('turnover_rate') * pl.col('pe_ttm') + pl.col('industry').str.len_chars())\n"
                "        .alias('custom_valuation')\n"
                "    )\n"
                "FACTOR_PLUGIN = FactorPlugin(\n"
                "    factor_id='custom_valuation', display_name='Custom valuation',\n"
                "    group='user', required_columns=('turnover_rate', 'pe_ttm', 'industry'),\n"
                "    compute=compute,\n"
                ")\n",
                encoding="utf-8",
            )
            discovery = discover_factor_plugins(root)
            plugin = discovery.by_id("custom_valuation")
            self.assertIsNotNone(plugin)
            panel = pl.DataFrame(
                {
                    "date": [__import__("datetime").date(2024, 1, 2)],
                    "asset": ["000001.SZ"],
                    "turnover_rate": [0.03],
                    "pe_ttm": [12.0],
                    "industry": ["银行"],
                }
            )
            output = compute_plugin(panel, plugin)
            self.assertIn("custom_valuation", output.columns)
            self.assertIsNotNone(output["custom_valuation"][0])

    def test_custom_buffer_band_strategy_is_loaded_from_strategy_dir(self) -> None:
        from quantide.service.discovery import ScanSource, StrategyLoader

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "custom_buffer.py").write_text(
                "from quantide.core.strategy import BaseStrategy\n"
                "class BufferedStrategy(BaseStrategy):\n"
                "    BAR_INTERVAL = '1d'\n"
                "    hold_buffer = 4\n"
                "    buffer_k = 0.2\n"
                "    @staticmethod\n"
                "    def default_config():\n"
                "        return {'hold_buffer': 4, 'buffer_k': 0.2}\n",
                encoding="utf-8",
            )
            loader = StrategyLoader()
            try:
                scanned = loader._scan_source(ScanSource(root))
            finally:
                sys.modules.pop("custom_buffer", None)
            self.assertIn("BufferedStrategy", scanned)
            self.assertEqual(Path(scanned["BufferedStrategy"].scan_dir).resolve(), root.resolve())

    def test_custom_risk_extension_loads_from_user_directory(self) -> None:
        from quantide.providers import risk_extensions

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "risk-extensions.json").write_text('{"enabled": true}', encoding="utf-8")
            (root / "risk_extensions.py").write_text(
                "from quantide.service.risk_programs import RiskProgramAdapter\n"
                "def register_extensions(registry):\n"
                "    registry.register(RiskProgramAdapter(id='user.custom_cap', name='User cap'))\n",
                encoding="utf-8",
            )
            from quantide.service.risk_programs import RiskProgramAdapter

            registry = RiskProgramRegistry()
            registry.register(RiskProgramAdapter(id="host.sentinel"))
            with (
                patch.object(risk_extensions, "extension_directory", lambda: root),
                patch.object(risk_extensions, "_LOADED_IDS", set()),
            ):
                loaded = risk_extensions.load_risk_extensions(registry)
            self.assertEqual(loaded, ["user.custom_cap"])
            self.assertIsNotNone(registry.get("user.custom_cap"))


class ScopeControlTest(unittest.TestCase):
    def test_no_openapi_range_cli_was_added(self) -> None:
        from quantide import cli

        for name in ("openapi", "protocol-range", "target-range", "alert-link"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                cli.main([name])

    def test_no_alert_linkage_or_range_ui_modules_were_added(self) -> None:
        forbidden = (
            "openapi_range",
            "protocol_range",
            "target_range",
            "alert_automation",
            "send_test_alert",
            "dingtalk_alert",
            "email_alert",
        )
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in ROOT.joinpath("quantide").rglob("*.py")
        )
        for token in forbidden:
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()

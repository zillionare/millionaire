"""AI research CLI envelope, exit codes and factor template contracts."""

from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import polars as pl
import pytest

import quantide.cli as cli
from quantide.config.paths import set_app_config_dir_override
from quantide.factors import plugins
from quantide.service import research_cli
from quantide.service.factor_wind_tunnel import run_factor_wind_tunnel


def _plugin(directory: Path, factor_id: str, expression: str) -> Path:
    path = directory / f"{factor_id}.py"
    path.write_text(
        f"""
import polars as pl
from quantide.factors.plugins import FactorPlugin

FACTOR_PLUGIN = FactorPlugin(
    factor_id="{factor_id}",
    display_name="cli test",
    compute=lambda panel: panel.select({expression}).to_series(),
    required_columns=("close",),
    warmup_bars=1,
)
""",
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


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch):
    previous = set_app_config_dir_override(tmp_path / "config")
    monkeypatch.setattr("quantide.config.settings.get_factor_dir", lambda: str(tmp_path))
    plugins.clear_plugin_cache()
    yield
    plugins.clear_plugin_cache()
    set_app_config_dir_override(previous)


def test_factor_init_writes_template_and_lists_it(tmp_path: Path, capsys) -> None:
    assert cli.main(["factor", "init", "ai_cli_factor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "factor.init"
    assert payload["data"]["source_hash"]
    assert Path(payload["data"]["path"]).is_file()

    assert cli.main(["factor", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    factors = {item["factor_id"]: item for item in listed["data"]["factors"]}
    assert factors["ai_cli_factor"]["source"] == "external"
    assert factors["ai_cli_factor"]["wind_tunnel_status"] == "UNVERIFIED"


def test_generated_template_passes_wind_tunnel(tmp_path: Path, capsys) -> None:
    assert cli.main(["factor", "init", "ai_template_factor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    frame = _frame().sort(["asset", "date"])
    dates = sorted(frame["date"].unique().to_list())

    result = run_factor_wind_tunnel(
        "ai_template_factor",
        frame=frame,
        cutoffs=(dates[10], dates[20], dates[30]),
        save=False,
    )

    assert Path(payload["data"]["path"]).is_file()
    assert result.status == "PASS"


def test_factor_init_rejects_builtin_id(tmp_path: Path, capsys) -> None:
    assert cli.main(["factor", "init", "ma20_slope", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["exit_code"] == 2


def test_factor_check_passes_and_returns_standard_json(tmp_path: Path, monkeypatch, capsys) -> None:
    path = _plugin(tmp_path, "ai_cli_good", 'pl.col("close").shift(1).over("asset")')
    frame = _frame()
    dates = sorted(frame["date"].unique().to_list())
    monkeypatch.setattr(research_cli, "load_wind_tunnel_frame", lambda start, end: frame)
    monkeypatch.setattr(research_cli, "_bar_dates", lambda: dates)

    assert cli.main(["factor", "check", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "PASS"
    assert payload["fingerprints"]["source_hash"]
    assert "NaN" not in json.dumps(payload, ensure_ascii=False)


def test_factor_check_returns_three_for_future_leak(tmp_path: Path, monkeypatch, capsys) -> None:
    path = _plugin(tmp_path, "ai_cli_bad", 'pl.col("close").shift(-1).over("asset")')
    frame = _frame()
    dates = sorted(frame["date"].unique().to_list())
    monkeypatch.setattr(research_cli, "load_wind_tunnel_frame", lambda start, end: frame)
    monkeypatch.setattr(research_cli, "_bar_dates", lambda: dates)

    assert cli.main(["factor", "check", str(path), "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "FAIL"
    assert any(item["first_difference"] for item in payload["diagnostics"])


def test_factor_check_missing_target_is_contract_error(capsys) -> None:
    assert cli.main(["factor", "check", "does_not_exist", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ERROR"
    assert payload["diagnostics"][0]["code"] == "INVALID_REQUEST"


def test_preset_cli_save_and_list_use_research_envelope(capsys) -> None:
    assert (
        cli.main(
            [
                "preset",
                "save",
                "--id",
                "cli_preset",
                "--name",
                "CLI Preset",
                "--features",
                "ma20_slope,bias_5",
                "--label-kind",
                "cs_rank",
                "--params",
                '{"top_k": 12}',
                "--json",
            ]
        )
        == 0
    )
    saved = json.loads(capsys.readouterr().out)
    assert saved["command"] == "preset.save"
    assert saved["data"]["preset_id"] == "cli_preset"
    assert saved["data"]["label_kind"] == "cs_rank"
    assert saved["data"]["preset_hash"]

    assert cli.main(["preset", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["command"] == "preset.list"
    assert listed["data"]["presets"][0]["preset_id"] == "cli_preset"


def test_backtest_cli_rejects_ablation_without_preset(capsys) -> None:
    assert (
        cli.main(
            [
                "backtest",
                "run",
                "--strategy",
                "MLMomentumReversalStrategy",
                "--ablation-vs",
                "base",
                "--start",
                "2024-01-02",
                "--end",
                "2024-01-31",
                "--json",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "INVALID_REQUEST"


def test_backtest_cli_serializes_isolated_run_payload(monkeypatch, capsys) -> None:
    from quantide.service import research_backtest

    def fake_run(strategy_id: str, **kwargs) -> dict[str, object]:
        return {
            "portfolio_id": "research-run",
            "strategy_id": strategy_id,
            "preset_id": None,
            "start": kwargs["start"].isoformat(),
            "end": kwargs["end"].isoformat(),
            "initial_cash": kwargs["initial_cash"],
            "config": {},
            "features": [],
            "metrics": {"annual_return": 0.1},
            "turnover": 1.0,
            "total_fees": 10.0,
            "trade_count": 1,
            "equity_curve": [],
            "shap_top_features": [],
            "diagnostics": ["shap_unavailable"],
        }

    monkeypatch.setattr(research_backtest, "run_single_backtest", fake_run)
    assert (
        cli.main(
            [
                "backtest",
                "run",
                "--strategy",
                "MLMomentumReversalStrategy",
                "--params",
                "{}",
                "--start",
                "2024-01-02",
                "--end",
                "2024-01-31",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "backtest.run"
    assert payload["data"]["portfolio_id"] == "research-run"
    assert payload["data"]["start"] == "2024-01-02"
    assert payload["data"]["diagnostics"] == ["shap_unavailable"]


def test_json_cli_survives_cp1252_pipe_with_non_bmp_roundtrip(monkeypatch) -> None:
    payload = research_cli.envelope(
        "factor.check",
        ok=False,
        status="FAIL",
        exit_code=3,
        diagnostics=[{"code": "FUTURE_DATA_LEAK", "message": "中文诊断 🚀🧪"}],
    )
    legacy = research_cli.envelope_json(payload)
    assert not legacy.isascii()
    with pytest.raises(UnicodeEncodeError):
        io.TextIOWrapper(io.BytesIO(), encoding="cp1252").write(legacy)
    with pytest.raises(ValueError):
        research_cli.envelope_json({"bad": float("nan")}, ensure_ascii=True)

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", stream)
    cli._emit(payload, True)
    stream.flush()

    encoded = raw.getvalue()
    assert encoded
    assert encoded.isascii()
    assert json.loads(encoded.decode("ascii")) == payload

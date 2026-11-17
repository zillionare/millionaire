"""Real child-process research CLI closure used by the official Agent Skill."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from quantide.config.paths import get_app_db_path, set_app_config_dir_override
from quantide.config.settings import get_factor_dir
from quantide.core.enums import BidType, OrderSide, OrderStatus
from quantide.core.market_time import market_now
from quantide.data.models import Asset, Order, Position, Trade
from quantide.data.sqlite import db
from quantide.factors.registry import catalog_version
from quantide.service.demo_bundle import activate_demo_bundle
from quantide.service.factor_presets import FactorPreset, load_preset
from quantide.service.init_wizard import init_wizard
from quantide.service.model_store import ModelArtifact, ModelStore
from quantide.service.research_backtest import _config_for
from quantide.service.sim_broker import PaperBroker
from quantide.service.strategy_tracking import tracking_store
from quantide.strategies.example.ml_momentum_reversal import (
    PIPELINE_VERSION,
    MLMomentumReversalStrategy,
)

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]

_PAPER_ID = "phaseb-paper"
_RUNTIME_ID = "paper:phaseb-cli"
_FAKE_KEY = "sk-phaseb-secret-9000"
_FACT_TABLES = (
    "portfolios",
    "orders",
    "trades",
    "positions",
    "assets",
    "strategy_tracking_runs",
    "strategy_tracking_daily",
    "strategy_tracking_bars",
    "strategy_shadow_state",
)


def _table_rows(
    connection: sqlite3.Connection, table: str, portfolio_id: str
) -> list[dict[str, object]]:
    connection.row_factory = sqlite3.Row
    columns = {
        str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    }
    if "portfolio_id" not in columns:
        return []
    rows = connection.execute(
        f'SELECT * FROM "{table}" WHERE portfolio_id = ? ORDER BY rowid',
        (portfolio_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _paper_facts(path: Path, portfolio_id: str) -> dict[str, list[dict[str, object]]]:
    if not path.is_file():
        return {}
    connection = sqlite3.connect(path)
    try:
        return {
            table: _table_rows(connection, table, portfolio_id)
            for table in _FACT_TABLES
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        }
    finally:
        connection.close()


def _model_state(root: Path, key: str) -> dict[str, object]:
    latest_json = root / key / "latest.json"
    latest_pickle = root / key / "latest.pkl"
    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    return {
        "metadata": payload,
        "latest_sha256": hashlib.sha256(latest_pickle.read_bytes()).hexdigest(),
        "model_ref": str((payload.get("extra") or {}).get("model_ref") or ""),
    }


def _run(env: dict[str, str], *args: str) -> tuple[int, dict[str, object]]:
    completed = subprocess.run(
        [sys.executable, env["CLI_RUNNER"], *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )
    stdout = completed.stdout.strip()
    streams = stdout + completed.stderr
    assert "NaN" not in streams and "Infinity" not in streams, completed.stderr[-1000:]
    assert _FAKE_KEY not in streams
    assert stdout, completed.stderr[-2000:]
    return completed.returncode, json.loads(stdout)


def _seed_model(preset: FactorPreset) -> tuple[str, dict[str, object]]:
    baseline_config = _config_for("MLMomentumReversalStrategy", preset, None)
    strategy = MLMomentumReversalStrategy(None, baseline_config)
    key = strategy._model_key
    expected = MLMomentumReversalStrategy(
        None,
        {
            **MLMomentumReversalStrategy.default_config(),
            "features": ["ma20_slope", "bias_5"],
            "factor_catalog_version": catalog_version(),
            "pipeline_version": PIPELINE_VERSION,
            "symbols": None,
        },
    )._model_key
    assert key == expected
    store = ModelStore()
    artifact = store.save(
        key=key,
        model={"phaseb": "running-model"},
        metadata=ModelArtifact(
            model_key=key,
            strategy_name="MLMomentumReversalStrategy",
            config_hash="phaseb-config",
            train_end="2024-12-31",
            effective_from="2024-12-31",
            pipeline_version=PIPELINE_VERSION,
            metrics={"rank_ic": 0.02},
        ),
    )
    return key, artifact.to_dict()


def _seed_paper(day: dt.date, model_ref: str, model_hash: str) -> None:
    broker = PaperBroker.create(
        _PAPER_ID,
        principal=250_000,
        portfolio_name="Phase B Paper",
        info="real CLI isolation account",
    )
    try:
        asset = "000001.SZ"
        filled = Order(
            portfolio_id=_PAPER_ID,
            asset=asset,
            side=OrderSide.BUY,
            shares=1_000,
            bid_type=BidType.FIXED,
            price=10.0,
            filled=1_000,
            status=OrderStatus.SUCCEEDED,
            tm=dt.datetime.combine(day, dt.time(10, 0)),
        )
        db.insert_order(filled)
        db.insert_trades(
            Trade(
                portfolio_id=_PAPER_ID,
                tid="phaseb-trade-1",
                qtoid=filled.qtoid,
                foid="phaseb-fill-1",
                asset=asset,
                shares=1_000,
                price=10.0,
                amount=10_000.0,
                tm=dt.datetime.combine(day, dt.time(10, 0)),
                side=OrderSide.BUY,
                cid="phaseb-cid-1",
                fee=5.0,
            )
        )
        db.insert_order(
            Order(
                portfolio_id=_PAPER_ID,
                asset=asset,
                side=OrderSide.BUY,
                shares=500,
                bid_type=BidType.FIXED,
                price=9.2,
                status=OrderStatus.REPORTED,
                tm=dt.datetime.combine(day, dt.time(10, 5)),
            )
        )
        db.upsert_positions(
            Position(
                portfolio_id=_PAPER_ID,
                dt=day,
                asset=asset,
                shares=1_000,
                avail=800,
                price=10.0,
                profit=0.12,
                mv=12_000.0,
            )
        )
        db.upsert_asset(
            Asset(
                portfolio_id=_PAPER_ID,
                dt=day,
                principal=250_000,
                cash=237_995.0,
                frozen_cash=4_600.0,
                market_value=12_000.0,
                total=249_995.0,
            )
        )
    finally:
        broker.close()
    positions = [{"asset": "000001.SZ", "shares": 1_000, "mv": 12_000.0}]
    tracking_store.ensure_run(
        _RUNTIME_ID,
        _PAPER_ID,
        backtest_id="phaseb-backtest",
        start_date=day,
        bar_interval="1d",
        start_slot=f"{day.isoformat()}T10:00:00+08:00",
    )
    tracking_store.save_shadow_state(
        _RUNTIME_ID,
        _PAPER_ID,
        cash=237_995.0,
        positions=positions,
        last_bar_slot=f"{day.isoformat()}T10:00:00+08:00",
    )
    tracking_store.save_daily(
        runtime_id=_RUNTIME_ID,
        portfolio_id=_PAPER_ID,
        day=day,
        source="paper",
        nav=249_995.0,
        cash=237_995.0,
        market_value=12_000.0,
        positions=positions,
        trades=[{"tid": "phaseb-trade-1", "asset": "000001.SZ", "fee": 5.0}],
        model_hash=model_hash,
    )
    tracking_store.save_bar(
        runtime_id=_RUNTIME_ID,
        portfolio_id=_PAPER_ID,
        bar_slot=f"{day.isoformat()}T10:00:00+08:00",
        bar_interval="1d",
        source="actual",
        nav=249_995.0,
        cash=237_995.0,
        market_value=12_000.0,
        positions=positions,
        trades=[{"tid": "phaseb-trade-1", "asset": "000001.SZ", "fee": 5.0}],
        model_hash=model_hash,
        model_ref=model_ref,
    )


def _assert_paper_snapshot(facts: dict[str, list[dict[str, object]]]) -> None:
    for table in _FACT_TABLES:
        assert facts[table], table
    assert len(facts["orders"]) == 2
    assert {str(row["status"]) for row in facts["orders"]} == {
        str(int(OrderStatus.SUCCEEDED)),
        str(int(OrderStatus.REPORTED)),
    }
    assert float(facts["trades"][0]["fee"]) == 5.0
    assert float(facts["positions"][0]["shares"]) == 1_000.0
    assert float(facts["assets"][0]["total"]) == 249_995.0
    assert facts["strategy_tracking_runs"][0]["runtime_id"] == _RUNTIME_ID
    assert facts["strategy_tracking_bars"][0]["model_ref"]


def _assert_ablation(data: dict[str, object]) -> None:
    baseline = data["baseline"]
    variant = data["variants"][0]
    assert baseline["trade_count"] > 0
    assert baseline["total_fees"] > 0
    assert len(baseline["equity_curve"]) >= 20
    assert len(variant["equity_curve"]) >= 20
    assert variant["total_fees"] > 0
    assert baseline["shap_top_features"]
    assert variant["shap_top_features"]
    assert variant["max_drawdown_delta"] is not None
    assert baseline["equity_curve"][-1]["total"] > 0
    assert variant["equity_curve"][-1]["total"] > 0
    assert all(
        isinstance(item.get("total"), (int, float))
        for item in [*baseline["equity_curve"], *variant["equity_curve"]]
    )


@pytest.mark.parametrize("custom_factor_dir", [False, True])
@pytest.mark.timeout(300)
def test_skill_cli_completes_real_ablation_without_touching_paper(
    tmp_path: Path, custom_factor_dir: bool
) -> None:
    config_home = tmp_path / "config"
    previous = set_app_config_dir_override(config_home)
    db.init(get_app_db_path())
    state = init_wizard.get_state()
    state.app_home = str(tmp_path / "formal")
    state.init_completed = True
    state.init_step = 6
    state.tushare_token = ""
    init_wizard.save_state(state)
    demo = activate_demo_bundle()
    expected_factor_dir = (
        tmp_path / "custom-factors" if custom_factor_dir else config_home / "factors"
    )
    init_wizard.save_runtime_config(
        str(tmp_path / "formal"),
        "127.0.0.1",
        8130,
        "/quantide",
        factor_dir=str(expected_factor_dir) if custom_factor_dir else "",
        strategy_dir=str(config_home / "strategies"),
    )
    assert Path(get_factor_dir()).resolve() == expected_factor_dir.resolve()
    assert expected_factor_dir.is_dir()

    runner = tmp_path / "cli_runner.py"
    runner.write_text(
        "from quantide.cli import main\nif __name__ == '__main__':\n    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "QUANTIDE_CONFIG_HOME": str(config_home),
        "QUANTIDE_DATA_HOME": str(demo["demo_home"]),
        "QUANTIDE_LOG_HOME": str(tmp_path / "logs"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PHASEB_FAKE_API_KEY": _FAKE_KEY,
        "CLI_RUNNER": str(runner),
    }
    try:
        rc, created = _run(env, "factor", "init", "ai_skill_factor", "--json")
        assert rc == 0 and created["ok"] is True
        path = Path(str((created["data"] or {})["path"]))
        assert path.parent.resolve() == expected_factor_dir.resolve()
        good = path.read_text(encoding="utf-8")
        path.write_text(
            good.replace(
                'pl.col("close").shift(1).over("asset")',
                'pl.col("close").shift(-1).over("asset")',
            ),
            encoding="utf-8",
        )
        rc, bad = _run(env, "factor", "check", "ai_skill_factor", "--json")
        assert rc == 3 and bad["status"] == "FAIL"
        assert bad["diagnostics"]

        path.write_text(good, encoding="utf-8")
        rc, passed = _run(env, "factor", "check", "ai_skill_factor", "--json")
        assert rc == 0 and passed["status"] == "PASS"
        assert (passed["data"] or {})["orthogonality"]["max_abs_rank_corr"] is not None

        rc, listed = _run(env, "factor", "list", "--json")
        assert rc == 0
        factor_ids = {item["factor_id"] for item in (listed["data"] or {}).get("factors") or []}
        assert "ai_skill_factor" in factor_ids

        rc, study = _run(
            env,
            "factor",
            "study",
            "ai_skill_factor",
            "--start",
            "2024-01-02",
            "--end",
            "2024-06-28",
            "--holdings",
            "5",
            "--json",
        )
        assert rc == 0 and study["status"] == "OK"
        assert (study["data"] or {})["results"]

        rc, base = _run(
            env,
            "preset",
            "save",
            "--id",
            "skill_base",
            "--name",
            "Skill Base",
            "--features",
            "ma20_slope,bias_5",
            "--json",
        )
        assert rc == 0 and base["ok"] is True
        rc, preset = _run(
            env,
            "preset",
            "save",
            "--id",
            "skill_ai",
            "--name",
            "Skill AI",
            "--features",
            "ma20_slope,bias_5,ai_skill_factor",
            "--json",
        )
        assert rc == 0 and preset["ok"] is True
        assert (preset["data"] or {})["features"][-1] == "ai_skill_factor"

        day = market_now().date()
        model_key_value, model = _seed_model(load_preset("skill_base"))
        model_ref = str((model.get("extra") or {}).get("model_ref") or "")
        assert model_ref
        tracking_store.rebind(get_app_db_path())
        _seed_paper(day, model_ref, str(model.get("model_hash") or ""))
        db_path = get_app_db_path()
        facts_before = _paper_facts(db_path, _PAPER_ID)
        _assert_paper_snapshot(facts_before)
        model_before = _model_state(ModelStore().root, model_key_value)
        assert model_before["model_ref"] == model_ref

        rc, ablation = _run(
            env,
            "backtest",
            "run",
            "--strategy",
            "MLMomentumReversalStrategy",
            "--preset",
            "skill_ai",
            "--ablation-vs",
            "skill_base",
            "--start",
            "2024-11-01",
            "--end",
            "2024-12-31",
            "--initial-cash",
            "250000",
            "--json",
        )
        assert rc == 0 and ablation["status"] == "OK"
        _assert_ablation(ablation["data"])
        baseline_ref = str((ablation["data"] or {}).get("baseline", {}).get("model_ref") or "")
        assert baseline_ref
        assert baseline_ref.rsplit("/", 1)[0] == model_key_value
        baseline_payload, baseline_artifact = ModelStore().load_ref(baseline_ref)
        assert baseline_payload is not None and baseline_artifact is not None
        assert baseline_artifact.model_key == model_key_value
        assert baseline_artifact.pipeline_version == PIPELINE_VERSION

        rc, invalid = _run(
            env,
            "backtest",
            "run",
            "--strategy",
            "MLMomentumReversalStrategy",
            "--preset",
            "missing_preset",
            "--start",
            "2024-01-02",
            "--end",
            "2024-02-01",
            "--json",
        )
        assert rc == 2 and invalid["status"] == "ERROR"
        rc, insufficient = _run(
            env,
            "factor",
            "check",
            "ai_skill_factor",
            "--start",
            "1990-01-01",
            "--end",
            "1990-01-02",
            "--json",
        )
        assert rc == 4 and insufficient["status"] == "INCONCLUSIVE"

        assert _paper_facts(db_path, _PAPER_ID) == facts_before
        model_after = _model_state(ModelStore().root, model_key_value)
        assert model_after == model_before
        reloaded, metadata = ModelStore().load(model_key_value)
        referenced, ref_metadata = ModelStore().load_ref(model_ref)
        assert reloaded == {"phaseb": "running-model"} == referenced
        assert metadata is not None and ref_metadata is not None
        assert str((metadata.extra or {}).get("model_ref") or "") == model_ref
        assert str((ref_metadata.extra or {}).get("model_ref") or "") == model_ref
    finally:
        set_app_config_dir_override(previous)

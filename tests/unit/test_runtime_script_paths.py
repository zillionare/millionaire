"""Maintenance tools must honor the same profile as the application."""

import json
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest

from scripts import fix_daily_sync, replay_decision
from quantide.data.models.app_state import AppState


@pytest.fixture
def maintenance_profile(monkeypatch, tmp_path, db):
    previous = db.db_path
    target = tmp_path / "config/quantide.db"
    target.parent.mkdir()
    monkeypatch.setattr(fix_daily_sync, "get_app_db_path", lambda: target)
    loader = Mock()
    monkeypatch.setattr("quantide.data.init_data", loader)
    try:
        db.init(target)
        yield tmp_path, db, loader
    finally:
        db.init(previous)


def test_sync_tool_preserves_saved_directory_and_settings(monkeypatch, maintenance_profile):
    root, db, loader = maintenance_profile
    saved = AppState(app_home=str(root / "saved"), app_port=9123, init_completed=False)
    db["app_state"].upsert(saved.to_dict(), pk="id")
    monkeypatch.setenv("QUANTIDE_DATA_HOME", str(root / "environment"))
    fix_daily_sync.init_app_state("test-token")
    row = db["app_state"].get(1)
    assert row["app_home"] == str(root / "saved")
    assert row["app_port"] == 9123
    assert not row["init_completed"]
    assert row["tushare_token"] == "test-token"
    loader.assert_called_once_with(str(root / "saved"), init_db=False)


@pytest.mark.parametrize("configured", [True, False])
def test_sync_tool_uses_environment_then_tmp_for_a_new_profile(
    monkeypatch, maintenance_profile, configured
):
    from quantide.config import paths

    root, db, loader = maintenance_profile
    monkeypatch.delenv("QUANTIDE_DATA_HOME", raising=False)
    monkeypatch.setattr(paths, "temporary_runtime_dir", lambda: root / "fallback")
    expected = root / "fallback/market"
    if configured:
        expected = root / "configured"
        monkeypatch.setenv("QUANTIDE_DATA_HOME", str(expected))
    fix_daily_sync.init_app_state("test-token")
    assert db["app_state"].get(1)["app_home"] == str(expected)
    loader.assert_called_once_with(str(expected), init_db=False)


def test_sync_verifier_reads_saved_directory(maintenance_profile):
    root, db, _ = maintenance_profile
    home = root / "saved"
    (home / "data").mkdir(parents=True)
    pl.DataFrame({"asset": ["000001.SZ"]}).write_parquet(home / "data/stock_list.parquet")
    db["app_state"].upsert(AppState(app_home=str(home)).to_dict(), pk="id")
    assert fix_daily_sync.verify_data()["stock_list"] == {"total_rows": 1}


def test_replay_uses_configured_profile_and_initializes_settings(monkeypatch, tmp_path, capsys):
    state = tmp_path / "config/strategy_runtimes.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"strategy_runtimes": [{
        "mode": "paper", "runtime_id": "saved-runtime", "config": {"top_k": 5}
    }]}))
    loader = Mock()
    monkeypatch.setattr(replay_decision, "init_data", loader)
    monkeypatch.setattr(replay_decision, "get_strategy_runtime_state_path", lambda: state)
    monkeypatch.setattr(replay_decision.ml, "_ensure_data_connected", lambda: True)
    monkeypatch.setattr(replay_decision, "_load_quotes", lambda _args: ({}, "fixture"))
    monkeypatch.setattr(replay_decision, "build_report", lambda *_args: {"ranked": [{}]})
    monkeypatch.setattr(replay_decision.sys, "argv", ["replay", "--json"])
    assert replay_decision.main() == 0
    loader.assert_called_once_with(None)
    assert json.loads(capsys.readouterr().out)["runtime_id"] == "saved-runtime"


def test_replay_refuses_checkout_quote_output_before_loading_data(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    loader = Mock()
    monkeypatch.setattr(replay_decision, "init_data", loader)
    monkeypatch.setattr(replay_decision.sys, "argv", [
        "replay", "--save-quotes", str(root / "data/quotes.json")
    ])
    with pytest.raises(SystemExit) as error:
        replay_decision.main()
    assert error.value.code == 2
    loader.assert_not_called()

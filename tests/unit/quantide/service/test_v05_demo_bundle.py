"""Demo Bundle integrity, isolation and research-mode contract tests."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from quantide.config.settings import get_data_home, get_settings
from quantide.data.models.daily_bars import daily_bars
from quantide.service import demo_bundle
from quantide.service.demo_bundle import (
    REQUIRED_FILES,
    activate_demo_bundle,
    deactivate_demo_bundle,
    demo_status,
    verify_bundle,
)
from quantide.service.init_wizard import init_wizard
from quantide.service.research_cli import data_status


def _seed_state(tmp_path: Path) -> Path:
    formal = tmp_path / "formal-home"
    formal.mkdir()
    (formal / "keep.txt").write_text("formal", encoding="utf-8")
    state = init_wizard.get_state()
    state.app_home = str(formal)
    state.factor_dir = str(tmp_path / "factors")
    state.strategy_dir = str(tmp_path / "strategies")
    state.init_completed = True
    state.init_step = 6
    state.tushare_token = ""
    init_wizard.save_state(state)
    return formal


def test_committed_bundle_is_under_budget_and_complete() -> None:
    manifest = verify_bundle()
    total = sum((demo_bundle.bundle_root() / name).stat().st_size for name in REQUIRED_FILES)
    total += (demo_bundle.bundle_root() / "manifest.json").stat().st_size
    assert total <= 15 * 1024 * 1024
    assert 100 <= manifest["asset_count"] <= 200
    assert manifest["trading_days"] >= 500
    assert {item["name"] for item in manifest["files"]} == set(REQUIRED_FILES)


def test_activation_mounts_isolated_copy_without_touching_formal_home(db, tmp_path) -> None:
    formal = _seed_state(tmp_path)
    before = {path.relative_to(formal) for path in formal.rglob("*")}

    status = activate_demo_bundle()

    after = {path.relative_to(formal) for path in formal.rglob("*")}
    assert after == before
    assert (formal / "keep.txt").read_text(encoding="utf-8") == "formal"
    assert status["mode"] == "demo_bundle"
    assert Path(status["demo_home"]).is_dir()
    assert Path(status["demo_home"]).is_relative_to(demo_bundle.ensure_app_config_dir())
    assert Path(status["demo_home"]) != formal
    assert get_data_home() == status["demo_home"]
    assert get_settings().data_source_mode == "demo_bundle"
    assert len(daily_bars.available_dates) >= 500
    assert (Path(status["demo_home"]) / "data/stock_status_pit.parquet").is_file()
    report = data_status()
    assert report["mode"] == "demo_bundle"
    assert report["data_home"] == status["demo_home"]
    assert report["formal_data_home"] == str(formal)
    assert any(row["name"] == "stock_status_pit" for row in report["datasets"])


def test_deactivation_restores_standard_mode_and_formal_home(db, tmp_path) -> None:
    formal = _seed_state(tmp_path)
    activate_demo_bundle()

    status = deactivate_demo_bundle()

    assert status["mode"] == "standard"
    assert get_settings().data_source_mode == "standard"
    assert get_data_home() == str(formal)
    assert (formal / "keep.txt").is_file()
    assert demo_status()["formal_data_home"] == str(formal)


def test_manifest_hash_is_enforced(tmp_path) -> None:
    copied = tmp_path / "bundle"
    shutil.copytree(demo_bundle.bundle_root(), copied)
    target = copied / "calendar.parquet"
    target.write_bytes(target.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="校验失败"):
        verify_bundle(copied)


def test_activation_is_idempotent_and_does_not_copy_into_checkout(db, tmp_path) -> None:
    _seed_state(tmp_path)
    first = activate_demo_bundle()
    second = activate_demo_bundle()
    assert first["demo_home"] == second["demo_home"]
    assert Path(second["demo_home"]).is_relative_to(Path(demo_bundle.ensure_app_config_dir()))
    assert dt.date.fromisoformat(str(second["data_end"])) >= dt.date(2024, 12, 31)

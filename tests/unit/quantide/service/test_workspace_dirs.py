"""Durable workspace directory normalization and persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantide.config.settings import Settings
from quantide.data.models.app_state import AppState
from quantide.service.workspace_dirs import normalize_workspace_directories, prepare_workspace_dir


def test_three_directories_are_created_and_probed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANTIDE_CONFIG_HOME", str(tmp_path / "config"))
    directories = normalize_workspace_directories(
        tmp_path / "market",
        None,
        str(tmp_path / "strategies"),
    )

    assert Path(directories.data_home).is_dir()
    assert Path(directories.factor_dir).is_dir()
    assert Path(directories.factor_dir).name == "factors"
    assert Path(directories.strategy_dir) == (tmp_path / "strategies").resolve()
    assert not list(Path(directories.factor_dir).glob(".millionaire-write-probe-*"))


def test_source_checkout_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside the source checkout"):
        prepare_workspace_dir(Path.cwd(), "用户因子目录")


def test_settings_resolve_workspace_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANTIDE_CONFIG_HOME", str(tmp_path / "config"))
    state = AppState(app_home=str(tmp_path / "market"))

    settings = Settings.from_state(state)

    assert settings.app_home == str((tmp_path / "market").resolve())
    assert settings.factor_dir == str((tmp_path / "config" / "factors").resolve())
    assert settings.strategy_dir == str((tmp_path / "config" / "strategies").resolve())

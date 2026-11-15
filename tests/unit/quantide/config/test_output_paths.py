"""Regression contracts for cwd-independent runtime output."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantide.config import output_paths, paths

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("value", [".", "data", ROOT, ROOT / "runtime/config"])
def test_source_output_is_rejected_before_any_directory_is_created(monkeypatch, value):
    monkeypatch.chdir(ROOT)
    with pytest.raises(ValueError, match="outside the source checkout"):
        paths.normalize_data_home(value)
    monkeypatch.setenv("QUANTIDE_CONFIG_HOME", str(value))
    with pytest.raises(ValueError, match="outside the source checkout"):
        paths.get_app_config_dir()


def test_symlink_cannot_redirect_runtime_output_into_checkout(tmp_path):
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(ROOT, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable for this Windows account")
    with pytest.raises(ValueError, match="outside the source checkout"):
        output_paths.external_runtime_path(alias / "data")


def test_temporary_fallback_is_per_user_and_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("QUANTIDE_DATA_HOME", raising=False)
    first = Path(paths.normalize_data_home())
    monkeypatch.chdir(tmp_path)
    assert Path(paths.normalize_data_home("   ")) == first
    assert first.is_relative_to(output_paths.temporary_runtime_dir())
    if os.name != "nt":
        assert first.is_relative_to(Path("/tmp"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "another-user"))
    assert Path(paths.normalize_data_home()) != first


def test_windows_fallback_uses_native_temp(monkeypatch, tmp_path):
    monkeypatch.setattr(output_paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(output_paths.tempfile, "gettempdir", lambda: str(tmp_path))
    assert output_paths.temporary_runtime_dir().is_relative_to(tmp_path / "millionaire")


def test_explicit_data_home_overrides_environment_and_stays_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUANTIDE_DATA_HOME", str(tmp_path / "environment"))
    assert paths.normalize_data_home() == str(tmp_path / "environment")
    selected = paths.normalize_data_home("explicit")
    monkeypatch.chdir(tmp_path.parent)
    assert selected == str(tmp_path / "explicit")


@pytest.mark.parametrize("configured", [False, True])
def test_development_logs_use_configuration_then_tmp(monkeypatch, tmp_path, configured):
    monkeypatch.delenv("QUANTIDE_LOG_HOME", raising=False)
    monkeypatch.setattr(output_paths, "temporary_runtime_dir", lambda: tmp_path / "fallback")
    if configured:
        monkeypatch.setenv("QUANTIDE_LOG_HOME", str(tmp_path / "configured"))
    path = output_paths.console_log_path()
    expected = tmp_path / "configured" if configured else tmp_path / "fallback/logs"
    assert path == expected / "development.log"
    path.write_text("service log\n")
    assert path.read_text() == "service log\n"


def test_runtime_writers_reject_checkout_database_and_model_paths():
    from quantide.data.sqlite import db
    from quantide.service.model_store import ModelStore
    from quantide.service.simulated_counter import SimulatedCounter
    from quantide.service.strategy_tracking import TrackingStore
    from quantide.web.auth.database import AuthDatabase

    for writer in (db.init, ModelStore, SimulatedCounter, TrackingStore, AuthDatabase):
        with pytest.raises(ValueError, match="outside the source checkout"):
            writer(ROOT / "quantide.db")


@pytest.mark.parametrize("bad_setting", ["install_root", "MILLIONAIRE_SERVICE_HOME"])
def test_windows_service_install_rejects_source_output_before_os_calls(
    monkeypatch, tmp_path, bad_setting
):
    from quantide.service import host_service

    monkeypatch.setattr(host_service, "install_root", lambda: tmp_path)
    if bad_setting == "install_root":
        monkeypatch.setattr(host_service, "install_root", lambda: ROOT)
    else:
        monkeypatch.setenv("MILLIONAIRE_SERVICE_HOME", str(ROOT / "data"))
    with pytest.raises(ValueError, match="outside the source checkout"):
        host_service._install_windows()

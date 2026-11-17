"""Explicit risk-extension loading, CLI opt-in and default-empty contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import quantide.providers.extensions as quote_extensions
import quantide.providers.risk_extensions as risk_extensions
from quantide.cli import main
from quantide.service.risk_programs import RiskProgramRegistry, risk_program_registry


@pytest.fixture
def extension_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(quote_extensions, "ensure_app_config_dir", lambda: tmp_path)
    previous_adapters = dict(risk_program_registry._adapters)
    previous_loaded = set(risk_extensions._LOADED_IDS)
    risk_program_registry.clear()
    risk_extensions._LOADED_IDS.clear()
    try:
        yield tmp_path / "extensions"
    finally:
        risk_program_registry.clear()
        risk_program_registry._adapters.update(previous_adapters)
        risk_extensions._LOADED_IDS.clear()
        risk_extensions._LOADED_IDS.update(previous_loaded)


def test_disabled_extension_never_executes_user_code(extension_state) -> None:
    extension_state.mkdir(parents=True)
    (extension_state / "risk_extensions.py").write_text(
        "raise RuntimeError('must not execute while disabled')\n", encoding="utf-8"
    )

    registry = RiskProgramRegistry()

    assert risk_extensions.load_risk_extensions(registry) == []
    assert registry.list() == []
    assert risk_program_registry.list() == []


def test_cli_copy_example_enables_and_loads_only_example(extension_state, capsys) -> None:
    exit_code = main(["risk-extension", "enable", "--copy-example", "--json"])

    output = json.loads(capsys.readouterr().out)
    payload = output["data"]
    assert exit_code == 0
    assert output["command"] == "risk-extension.enable"
    assert payload["enabled"] is True
    assert payload["copied_example"] is True
    assert Path(payload["extension_path"]).is_file()

    loaded = risk_extensions.load_risk_extensions()
    assert loaded == ["example.single_asset_weight_cap"]
    assert [adapter.id for adapter in risk_program_registry.list()] == loaded
    source = Path(payload["extension_path"]).read_text(encoding="utf-8").lower()
    assert "triple_barrier" not in source
    assert "rolling_drawdown" not in source
    assert "stop_loss" not in source

    assert main(["risk-extension", "disable", "--json"]) == 0
    assert risk_extensions.load_risk_extensions() == []
    assert risk_program_registry.list() == []


def test_status_and_enable_do_not_import_extension(extension_state, capsys, monkeypatch) -> None:
    extension_state.mkdir(parents=True)
    (extension_state / "risk_extensions.py").write_text(
        "raise RuntimeError('status must not import me')\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        risk_extensions.importlib.util,
        "spec_from_file_location",
        lambda *args, **kwargs: pytest.fail("configuration must not import user code"),
    )

    assert main(["risk-extension", "status", "--json"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["data"]["file_exists"] is True

    assert main(["risk-extension", "enable", "--json"]) == 0
    enable_payload = json.loads(capsys.readouterr().out)
    assert enable_payload["data"]["enabled"] is True


def test_adapter_exposes_both_execution_factories(extension_state) -> None:
    main(["risk-extension", "enable", "--copy-example", "--json"])
    risk_extensions.load_risk_extensions()
    adapter = risk_program_registry.get("example.single_asset_weight_cap")

    assert adapter is not None
    assert adapter.default_params == {"max_weight": 0.25}
    assert adapter.overlay_factory is not None
    assert adapter.live_strategy_factory is not None
    assert 50 <= len(risk_extensions.EXAMPLE_FILE.read_text(encoding="utf-8").splitlines()) <= 80

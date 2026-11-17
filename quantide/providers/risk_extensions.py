"""Explicitly enabled, persistent user risk extensions loaded in-process."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any, cast

from quantide.core.atomic_files import write_json
from quantide.providers.extensions import extension_directory
from quantide.service.risk_programs import RiskProgramRegistry, risk_program_registry

STATE_FILE = "risk-extensions.json"
EXTENSION_FILE = "risk_extensions.py"
EXAMPLE_FILE = (
    Path(__file__).resolve().parents[1] / "assets" / "examples" / "risk_single_asset_cap.py"
)
_LOADED_IDS: set[str] = set()


def risk_extension_path() -> Path:
    """Return the explicit user risk-extension module path."""
    return extension_directory() / EXTENSION_FILE


def risk_state_path() -> Path:
    """Return the persistent opt-in state path."""
    return extension_directory() / STATE_FILE


def risk_extension_enabled() -> bool:
    """Require a boolean opt-in and never execute user code from this check."""
    state_path = risk_state_path()
    if not state_path.exists():
        return False
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if type(payload.get("enabled")) is not bool:
        raise ValueError(f"{STATE_FILE} requires a boolean enabled field")
    return cast(bool, payload["enabled"])


def _copy_example(target: Path) -> bool:
    if target.exists():
        return False
    if not EXAMPLE_FILE.is_file():
        raise FileNotFoundError(f"Teaching example is missing: {EXAMPLE_FILE}")
    shutil.copy2(EXAMPLE_FILE, target)
    return True


def _status(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    path = risk_extension_path()
    return {
        "enabled": risk_extension_enabled(),
        "extension_path": str(path),
        "state_path": str(risk_state_path()),
        "file_exists": path.is_file(),
        "example_path": str(EXAMPLE_FILE),
        "example_available": EXAMPLE_FILE.is_file(),
        "loaded_program_ids": sorted(_LOADED_IDS),
        **(extra or {}),
    }


def configure_risk_extension(enabled: bool, *, copy_example: bool = False) -> dict[str, Any]:
    """Persist opt-in without importing user code in the configuration process."""
    path = risk_extension_path()
    copied = copy_example and enabled and _copy_example(path)
    if enabled and not path.is_file():
        raise FileNotFoundError(f"Create {path} before enabling the risk extension")
    write_json(risk_state_path(), {"enabled": bool(enabled)})
    return _status({"copied_example": copied, "restart_required": True})


def risk_extension_status() -> dict[str, Any]:
    """Return credential-free visibility for CLI and system maintenance."""
    return _status()


def _unload_loaded(registry: RiskProgramRegistry) -> None:
    for program_id in tuple(_LOADED_IDS):
        registry.unregister(program_id)
    _LOADED_IDS.clear()


def load_risk_extensions(registry: RiskProgramRegistry | None = None) -> list[str]:
    """Load ``register_extensions`` only when explicitly enabled."""
    target = registry or risk_program_registry
    if not risk_extension_enabled():
        _unload_loaded(target)
        return []
    path = risk_extension_path()
    if not path.is_file():
        raise FileNotFoundError(f"Risk extension is enabled but missing: {path}")
    spec = importlib.util.spec_from_file_location("millionaire_user_risk_extensions", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load risk extensions from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    register = getattr(module, "register_extensions", None)
    if not callable(register):
        raise TypeError("risk_extensions.py must export register_extensions(registry)")

    staged = RiskProgramRegistry()
    register(staged)
    adapters = staged.list()
    conflicts = [
        adapter.id
        for adapter in adapters
        if target.get(adapter.id) is not None and adapter.id not in _LOADED_IDS
    ]
    if conflicts:
        raise ValueError(f"risk extension conflicts with host programs: {', '.join(conflicts)}")

    _unload_loaded(target)
    for adapter in adapters:
        target.register(adapter)
        _LOADED_IDS.add(adapter.id)
    return sorted(_LOADED_IDS)


__all__ = [
    "EXTENSION_FILE",
    "EXAMPLE_FILE",
    "STATE_FILE",
    "configure_risk_extension",
    "load_risk_extensions",
    "risk_extension_enabled",
    "risk_extension_path",
    "risk_extension_status",
    "risk_state_path",
]

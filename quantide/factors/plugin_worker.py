"""Isolated worker entry points for external factor plugins."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import polars as pl

from quantide.factors.plugins import (
    FactorPlugin,
    PluginContractError,
    SkippedFactorReason,
    _load_plugin,
    _PluginLoadError,
    compute_plugin,
)


def _plugin_payload(plugin: FactorPlugin) -> dict[str, Any]:
    payload = asdict(plugin)
    payload.pop("compute", None)
    return payload


def inspect_plugin(path: str, expected_source_hash: str = "") -> dict[str, Any]:
    """Import one file inside a worker and return picklable metadata or a problem."""
    try:
        plugin = _load_plugin(Path(path))
        if expected_source_hash and plugin.source_hash != expected_source_hash:
            raise _PluginLoadError(
                SkippedFactorReason.IMPORT_ERROR,
                "source changed while it was being inspected",
            )
        return {"plugin": _plugin_payload(plugin)}
    except _PluginLoadError as exc:
        return {"problem": {"reason": exc.reason.value, "detail": exc.detail}}
    except BaseException as exc:  # worker boundary: SystemExit must not kill the parent
        return {"problem": {"reason": "ImportError", "detail": f"{type(exc).__name__}: {exc}"}}


def compute_once(path: str, expected_source_hash: str, frame: pl.DataFrame) -> pl.DataFrame:
    """Load and compute one plugin inside a worker process."""
    plugin = _load_plugin(Path(path))
    if expected_source_hash and plugin.source_hash != expected_source_hash:
        raise PluginContractError("plugin source changed before computation")
    return compute_plugin(frame, plugin)


def compute_sequence(
    path: str,
    expected_source_hash: str,
    frames: list[pl.DataFrame],
) -> list[pl.DataFrame]:
    """Warm one plugin module, then compute a sequence of frames in one worker."""
    plugin = _load_plugin(Path(path))
    if expected_source_hash and plugin.source_hash != expected_source_hash:
        raise PluginContractError("plugin source changed before computation")
    return [compute_plugin(frame, plugin) for frame in frames]


__all__ = ["compute_once", "compute_sequence", "inspect_plugin"]

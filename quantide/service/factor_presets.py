"""Durable factor presets with strict existence and wind-tunnel validation."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantide.audit.models import canonical_hash
from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import write_json
from quantide.core.market_time import market_now
from quantide.factors.plugins import discover_factor_plugins
from quantide.factors.registry import all_factor_ids
from quantide.service.factor_audit import factor_wind_tunnel_badge

_PRESET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
LABEL_KINDS = {"raw_return", "excess_mean", "cs_rank"}
DEFAULT_STRATEGY_ID = "MLMomentumReversalStrategy"


def _preset_root() -> Path:
    root = ensure_app_config_dir() / "presets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path(preset_id: str) -> Path:
    if not _PRESET_ID.fullmatch(preset_id):
        raise ValueError("preset_id 必须匹配 ^[a-z0-9][a-z0-9_-]{1,63}$")
    return _preset_root() / f"{preset_id}.json"


def _strategy_class(strategy_id: str) -> Any:
    if strategy_id in {"MLMomentumReversalStrategy", "ml_momentum_reversal"}:
        from quantide.strategies.example.ml_momentum_reversal import (
            MLMomentumReversalStrategy,
        )

        return MLMomentumReversalStrategy
    try:
        from quantide.service.discovery import strategy_loader

        cls = strategy_loader.load_from_cache().get(strategy_id)
        if cls is not None:
            return cls
    except Exception:
        pass
    raise ValueError(f"未知策略: {strategy_id}")


def _strategy_interval(strategy_id: str) -> str:
    cls = _strategy_class(strategy_id)
    raw = getattr(cls, "BAR_INTERVAL", None) or getattr(cls, "bar_interval", None)
    return str(raw or "1d").strip()


def resolve_strategy(strategy_id: str) -> Any:
    """Return the registered strategy class for a preset/backtest command."""
    return _strategy_class(strategy_id)


def strategy_interval(strategy_id: str) -> str:
    """Return the immutable interval declared by one strategy."""
    return _strategy_interval(strategy_id)


def _feature_interval(factor_id: str) -> str:
    plugin = discover_factor_plugins().by_id(factor_id)
    return plugin.bar_interval if plugin is not None else "1d"


def _validate_features(features: list[str], bar_interval: str) -> tuple[str, ...]:
    if not features:
        raise ValueError("因子预设必须至少包含一个因子")
    known = set(all_factor_ids())
    for factor_id in features:
        if factor_id not in known:
            raise ValueError(f"预设引用缺失因子: {factor_id}")
        interval = _feature_interval(factor_id)
        if interval != bar_interval:
            raise ValueError(f"因子 {factor_id} 周期 {interval} 与预设周期 {bar_interval} 不匹配")
        badge = factor_wind_tunnel_badge(factor_id)
        if badge.badge_status == "FAIL":
            raise ValueError(f"预设引用风洞 FAIL 因子: {factor_id}")
    return tuple(features)


@dataclass(frozen=True)
class FactorPreset:
    """One named factor combination bound to a strategy and interval."""

    preset_id: str
    name: str
    description: str
    strategy_id: str
    bar_interval: str
    features: tuple[str, ...]
    label_kind: str = "raw_return"
    strategy_params: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""
    preset_hash: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "name": self.name,
            "description": self.description,
            "strategy_id": self.strategy_id,
            "bar_interval": self.bar_interval,
            "features": list(self.features),
            "label_kind": self.label_kind,
            "strategy_params": self.strategy_params,
            "updated_at": self.updated_at,
        }

    def compute_hash(self) -> str:
        payload = self.payload()
        payload.pop("updated_at", None)
        return canonical_hash(payload)

    def as_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["preset_hash"] = self.preset_hash or self.compute_hash()
        return payload

    def to_config(self) -> dict[str, Any]:
        config = dict(self.strategy_params)
        config.update(
            {
                "features": list(self.features),
                "label_kind": self.label_kind,
                "bar_interval": self.bar_interval,
            }
        )
        return config

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FactorPreset:
        preset = cls(
            preset_id=str(payload.get("preset_id") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            strategy_id=str(payload.get("strategy_id") or DEFAULT_STRATEGY_ID),
            bar_interval=str(payload.get("bar_interval") or "1d"),
            features=tuple(str(item) for item in payload.get("features") or []),
            label_kind=str(payload.get("label_kind") or "raw_return"),
            strategy_params=dict(payload.get("strategy_params") or {}),
            updated_at=str(payload.get("updated_at") or ""),
            preset_hash=str(payload.get("preset_hash") or ""),
        )
        expected = preset.compute_hash()
        if preset.preset_hash and preset.preset_hash != expected:
            raise ValueError(f"预设指纹不匹配: {preset.preset_id}")
        return preset


def validate_preset(preset: FactorPreset) -> FactorPreset:
    if not _PRESET_ID.fullmatch(preset.preset_id):
        raise ValueError("preset_id 必须匹配 ^[a-z0-9][a-z0-9_-]{1,63}$")
    if preset.label_kind not in LABEL_KINDS:
        raise ValueError(f"不支持的 label_kind: {preset.label_kind}")
    expected_interval = _strategy_interval(preset.strategy_id)
    if preset.bar_interval != expected_interval:
        raise ValueError(f"预设周期 {preset.bar_interval} 与策略周期 {expected_interval} 不匹配")
    features = _validate_features(list(preset.features), preset.bar_interval)
    return FactorPreset(
        preset_id=preset.preset_id,
        name=preset.name,
        description=preset.description,
        strategy_id=preset.strategy_id,
        bar_interval=preset.bar_interval,
        features=features,
        label_kind=preset.label_kind,
        strategy_params=dict(preset.strategy_params),
        updated_at=preset.updated_at,
        preset_hash=preset.compute_hash(),
    )


def save_preset(
    preset_id: str,
    name: str,
    features: list[str] | tuple[str, ...],
    *,
    description: str = "",
    strategy_id: str = DEFAULT_STRATEGY_ID,
    label_kind: str = "raw_return",
    strategy_params: dict[str, Any] | None = None,
) -> FactorPreset:
    """Validate and atomically persist one preset; missing/FAIL factors abort."""
    if "features" in (strategy_params or {}):
        raise ValueError("strategy_params 不应包含 features，请使用 --features")
    preset = FactorPreset(
        preset_id=preset_id,
        name=name or preset_id,
        description=description,
        strategy_id=strategy_id,
        bar_interval=_strategy_interval(strategy_id),
        features=tuple(features),
        label_kind=label_kind,
        strategy_params=dict(strategy_params or {}),
        updated_at=market_now().isoformat(),
    )
    validated = validate_preset(preset)
    write_json(_path(validated.preset_id), validated.as_dict())
    return validated


def load_preset(preset_id: str, *, validate: bool = True) -> FactorPreset:
    path = _path(preset_id)
    if not path.is_file():
        raise KeyError(f"预设不存在: {preset_id}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"预设文件损坏: {preset_id}") from exc
    preset = FactorPreset.from_dict(payload)
    return validate_preset(preset) if validate else preset


def list_presets(*, validate: bool = False) -> list[FactorPreset]:
    presets: list[FactorPreset] = []
    for path in sorted(_preset_root().glob("*.json")):
        try:
            preset = load_preset(path.stem, validate=validate)
        except (KeyError, ValueError):
            continue
        presets.append(preset)
    return presets


def delete_preset(preset_id: str) -> bool:
    path = _path(preset_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def clone_preset(source_id: str, target_id: str, name: str | None = None) -> FactorPreset:
    source = load_preset(source_id)
    return save_preset(
        target_id,
        name or f"{source.name} copy",
        source.features,
        description=source.description,
        strategy_id=source.strategy_id,
        label_kind=source.label_kind,
        strategy_params=source.strategy_params,
    )


def preset_updated_at(preset: FactorPreset) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(preset.updated_at)
    except ValueError:
        return None


__all__ = [
    "DEFAULT_STRATEGY_ID",
    "FactorPreset",
    "LABEL_KINDS",
    "clone_preset",
    "delete_preset",
    "list_presets",
    "load_preset",
    "resolve_strategy",
    "save_preset",
    "strategy_interval",
    "validate_preset",
]

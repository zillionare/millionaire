"""Generic risk-program extension and adapter boundary.

Risk programs are registered explicitly through host-supplied adapters.  The
Community Edition ships only this generic extension mechanism; its default
registry is empty and it contains no built-in program implementations.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from quantide.core.enums import FrameType
from quantide.core.strategy import BaseStrategy
from quantide.service.risk_overlay import CompositeRiskOverlay

RISK_PROGRAMS_KEY = "risk_programs"
ALLOW_SAME_BAR_REPURCHASE_KEY = "allow_same_bar_repurchase"

RiskCompatibility = Callable[[type[BaseStrategy] | None, FrameType | str], bool]
OverlayFactory = Callable[[dict[str, Any]], Any]
LiveStrategyFactory = Callable[[Any, dict[str, Any]], Any]


@dataclass(frozen=True)
class RiskProgramAdapter:
    """Host-provided adapter for one selectable risk program.

    ``overlay_factory`` adapts the program to the generic backtest overlay
    lifecycle.  ``live_strategy_factory`` adapts it to the unchanged generic
    ``RiskStrategy`` lifecycle.  An adapter may provide either side, but a
    selected program must provide the side required by the caller.
    """

    id: str
    name: str | None = None
    description: str = ""
    default_params: Mapping[str, Any] = field(default_factory=dict)
    compatible: RiskCompatibility | None = None
    overlay_factory: OverlayFactory | None = None
    live_strategy_factory: LiveStrategyFactory | None = None

    @property
    def program_id(self) -> str:
        """Stable public alias for the adapter identifier."""
        return self.id

    def supports(
        self,
        host_strategy_cls: type[BaseStrategy] | None,
        frame_type: FrameType | str,
    ) -> bool:
        if self.compatible is None:
            return True
        return bool(self.compatible(host_strategy_cls, frame_type))

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id.rsplit(".", 1)[-1],
            "description": self.description,
            "params": dict(self.default_params),
            "adapter": self,
        }


class RiskProgramRegistry:
    """Explicit process-local registry for host-owned risk adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, RiskProgramAdapter] = {}

    def register(self, adapter: RiskProgramAdapter, *, replace: bool = False) -> RiskProgramAdapter:
        if not isinstance(adapter, RiskProgramAdapter):
            raise TypeError("risk program adapter must be a RiskProgramAdapter")
        program_id = str(adapter.id).strip()
        if not program_id:
            raise ValueError("risk program adapter id cannot be empty")
        if program_id in self._adapters and not replace:
            raise ValueError(f"risk program adapter already registered: {program_id}")
        self._adapters[program_id] = adapter
        return adapter

    def unregister(self, program_id: str) -> RiskProgramAdapter | None:
        return self._adapters.pop(str(program_id), None)

    def get(self, program_id: str) -> RiskProgramAdapter | None:
        return self._adapters.get(str(program_id))

    def clear(self) -> None:
        """Remove registered adapters; useful for host lifecycle and tests."""
        self._adapters.clear()

    def adapters(
        self,
        host_strategy_cls: type[BaseStrategy] | None = None,
        frame_type: FrameType | str = FrameType.DAY,
    ) -> list[RiskProgramAdapter]:
        return [
            adapter
            for adapter in self._adapters.values()
            if adapter.supports(host_strategy_cls, frame_type)
        ]

    def __len__(self) -> int:
        return len(self._adapters)


risk_program_registry = RiskProgramRegistry()


def register_risk_program(
    adapter: RiskProgramAdapter, *, replace: bool = False
) -> RiskProgramAdapter:
    """Register a host-owned risk adapter and return it for decorator use."""
    return risk_program_registry.register(adapter, replace=replace)


def unregister_risk_program(program_id: str) -> RiskProgramAdapter | None:
    """Remove a host-owned adapter, if present."""
    return risk_program_registry.unregister(program_id)


def available_risk_programs(
    host_strategy_cls: type[BaseStrategy] | None = None,
    frame_type: FrameType | str = FrameType.DAY,
) -> list[dict[str, Any]]:
    """List explicitly registered adapters compatible with the host/bar type."""
    return [
        adapter.metadata()
        for adapter in risk_program_registry.adapters(host_strategy_cls, frame_type)
    ]


def _available_by_id(
    host_strategy_cls: type[BaseStrategy] | None,
    frame_type: FrameType | str,
) -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): item for item in available_risk_programs(host_strategy_cls, frame_type)
    }


def unavailable_risk_program_ids(
    selected: Any,
    *,
    host_strategy_cls: type[BaseStrategy] | None = None,
    frame_type: FrameType | str = FrameType.DAY,
) -> list[str]:
    """Return persisted IDs that cannot be resolved by the current registry."""
    available = _available_by_id(host_strategy_cls, frame_type)
    values = selected if isinstance(selected, list) else []
    result: list[str] = []
    for item in values:
        program_id = str(item.get("id") if isinstance(item, dict) else item).strip()
        if program_id and program_id not in available and program_id not in result:
            result.append(program_id)
    return result


def _normalize_risk_item(
    item: Any, index: int, available: dict[str, dict[str, Any]], seen: set[str]
) -> tuple[int, int, dict[str, Any]]:
    if isinstance(item, str):
        item = {"id": item, "params": {}}
    if not isinstance(item, dict):
        raise ValueError("risk_programs 项必须是对象")
    program_id = str(item.get("id") or "").strip()
    if program_id not in available:
        raise ValueError(f"不可用的回测风控程序: {program_id or '<empty>'}")
    if program_id in seen:
        raise ValueError(f"回测风控程序重复选择: {program_id}")
    seen.add(program_id)
    params = item.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError(f"风控程序 {program_id} 的参数必须是对象")
    defaults = available[program_id]["params"]
    effective_params = dict(defaults)
    effective_params.update(params)
    try:
        priority = int(item.get("priority", index))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"风控程序 {program_id} 的优先级无效") from exc
    return priority, index, {"id": program_id, "params": effective_params}


def normalize_risk_programs(
    selected: Any,
    *,
    host_strategy_cls: type[BaseStrategy] | None = None,
    frame_type: FrameType | str = FrameType.DAY,
) -> list[dict[str, Any]]:
    """Validate and deterministically order explicitly selected adapters."""
    if selected in (None, ""):
        return []
    if isinstance(selected, str):
        try:
            selected = json.loads(selected)
        except json.JSONDecodeError as exc:
            raise ValueError("risk_programs 必须是 JSON 数组") from exc
    if not isinstance(selected, list):
        raise ValueError("risk_programs 必须是数组")

    available = _available_by_id(host_strategy_cls, frame_type)
    normalized: list[tuple[int, int, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, item in enumerate(selected):
        normalized.append(_normalize_risk_item(item, index, available, seen))

    normalized.sort(key=lambda row: (row[0], row[1]))
    return [{**item, "priority": priority} for priority, (_, _, item) in enumerate(normalized)]


def risk_program_names(
    selected: Any,
    *,
    host_strategy_cls: type[BaseStrategy] | None = None,
    frame_type: FrameType | str = FrameType.DAY,
) -> list[str]:
    """Return names while marking persisted IDs unavailable in this CE host."""
    available = _available_by_id(host_strategy_cls, frame_type)
    names: list[str] = []
    for item in selected or []:
        program_id = str(item.get("id") if isinstance(item, dict) else item)
        metadata = available.get(program_id)
        names.append(str(metadata["name"]) if metadata is not None else f"不可用（{program_id}）")
    return names


def build_backtest_risk_overlay(
    strategy_cls: type[BaseStrategy],
    config: dict[str, Any],
    frame_type: FrameType | str,
) -> CompositeRiskOverlay | None:
    """Build an ordered composite from selected adapters, if any."""
    selected = normalize_risk_programs(
        config.get(RISK_PROGRAMS_KEY, []),
        host_strategy_cls=strategy_cls,
        frame_type=frame_type,
    )
    overlays: list[Any] = []
    for item in selected:
        adapter = risk_program_registry.get(str(item["id"]))
        if adapter is None or adapter.overlay_factory is None:
            raise ValueError(f"风控程序缺少回测适配器: {item['id']}")
        overlays.append(adapter.overlay_factory(dict(item["params"])))
    if not overlays:
        return None
    return CompositeRiskOverlay(
        overlays,
        allow_same_bar_repurchase=bool(config.get(ALLOW_SAME_BAR_REPURCHASE_KEY, True)),
    )


def _declared_live_adapter(
    strategy_cls: type[BaseStrategy],
    frame_type: FrameType | str,
) -> RiskProgramAdapter | None:
    """Resolve a host's ``RISK_OVERLAY`` declaration through the registry."""
    declaration = getattr(strategy_cls, "RISK_OVERLAY", None)
    if not declaration or isinstance(declaration, bool):
        return None
    adapter = risk_program_registry.get(str(declaration).strip())
    if adapter is None or adapter.live_strategy_factory is None:
        return None
    if not adapter.supports(strategy_cls, frame_type):
        return None
    return adapter


def _legacy_live_enabled(
    strategy_cls: type[BaseStrategy],
    config: dict[str, Any],
) -> bool:
    """Honor the legacy explicit opt-out for host-declared live risk."""
    if "use_broker_barriers" in config:
        return bool(config["use_broker_barriers"])
    defaults = getattr(strategy_cls, "default_config", None)
    if callable(defaults):
        return bool(defaults().get("use_broker_barriers", True))
    return True


def build_live_risk_strategies(
    strategy_cls: type[BaseStrategy],
    broker: Any,
    config: dict[str, Any],
    frame_type: FrameType | str = FrameType.DAY,
) -> list[Any]:
    """Instantiate explicitly selected live adapters or declared host overlays."""
    if RISK_PROGRAMS_KEY not in config:
        adapter = _declared_live_adapter(strategy_cls, frame_type)
        if (
            adapter is None
            or adapter.live_strategy_factory is None
            or not _legacy_live_enabled(strategy_cls, config)
        ):
            return []
        return [adapter.live_strategy_factory(broker, dict(config))]
    selected = normalize_risk_programs(
        config.get(RISK_PROGRAMS_KEY, []),
        host_strategy_cls=strategy_cls,
        frame_type=frame_type,
    )
    strategies: list[Any] = []
    for item in selected:
        adapter = risk_program_registry.get(str(item["id"]))
        if adapter is None or adapter.live_strategy_factory is None:
            raise ValueError(f"风控程序缺少实时适配器: {item['id']}")
        strategies.append(adapter.live_strategy_factory(broker, dict(item["params"])))
    return strategies

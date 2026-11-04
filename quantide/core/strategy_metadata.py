"""Immutable discovered-strategy metadata and its shared legacy field schema."""

from dataclasses import dataclass, field, fields
from typing import Any, Literal


@dataclass(frozen=True)
class StrategyMetadata:
    """策略元数据 (FR-020)."""

    strategy_id: str
    name: str
    description: str
    strategy_type: Literal["independent", "risk"]
    module: str
    is_builtin: bool
    default_config: dict[str, Any] = field(default_factory=dict)


def metadata_annotations() -> dict[str, Any]:
    """Share fields with the mutable persistence DTO without dataclass inheritance."""
    return {item.name: item.type for item in fields(StrategyMetadata)}

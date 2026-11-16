"""Immutable discovered-strategy metadata and its shared legacy field schema."""

from dataclasses import dataclass, field
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

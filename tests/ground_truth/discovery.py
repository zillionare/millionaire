"""Ground truth implementations of FR-020 (Strategy discovery).

Same purity rules as tests/ground_truth/calendar.py: NO `quantide.*` imports.

These functions replicate what `quantide.service.discovery.enumerate_strategies`
should do, computed by walking the strategy directory directly. Used to verify
the impl's enumeration output.
"""
from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Type


@dataclass
class ExpectedStrategyMetadata:
    """Expected structure of a discovered strategy (matches impl's StrategyMetadata)."""
    name: str
    qualified_name: str
    strategy_type: str
    module: str
    file_path: str
    base_classes: list[str] = field(default_factory=list)
    param_specs: list[dict[str, Any]] = field(default_factory=list)


def is_strategy_class(obj: Any) -> bool:
    """Return True iff obj is a Strategy subclass (excludes RiskStrategy).

    A class is a Strategy subclass iff:
      - it is a class
      - it has at least one base whose name is in {Strategy, BaseStrategy}
      - it is NOT a subclass of RiskStrategy
    """
    if not inspect.isclass(obj):
        return False
    bases = [b.__name__ for b in obj.__mro__]
    if "Strategy" not in bases and "BaseStrategy" not in bases:
        return False
    if "RiskStrategy" in bases:
        return False
    return True


def enumerate_strategies_from_module(module_name: str) -> list[ExpectedStrategyMetadata]:
    """Import a module and return all Strategy subclasses found in it.

    Returned metadata matches impl's StrategyMetadata shape (test plan §1.2).
    Excludes RiskStrategy descendants per spec (FR-020 only enumerates Strategy).
    """
    mod = importlib.import_module(module_name)
    out: list[ExpectedStrategyMetadata] = []

    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ != module_name:
            continue
        if not is_strategy_class(obj):
            continue
        bases = [b.__name__ for b in obj.__mro__[1:]]
        out.append(ExpectedStrategyMetadata(
            name=name,
            qualified_name=f"{module_name}.{name}",
            strategy_type="base" if "BaseStrategy" in bases else "abstract",
            module=module_name,
            file_path=inspect.getfile(obj),
            base_classes=bases,
            param_specs=_extract_param_specs(obj),
        ))
    return out


def enumerate_strategies_from_directory(patterns: list[str]) -> list[ExpectedStrategyMetadata]:
    """Walk a list of module name patterns and enumerate strategies from each.

    patterns: list of module names (e.g. ['quantide.strategies.demo']).
    """
    out: list[ExpectedStrategyMetadata] = []
    for p in patterns:
        out.extend(enumerate_strategies_from_module(p))
    return out


def _extract_param_specs(cls: Type) -> list[dict[str, Any]]:
    """Extract ParamSpec-style metadata from class annotations + defaults.

    Looks for __init__ params (excluding `self`) with type annotation AND/OR
    default. Returns list of {name, type, default, required} dicts.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return []
    out: list[dict[str, Any]] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        type_name = (
            param.annotation.__name__
            if hasattr(param.annotation, "__name__")
            else str(param.annotation)
        )
        has_default = param.default is not inspect.Parameter.empty
        out.append({
            "name": pname,
            "type": type_name,
            "default": param.default if has_default else None,
            "required": not has_default,
        })
    return out

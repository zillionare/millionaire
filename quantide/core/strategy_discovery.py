"""FR-020 自动发现策略.

按 spec-strategy.md §FR-020:
- 框架从用户配置的策略根目录中枚举用户编写的策略类
- 枚举目标: BaseStrategy / RiskStrategy 的所有子类
- 内置策略同样参与枚举 (FR-090/100/110)
- 元数据 schema: strategy_id, name, description, strategy_type, module, is_builtin, default_config
- EnumerationResult 返回 (含 diagnostics 收集) — 失败 / 跳过 / 冲突等均记录

实施:
- quantide.core.strategy_discovery.StrategyDiscovery.discover(root_path)
- 返回 EnumerationResult
- 不递归子目录; 容错策略按 spec
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Literal

from quantide.core.strategy_metadata import StrategyMetadata as StrategyMetadata

if TYPE_CHECKING:
    from quantide.core.strategy import Strategy


class SkippedReason(StrEnum):
    """跳过原因 (FR-020 diagnostics)."""

    NotAStrategy = "NotAStrategy"
    InvalidConfig = "InvalidConfig"
    SyntaxError = "SyntaxError"
    ImportError = "ImportError"
    PermissionDenied = "PermissionDenied"
    BuiltinOverridden = "BuiltinOverridden"


@dataclass(frozen=True)
class SkippedEntry:
    """跳过条目 (FR-020 diagnostics)."""

    path: str
    class_name: str | None
    reason: SkippedReason
    detail: str


@dataclass(frozen=True)
class EnumerationResult:
    """枚举结果 (FR-020) — 包含 strategies + diagnostics."""

    strategies: list[StrategyMetadata]
    diagnostics: list[SkippedEntry] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.strategies)

    def __iter__(self) -> Iterator[StrategyMetadata]:
        return iter(self.strategies)


def _file_diagnostic(
    path: str | Path,
    reason: SkippedReason,
    detail: str,
    class_name: str | None = None,
) -> SkippedEntry:
    return SkippedEntry(path=str(path), class_name=class_name, reason=reason, detail=detail)


def _import_strategy_source(
    path: Path,
) -> tuple[ModuleType | None, list[SkippedEntry]]:
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(f"_strategy_{path.stem}_{id(path)}", path)
    if spec is None or spec.loader is None:
        return None, [
            _file_diagnostic(
                path, SkippedReason.ImportError, "spec_from_file_location returned None"
            )
        ]
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except SyntaxError as exc:
        return None, [_file_diagnostic(path, SkippedReason.SyntaxError, str(exc))]
    except ImportError as exc:
        return None, [_file_diagnostic(path, SkippedReason.ImportError, str(exc))]
    except Exception as exc:
        return None, [
            _file_diagnostic(path, SkippedReason.ImportError, f"{type(exc).__name__}: {exc}")
        ]
    return module, []


def _strategy_default_config(
    strategy: type[Strategy], path: Path, diagnostics: list[SkippedEntry]
) -> dict[str, Any]:
    try:
        config = strategy.default_config()
        if isinstance(config, dict):
            return config
        detail = f"default_config() returned non-dict: {type(config).__name__}"
    except Exception as exc:
        detail = str(exc)
    diagnostics.append(
        _file_diagnostic(path, SkippedReason.InvalidConfig, detail, strategy.__name__)
    )
    return {}


def _enumerate_module_strategies(
    module: ModuleType,
    path: Path,
    base_cls: type[Strategy],
    risk_cls: type[Strategy],
) -> tuple[list[StrategyMetadata], list[SkippedEntry]]:
    strategies, diagnostics = [], []
    for _, strategy in inspect.getmembers(module, inspect.isclass):
        if strategy.__module__ != module.__name__ or strategy in (base_cls, risk_cls):
            continue
        kind: Literal["risk", "independent"]
        if issubclass(strategy, risk_cls):
            kind = "risk"
        elif issubclass(strategy, base_cls):
            kind = "independent"
        else:
            diagnostics.append(
                _file_diagnostic(
                    path,
                    SkippedReason.NotAStrategy,
                    f"class {strategy.__name__} does not inherit BaseStrategy/RiskStrategy",
                    strategy.__name__,
                )
            )
            continue
        strategies.append(
            StrategyMetadata(
                strategy_id=f"{strategy.__module__}.{strategy.__name__}",
                name=getattr(strategy, "__display_name__", None) or strategy.__name__,
                description=(inspect.getdoc(strategy) or "").split("\n")[0],
                strategy_type=kind,
                module=strategy.__module__,
                is_builtin="quantide.strategies" in strategy.__module__,
                default_config=_strategy_default_config(strategy, path, diagnostics),
            )
        )
    return strategies, diagnostics


class StrategyDiscovery:
    """策略发现 (FR-020)."""

    @staticmethod
    def discover(root_path: str | Path) -> EnumerationResult:
        """枚举 root_path 下所有策略类 (不递归子目录, FR-020).

        Args:
            root_path: 策略根目录 (用户配置 或 内置 quantide/strategies)

        Returns:
            EnumerationResult 含 strategies + diagnostics
        """
        from quantide.core.strategy import BaseStrategy, RiskStrategy

        root = Path(root_path)
        if not root.exists():
            return EnumerationResult(
                strategies=[],
                diagnostics=[
                    SkippedEntry(
                        path=str(root),
                        class_name=None,
                        reason=SkippedReason.PermissionDenied,
                        detail=f"directory does not exist: {root}",
                    )
                ],
            )

        strategies: list[StrategyMetadata] = []
        diagnostics: list[SkippedEntry] = []
        for py_file in sorted(root.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                file_strategies, file_diags = StrategyDiscovery._load_strategies_from_file(
                    py_file, BaseStrategy, RiskStrategy
                )
                strategies.extend(file_strategies)
                diagnostics.extend(file_diags)
            except SyntaxError as e:
                diagnostics.append(
                    SkippedEntry(
                        path=str(py_file),
                        class_name=None,
                        reason=SkippedReason.SyntaxError,
                        detail=str(e),
                    )
                )
            except ImportError as e:
                diagnostics.append(
                    SkippedEntry(
                        path=str(py_file),
                        class_name=None,
                        reason=SkippedReason.ImportError,
                        detail=str(e),
                    )
                )
        return EnumerationResult(strategies=strategies, diagnostics=diagnostics)

    @staticmethod
    def _load_strategies_from_file(
        py_file: Path, base_cls: type[Strategy], risk_cls: type[Strategy]
    ) -> tuple[list[StrategyMetadata], list[SkippedEntry]]:
        """Import one strategy source and classify only classes defined by that source."""
        module, diagnostics = _import_strategy_source(py_file)
        if module is None:
            return [], diagnostics
        return _enumerate_module_strategies(module, py_file, base_cls, risk_cls)

    @staticmethod
    def discover_builtin() -> EnumerationResult:
        """发现 CE 内置示例策略。风险程序由宿主显式注册。"""
        from quantide.strategies.example import dual_ma

        return StrategyDiscovery.discover(Path(dual_ma.__file__).parent)

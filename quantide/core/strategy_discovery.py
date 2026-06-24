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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal


class SkippedReason(str, Enum):
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
class StrategyMetadata:
    """策略元数据 (FR-020)."""

    strategy_id: str
    name: str
    description: str
    strategy_type: Literal["independent", "risk"]
    module: str
    is_builtin: bool
    default_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnumerationResult:
    """枚举结果 (FR-020) — 包含 strategies + diagnostics."""

    strategies: list[StrategyMetadata]
    diagnostics: list[SkippedEntry] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.strategies)

    def __iter__(self):
        return iter(self.strategies)


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
            return EnumerationResult(strategies=[], diagnostics=[
                SkippedEntry(
                    path=str(root),
                    class_name=None,
                    reason=SkippedReason.PermissionDenied,
                    detail=f"directory does not exist: {root}",
                )
            ])

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
                diagnostics.append(SkippedEntry(
                    path=str(py_file), class_name=None,
                    reason=SkippedReason.SyntaxError, detail=str(e),
                ))
            except ImportError as e:
                diagnostics.append(SkippedEntry(
                    path=str(py_file), class_name=None,
                    reason=SkippedReason.ImportError, detail=str(e),
                ))
        return EnumerationResult(strategies=strategies, diagnostics=diagnostics)

    @staticmethod
    def _load_strategies_from_file(
        py_file: Path, base_cls, risk_cls
    ) -> tuple[list[StrategyMetadata], list[SkippedEntry]]:
        """从 .py 文件加载策略类, 返回 (strategies, diagnostics)."""
        importlib.invalidate_caches()
        spec = importlib.util.spec_from_file_location(
            f"_strategy_{py_file.stem}_{id(py_file)}", py_file
        )
        if spec is None or spec.loader is None:
            return [], [SkippedEntry(
                path=str(py_file), class_name=None,
                reason=SkippedReason.ImportError, detail="spec_from_file_location returned None",
            )]
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except SyntaxError as e:
            return [], [SkippedEntry(
                path=str(py_file), class_name=None,
                reason=SkippedReason.SyntaxError, detail=str(e),
            )]
        except ImportError as e:
            return [], [SkippedEntry(
                path=str(py_file), class_name=None,
                reason=SkippedReason.ImportError, detail=str(e),
            )]
        except Exception as e:
            return [], [SkippedEntry(
                path=str(py_file), class_name=None,
                reason=SkippedReason.ImportError, detail=f"{type(e).__name__}: {e}",
            )]

        strategies: list[StrategyMetadata] = []
        diagnostics: list[SkippedEntry] = []
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if obj in (base_cls, risk_cls):
                continue
            if issubclass(obj, risk_cls):
                strategy_type: Literal["independent", "risk"] = "risk"
            elif issubclass(obj, base_cls):
                strategy_type = "independent"
            else:
                diagnostics.append(SkippedEntry(
                    path=str(py_file), class_name=obj.__name__,
                    reason=SkippedReason.NotAStrategy,
                    detail=f"class {obj.__name__} does not inherit BaseStrategy/RiskStrategy",
                ))
                continue

            display_name = getattr(obj, "__display_name__", None) or obj.__name__
            docstring = inspect.getdoc(obj) or ""
            description = docstring.split("\n")[0] if docstring else ""
            module_path = obj.__module__
            is_builtin = "quantide.strategies" in module_path

            try:
                default_cfg = obj.default_config()
                if not isinstance(default_cfg, dict):
                    diagnostics.append(SkippedEntry(
                        path=str(py_file), class_name=obj.__name__,
                        reason=SkippedReason.InvalidConfig,
                        detail=f"default_config() returned non-dict: {type(default_cfg).__name__}",
                    ))
                    default_cfg = {}
            except Exception as e:
                diagnostics.append(SkippedEntry(
                    path=str(py_file), class_name=obj.__name__,
                    reason=SkippedReason.InvalidConfig, detail=str(e),
                ))
                default_cfg = {}

            strategy_id = f"{module_path}.{obj.__name__}"
            strategies.append(
                StrategyMetadata(
                    strategy_id=strategy_id,
                    name=display_name,
                    description=description,
                    strategy_type=strategy_type,
                    module=module_path,
                    is_builtin=is_builtin,
                    default_config=default_cfg,
                )
            )
        return strategies, diagnostics

    @staticmethod
    def discover_builtin() -> EnumerationResult:
        """发现内置策略 (FR-090/100/110) — 合并多个目录的 EnumerationResult."""
        from quantide.strategies.example import dual_ma
        from quantide.strategies import pullback_sell, cost_stop_loss

        all_strategies: list[StrategyMetadata] = []
        all_diags: list[SkippedEntry] = []
        for path in (dual_ma.__file__, pullback_sell.__file__, cost_stop_loss.__file__):
            res = StrategyDiscovery.discover(Path(path).parent)
            all_strategies.extend(res.strategies)
            all_diags.extend(res.diagnostics)
        return EnumerationResult(strategies=all_strategies, diagnostics=all_diags)
"""FR-020 自动发现策略.

按 spec-strategy.md §FR-020:
- 框架从用户配置的策略根目录中枚举用户编写的策略类
- 枚举目标: BaseStrategy / RiskStrategy 的所有子类
- 内置策略同样参与枚举 (FR-090/100/110)
- 元数据 schema: strategy_id, name, description, strategy_type, module, is_builtin, default_config

实施:
- quantide.core.strategy_discovery.StrategyDiscovery.discover(root_path)
- 返回 list[StrategyMetadata]
- 不递归子目录; 容错策略按 spec
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from dataclasses import dataclass, field
from pathlib import Path
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


class StrategyDiscovery:
    """策略发现 (FR-020)."""

    @staticmethod
    def discover(root_path: str | Path) -> list[StrategyMetadata]:
        """枚举 root_path 下所有策略类 (不递归子目录, FR-020).

        Args:
            root_path: 策略根目录 (用户配置 或 内置 quantide/strategies)

        Returns:
            list[StrategyMetadata]
        """
        from quantide.core.strategy import BaseStrategy, RiskStrategy

        root = Path(root_path)
        if not root.exists():
            return []

        results: list[StrategyMetadata] = []
        for py_file in root.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                strategies = StrategyDiscovery._load_strategies_from_file(
                    py_file, root, BaseStrategy, RiskStrategy
                )
                results.extend(strategies)
            except (SyntaxError, ImportError):
                continue
        return results

    @staticmethod
    def _load_strategies_from_file(
        py_file: Path, root: Path, base_cls, risk_cls
    ) -> list[StrategyMetadata]:
        """从 .py 文件加载策略类.

        Args:
            py_file: .py 文件路径
            root: 策略根目录 (用于推导 module 名)
            base_cls: BaseStrategy 类
            risk_cls: RiskStrategy 类

        Returns:
            该文件中所有策略元数据
        """
        spec = importlib.util.spec_from_file_location(
            f"_strategy_{py_file.stem}", py_file
        )
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception:
            return []

        results: list[StrategyMetadata] = []
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
                continue

            display_name = getattr(obj, "__display_name__", None) or obj.__name__
            docstring = inspect.getdoc(obj) or ""
            description = docstring.split("\n")[0] if docstring else ""
            module_path = obj.__module__
            is_builtin = "quantide.strategies" in module_path

            try:
                default_cfg = obj.default_config()
            except Exception:
                default_cfg = {}

            strategy_id = f"{module_path}.{obj.__name__}"
            results.append(
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
        return results

    @staticmethod
    def discover_builtin() -> list[StrategyMetadata]:
        """发现内置策略 (FR-090/100/110).

        Returns:
            内置策略元数据列表
        """
        from quantide.strategies.example import dual_ma
        from quantide.strategies import pullback_sell, cost_stop_loss

        return StrategyDiscovery.discover(dual_ma.__file__).__class__ == list and (
            StrategyDiscovery.discover(dual_ma.__file__)
            + StrategyDiscovery.discover(pullback_sell.__file__)
            + StrategyDiscovery.discover(cost_stop_loss.__file__)
        ) or (  # simplify: just merge all
            []
        )
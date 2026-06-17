"""策略扫描与内置示例管理 (v0.2 spec)"""

import importlib
import inspect
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from quantide.core.strategy import BaseStrategy, RiskStrategy, Strategy
from quantide.data.models.strategy_config import (
    SKIP_INVALID_CONFIG,
    SKIP_NOT_A_STRATEGY,
    EnumerationResult,
    ParamSpec,
    SkippedEntry,
    StrategyConfig,
    StrategyInfo,
    StrategyMetadata,
)
from quantide.data.sqlite import db


@dataclass(frozen=True)
class ScanSource:
    """策略扫描源。"""

    directory: Path
    module_prefix: str | None = None


@dataclass(frozen=True)
class ExampleCopyResult:
    """示例策略复制结果。"""

    copied_files: list[str]
    skipped_files: list[str]

    @property
    def copied_count(self) -> int:
        """返回已复制文件数。"""
        return len(self.copied_files)

    @property
    def skipped_count(self) -> int:
        """返回跳过文件数。"""
        return len(self.skipped_files)


class StrategyLoader:
    """管理策略扫描、缓存与内置示例复制。"""

    def __init__(self) -> None:
        self._strategies: dict[str, type[Strategy]] = {}
        self._builtin_example_dir = (
            Path(__file__).resolve().parents[1] / "strategies" / "example"
        ).resolve()
        self._builtin_module_prefix = "quantide.strategies.example"

    def get_builtin_scan_directory(self) -> str:
        """返回内置示例策略目录。"""
        return str(self._builtin_example_dir)

    def get_user_scan_directory(self) -> str:
        """返回用户配置的策略目录。"""
        try:
            rows = list(db["strategy_config"].rows_where("key = ?", ("scan_directory",)))
            if rows:
                return (rows[0].get("value") or "").strip()
        except Exception as e:
            logger.warning(f"Failed to get scan directory from db: {e}")
        return ""

    def get_scan_directory(self) -> str:
        """返回当前主扫描目录。

        优先返回用户配置目录；未配置时回退到内置示例目录。
        """
        return self.get_user_scan_directory() or self.get_builtin_scan_directory()

    def get_scan_directories(self) -> list[str]:
        """返回实际参与扫描的目录列表。"""
        directories = [self.get_builtin_scan_directory()]
        user_dir = self.get_user_scan_directory()
        if not user_dir:
            return directories

        resolved_user_dir = str(Path(user_dir).expanduser().resolve())
        if resolved_user_dir not in directories:
            directories.append(resolved_user_dir)
        return directories

    def has_scan_directory_config(self) -> bool:
        """判断是否已显式配置扫描目录"""
        try:
            rows = list(db["strategy_config"].rows_where("key = ?", ("scan_directory",)))
            if not rows:
                return False
            return (rows[0].get("value") or "").strip() != ""
        except Exception as e:
            logger.warning(f"Failed to check scan directory config: {e}")
            return False

    def set_scan_directory(self, directory: str) -> None:
        """设置扫描目录"""
        from datetime import datetime

        existing_rows = list(
            db["strategy_config"].rows_where("key = ?", ("scan_directory",))
        )
        existing_id = existing_rows[0]["id"] if existing_rows else None

        config = StrategyConfig(
            id=existing_id or StrategyConfig().id,
            key="scan_directory",
            value=directory,
            updated_at=datetime.now(),
        )
        db["strategy_config"].upsert(config.to_dict(), pk="key")
        logger.info(f"Scan directory set to: {directory}")

    def load_from_cache(self) -> dict[str, type[Strategy]]:
        """从数据库缓存加载策略"""
        self._strategies = {}

        try:
            rows = list(db["strategy_info"].rows)

            for row in rows:
                try:
                    module_name = row["module_path"]
                    class_name = row["name"]
                    scan_dir = str(row.get("scan_dir") or "").strip()

                    if scan_dir and not module_name.startswith("quantide."):
                        self._add_scan_dir_to_sys_path(scan_dir)

                    # 导入模块
                    if module_name in sys.modules:
                        module = importlib.reload(sys.modules[module_name])
                    else:
                        module = importlib.import_module(module_name)

                    # 获取策略类
                    strategy_class = getattr(module, class_name, None)
                    if strategy_class and inspect.isclass(strategy_class):
                        is_valid = (
                            (issubclass(strategy_class, BaseStrategy) and strategy_class not in (BaseStrategy, Strategy))
                            or (issubclass(strategy_class, RiskStrategy) and strategy_class not in (RiskStrategy, Strategy))
                        )
                        if is_valid:
                            self._strategies[class_name] = strategy_class
                            logger.debug(f"Loaded strategy from cache: {class_name}")
                except Exception as e:
                    logger.error(f"Failed to load strategy from cache: {row.get('name', 'unknown')}: {e}")

        except Exception as e:
            logger.warning(f"Failed to load strategies from cache: {e}")

        return self._strategies

    def scan_and_cache(
        self,
        workspace_path: str | None = None,
    ) -> dict[str, type[Strategy]]:
        """扫描目录并缓存到数据库"""
        # 清空现有缓存
        self._clear_cache()

        scanned_strategies: dict[str, StrategyInfo] = {}
        for source in self._get_scan_sources(workspace_path):
            for name, strategy_info in self._scan_source(source).items():
                existing = scanned_strategies.get(name)
                if existing is not None:
                    logger.warning(
                        "Duplicate strategy name {} found in {} and {}. Using later source.",
                        name,
                        existing.scan_dir,
                        strategy_info.scan_dir,
                    )
                scanned_strategies[name] = strategy_info

        # 保存到数据库
        for strategy_info in scanned_strategies.values():
            try:
                db["strategy_info"].insert(strategy_info.to_dict(), pk=StrategyInfo.__pk__)
            except Exception as e:
                logger.error(f"Failed to cache strategy {strategy_info.name}: {e}")

        # 重新加载到内存
        return self.load_from_cache()

    def _clear_cache(self) -> None:
        """清空策略缓存"""
        try:
            # 删除所有策略信息
            db["strategy_info"].delete_where("1=1")
            logger.info("Strategy cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    def _add_scan_dir_to_sys_path(self, scan_dir: str) -> None:
        """将扫描目录加入 sys.path。"""
        str_path = str(Path(scan_dir).expanduser().resolve())
        if str_path not in sys.path:
            sys.path.insert(0, str_path)
            logger.info(f"Added {str_path} to sys.path")

    def _get_scan_sources(self, workspace_path: str | None = None) -> list[ScanSource]:
        """构建扫描源列表。"""
        if workspace_path:
            workspace = Path(workspace_path).expanduser().resolve()
            if workspace == self._builtin_example_dir:
                return [
                    ScanSource(
                        directory=workspace,
                        module_prefix=self._builtin_module_prefix,
                    )
                ]
            return [ScanSource(directory=workspace)]

        sources = [
            ScanSource(
                directory=self._builtin_example_dir,
                module_prefix=self._builtin_module_prefix,
            )
        ]
        user_dir = self.get_user_scan_directory()
        if not user_dir:
            return sources

        workspace = Path(user_dir).expanduser().resolve()
        if workspace != self._builtin_example_dir:
            sources.append(ScanSource(directory=workspace))
        return sources

    def _scan_source(self, source: ScanSource) -> dict[str, StrategyInfo]:
        """扫描单个目录源。"""
        if not source.directory.exists():
            logger.warning(f"Workspace path does not exist: {source.directory}")
            return {}

        if source.module_prefix is None:
            self._add_scan_dir_to_sys_path(str(source.directory))

        scanned: dict[str, StrategyInfo] = {}
        # spec FR-020 AC-020-02: 不递归子目录;仅顶层 .py 文件
        for file in sorted(source.directory.iterdir()):
            if not file.is_file() or not file.name.endswith(".py") or file.name.startswith("__"):
                continue
            file_path = file
            try:
                module_name = self._get_module_name(
                    source.directory,
                    file_path,
                    source.module_prefix,
                )
                strategies = self._load_module_and_get_info(
                    module_name,
                    str(source.directory),
                )
                for strategy_info in strategies:
                    scanned[strategy_info.name] = strategy_info
            except Exception as e:
                logger.error(f"Failed to process file {file_path}: {e}")
        return scanned

    def _get_module_name(
        self,
        root: Path,
        file_path: Path,
        module_prefix: str | None = None,
    ) -> str:
        """根据文件路径计算模块名。"""
        rel_path = file_path.relative_to(root)
        module_name = str(rel_path).replace(os.sep, ".")[:-3]
        if not module_prefix:
            return module_name
        return f"{module_prefix}.{module_name}"

    def _load_module_and_get_info(self, module_name: str, scan_dir: str) -> list[StrategyInfo]:
        """加载模块并获取策略信息"""
        from datetime import datetime

        strategies = []

        try:
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module):
                if not inspect.isclass(obj):
                    continue
                is_base = issubclass(obj, BaseStrategy) and obj not in (BaseStrategy, Strategy)
                is_risk = issubclass(obj, RiskStrategy) and obj not in (RiskStrategy, Strategy)
                if not is_base and not is_risk:
                    continue
                file_path = inspect.getfile(obj)
                params = {}
                if hasattr(obj, "params") and obj.params:
                    params = obj.params
                strategy_type = "risk" if is_risk else "independent"

                strategy_info = StrategyInfo(
                    name=name,
                    module_path=module_name,
                    file_path=file_path,
                    description=getattr(obj, "__doc__", "") or "",
                    version=getattr(obj, "version", "1.0.0"),
                    params=json.dumps(params, ensure_ascii=False),
                    scan_dir=scan_dir,
                    scanned_at=datetime.now(),
                    strategy_type=strategy_type,
                )
                strategies.append(strategy_info)
                logger.debug(f"Scanned strategy: {name} ({strategy_type}) from {module_name}")
        except Exception as e:
            # 不抛出异常，以免一个文件错误导致整个加载失败
            logger.debug(f"Failed to load module {module_name}: {e}")

        return strategies

    def load(self, workspace_path: str | None = None) -> dict[str, type[Strategy]]:
        """加载策略（优先从缓存）"""
        # 先尝试从缓存加载
        cached = self.load_from_cache()
        if cached:
            logger.info(f"Loaded {len(cached)} strategies from cache")
            return cached

        # 缓存为空，执行扫描
        logger.info("Cache empty, scanning directory...")
        return self.scan_and_cache(workspace_path)

    def get_strategy_info(self, name: str) -> StrategyInfo | None:
        """获取策略详细信息"""
        try:
            rows = list(db["strategy_info"].rows_where("name = ?", (name,)))
            if rows:
                return StrategyInfo(**rows[0])
        except Exception as e:
            logger.error(f"Failed to get strategy info: {e}")
        return None

    def list_strategies(self) -> list[StrategyInfo]:
        """列出所有已缓存的策略"""
        try:
            rows = list(db["strategy_info"].rows)
            return [StrategyInfo(**row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list strategies: {e}")
        return []

    def copy_examples_to_directory(self, directory: str | Path) -> ExampleCopyResult:
        """复制内置示例策略到目标目录。

        Args:
            directory: 用户策略目录。

        Returns:
            复制结果。
        """
        destination = Path(directory).expanduser().resolve()
        if not destination.exists():
            raise FileNotFoundError(f"目录不存在: {destination}")
        if not destination.is_dir():
            raise NotADirectoryError(f"路径不是目录: {destination}")

        copied_files: list[str] = []
        skipped_files: list[str] = []
        for source_file in self._iter_copyable_example_files():
            rel_path = source_file.relative_to(self._builtin_example_dir)
            target_file = destination / rel_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            if target_file.exists():
                skipped_files.append(str(rel_path))
                continue

            shutil.copy2(source_file, target_file)
            copied_files.append(str(rel_path))

        return ExampleCopyResult(
            copied_files=copied_files,
            skipped_files=skipped_files,
        )

    def _iter_copyable_example_files(self) -> list[Path]:
        """返回可复制的内置示例文件列表。"""
        if not self._builtin_example_dir.exists():
            raise FileNotFoundError(f"内置示例目录不存在: {self._builtin_example_dir}")

        return [
            file_path
            for file_path in sorted(self._builtin_example_dir.rglob("*"))
            if file_path.is_file()
            and "__pycache__" not in file_path.parts
            and file_path.suffix != ".pyc"
        ]


strategy_loader = StrategyLoader()


# ─────────────────── v0.2 spec FR-020 接口 ───────────────────


_BUILTIN_MODULE_PREFIX = "quantide.examples"


def _classify_strategy(cls) -> str | None:
    """v0.2 spec: BaseStrategy 子类 → "independent", RiskStrategy 子类 → "risk"
    排除 Strategy/BaseStrategy/RiskStrategy 自身.
    """
    from quantide.core.strategy import BaseStrategy, RiskStrategy, Strategy

    if not inspect.isclass(cls):
        return None
    if cls is BaseStrategy or cls is RiskStrategy or cls is Strategy:
        return None
    try:
        if issubclass(cls, RiskStrategy):
            return "risk"
        if issubclass(cls, BaseStrategy):
            return "independent"
    except TypeError:
        return None
    return None


def _to_param_spec(params: dict) -> dict:
    """v0.2 spec: default_config dict → dict[str, ParamSpec]"""
    result = {}
    for key, value in (params or {}).items():
        result[key] = ParamSpec(
            name=key,
            default=value,
            type_hint=None,
            description=None,
            constraints=None,
        )
    return result


def _is_builtin_class(cls) -> bool:
    """v0.2 spec: 框架包内 (quantide.*) 的类视为内置"""
    module = getattr(cls, "__module__", "") or ""
    return module.startswith("quantide.") and not module.startswith("quantide.examples.")


def is_builtin_path(path: str | Path) -> bool:
    """v0.2 spec: 路径在 quantide 框架包内视为内置目录"""
    p = Path(path).expanduser().resolve()
    quantide_root = Path(__file__).resolve().parent.parent
    try:
        p.relative_to(quantide_root)
        return True
    except ValueError:
        return False


def enumerate_strategies(
    root: str | Path | None = None,
    include_builtin: bool = True,
) -> EnumerationResult:
    """v0.2 spec FR-020: 枚举策略类

    Args:
        root: 用户策略目录 (None 表示未配置).
        include_builtin: 是否包含内置策略.

    Returns:
        EnumerationResult(strategies, diagnostics).
    """
    strategies: list[StrategyMetadata] = []
    diagnostics: list[SkippedEntry] = []

    if root is None:
        if include_builtin:
            builtin_root = Path(__file__).resolve().parent.parent / "examples"
            if builtin_root.exists():
                result = _enumerate_dir(builtin_root, is_builtin=True)
                strategies.extend(result[0])
                diagnostics.extend(result[1])
        return EnumerationResult(strategies=strategies, diagnostics=diagnostics)

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        diagnostics.append(SkippedEntry(
            path=str(root),
            class_name=None,
            reason="PermissionDenied",
            detail=f"directory does not exist: {root}",
        ))
        return EnumerationResult(strategies=strategies, diagnostics=diagnostics)

    user_strategies, user_diags = _enumerate_dir(root_path, is_builtin=False)
    strategies.extend(user_strategies)
    diagnostics.extend(user_diags)

    if include_builtin:
        builtin_root = Path(__file__).resolve().parent.parent / "examples"
        if builtin_root.exists() and builtin_root.resolve() != root_path:
            result = _enumerate_dir(builtin_root, is_builtin=True)
            strategies.extend(result[0])
            diagnostics.extend(result[1])

    return EnumerationResult(strategies=strategies, diagnostics=diagnostics)


def _enumerate_dir(
    directory: Path, is_builtin: bool
) -> tuple[list[StrategyMetadata], list[SkippedEntry]]:
    """扫描单个目录,返回 (strategies, diagnostics)"""
    strategies: list[StrategyMetadata] = []
    diagnostics: list[SkippedEntry] = []

    if not is_builtin:
        sys.path.insert(0, str(directory))

    for file in sorted(directory.iterdir()):
        if not file.is_file() or not file.name.endswith(".py") or file.name.startswith("__"):
            continue
        file_path = file
        try:
            module_name = (
                f"{_BUILTIN_MODULE_PREFIX}.{file.stem}" if is_builtin
                else file.stem
            )
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
        except SyntaxError as e:
            diagnostics.append(SkippedEntry(
                path=str(file_path),
                class_name=None,
                reason="SyntaxError",
                detail=f"line {e.lineno}: {e.msg}",
            ))
            continue
        except (ImportError, ModuleNotFoundError) as e:
            diagnostics.append(SkippedEntry(
                path=str(file_path),
                class_name=None,
                reason="ImportError",
                detail=str(e),
            ))
            continue
        except Exception as e:
            diagnostics.append(SkippedEntry(
                path=str(file_path),
                class_name=None,
                reason="ModuleInitError",
                detail=str(e),
            ))
            continue

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module_name:
                continue
            strategy_type = _classify_strategy(obj)
            if strategy_type is None:
                diagnostics.append(SkippedEntry(
                    path=str(file_path),
                    class_name=name,
                    reason=SKIP_NOT_A_STRATEGY,
                    detail="class is not a BaseStrategy/RiskStrategy subclass",
                ))
                continue
            try:
                params = obj.default_config()
            except Exception as e:
                diagnostics.append(SkippedEntry(
                    path=str(file_path),
                    class_name=name,
                    reason=SKIP_INVALID_CONFIG,
                    detail=str(e),
                ))
                continue
            strategy_id = f"{obj.__module__}.{name}"
            strategies.append(StrategyMetadata(
                strategy_id=strategy_id,
                name=getattr(obj, "__display_name__", None) or name,
                description=(obj.__doc__ or "").strip().split("\n", 1)[0] if obj.__doc__ else "",
                strategy_type=strategy_type,
                module=obj.__module__,
                is_builtin=is_builtin,
                default_config=_to_param_spec(params),
                skipped_reasons=[],
            ))

    return strategies, diagnostics

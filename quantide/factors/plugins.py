"""External factor plugin discovery and deterministic panel computation."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import Literal, cast

import polars as pl
from loguru import logger

from quantide.config.output_paths import external_runtime_path
from quantide.factors.alpha import FEATURE_COLS

_FACTOR_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_INTERVALS = {"1d", "30m", "1M"}
_SCOPES = {"time_series", "cross_sectional"}
_ADJUSTMENTS = {"hfq", "raw"}
_AVAILABILITY = {"bar_close", "next_open"}
_DIRECTIONS = {"positive", "negative", "nonlinear"}
_OhlcColumn = Literal["open", "high", "low", "close"]
_OHLC_COLUMNS: tuple[_OhlcColumn, ...] = ("open", "high", "low", "close")


class SkippedFactorReason(StrEnum):
    """Stable reasons for excluding one plugin file."""

    SYNTAX_ERROR = "SyntaxError"
    IMPORT_ERROR = "ImportError"
    MISSING_PLUGIN_DECLARATION = "MissingPluginDeclaration"
    INVALID_METADATA = "InvalidMetadata"
    BUILTIN_ID_CONFLICT = "BuiltinIdConflict"
    DUPLICATE_PLUGIN_ID = "DuplicatePluginId"
    SOURCE_CHECKOUT_REJECTED = "SourceCheckoutRejected"


@dataclass(frozen=True)
class GoldenCase:
    """An optional hand-calculated plugin test case."""

    name: str
    bars: list[dict[str, object]]
    expected: list[float | None]
    atol: float = 1e-9


@dataclass(frozen=True)
class FactorPlugin:
    """Declarative external factor contract."""

    factor_id: str
    display_name: str
    compute: Callable[[pl.DataFrame], pl.Series | pl.DataFrame]
    group: str = "自定义因子"
    bar_interval: Literal["1d", "30m", "1M"] = "1d"
    scope: Literal["time_series", "cross_sectional"] = "time_series"
    price_adjustment: Literal["hfq", "raw"] = "hfq"
    required_columns: tuple[str, ...] = ("open", "high", "low", "close", "volume", "amount")
    warmup_bars: int = 1
    availability: Literal["bar_close", "next_open"] = "bar_close"
    direction: Literal["positive", "negative", "nonlinear"] = "positive"
    principle: str = ""
    formula: str = ""
    example: str = ""
    caveats: str = ""
    golden_cases: tuple[GoldenCase, ...] = ()
    source_path: str = ""
    source_hash: str = ""


@dataclass(frozen=True)
class SkippedFactorEntry:
    """One plugin file that could not be accepted."""

    file_path: str
    reason: SkippedFactorReason
    detail: str
    factor_id: str = ""


@dataclass(frozen=True)
class PluginDiscovery:
    """Result of one tolerant directory scan."""

    factor_dir: str
    plugins: tuple[FactorPlugin, ...]
    skipped: tuple[SkippedFactorEntry, ...]
    signature: tuple[tuple[str, int, int], ...] = ()

    def by_id(self, factor_id: str) -> FactorPlugin | None:
        return next((plugin for plugin in self.plugins if plugin.factor_id == factor_id), None)


class PluginContractError(ValueError):
    """A plugin does not satisfy the factor panel contract."""


class _PluginLoadError(Exception):
    def __init__(self, reason: SkippedFactorReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


_CACHE_LOCK = threading.RLock()
_CACHE: dict[str, tuple[tuple[tuple[str, int, int], ...], PluginDiscovery]] = {}


def _directory_signature(path: Path) -> tuple[tuple[str, int, int], ...]:
    if not path.is_dir():
        return ()
    entries: list[tuple[str, int, int]] = []
    for item in sorted(path.iterdir(), key=lambda entry: entry.name):
        if not item.is_file() or item.suffix != ".py" or _skip_name(item.name):
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        entries.append((item.name, stat.st_mtime_ns, stat.st_size))
    return tuple(entries)


def _skip_name(name: str) -> bool:
    return name.startswith(".") or name.startswith("_") or name == "__pycache__"


def _resolve_factor_dir(factor_dir: str | Path | None) -> Path:
    text = str(factor_dir or "").strip()
    if not text:
        from quantide.config.settings import get_factor_dir

        text = get_factor_dir()
    return external_runtime_path(text)


def _module_name(path: Path, source_hash: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_]", "_", path.stem)
    return f"_millionaire_factor_{source_hash[:10]}_{stem}"


def _load_module(path: Path, source_hash: str) -> ModuleType:
    name = _module_name(path, source_hash)
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise _PluginLoadError(SkippedFactorReason.IMPORT_ERROR, "无法创建模块加载器")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _validate_metadata(plugin: object) -> None:
    required = ("factor_id", "display_name", "compute", "group")
    missing = [field for field in required if not getattr(plugin, field, None)]
    if missing:
        raise _PluginLoadError(
            SkippedFactorReason.MISSING_PLUGIN_DECLARATION,
            f"缺少必填元数据: {', '.join(missing)}",
        )
    factor_id = str(getattr(plugin, "factor_id", ""))
    if not _FACTOR_ID.fullmatch(factor_id):
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, f"非法 factor_id: {factor_id}")
    if str(getattr(plugin, "bar_interval", "1d")) not in _INTERVALS:
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, "bar_interval 不受支持")
    if str(getattr(plugin, "scope", "time_series")) not in _SCOPES:
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, "scope 不受支持")
    if str(getattr(plugin, "price_adjustment", "hfq")) not in _ADJUSTMENTS:
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, "price_adjustment 不受支持")
    if str(getattr(plugin, "availability", "bar_close")) not in _AVAILABILITY:
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, "availability 不受支持")
    if str(getattr(plugin, "direction", "positive")) not in _DIRECTIONS:
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, "direction 不受支持")
    columns = getattr(plugin, "required_columns", ())
    if (
        not isinstance(columns, tuple)
        or not columns
        or any(not isinstance(column, str) or not column.strip() for column in columns)
    ):
        raise _PluginLoadError(
            SkippedFactorReason.INVALID_METADATA, "required_columns 必须是非空字符串元组"
        )
    warmup = getattr(plugin, "warmup_bars", 0)
    if not isinstance(warmup, int) or warmup < 0:
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, "warmup_bars 必须是非负整数")
    if not callable(getattr(plugin, "compute", None)):
        raise _PluginLoadError(SkippedFactorReason.INVALID_METADATA, "compute 必须可调用")


def _load_plugin(path: Path) -> FactorPlugin:
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()[:16]
    try:
        module = _load_module(path, source_hash)
    except SyntaxError as exc:
        raise _PluginLoadError(
            SkippedFactorReason.SYNTAX_ERROR, f"{exc.msg}（第 {exc.lineno} 行）"
        ) from exc
    except ImportError as exc:
        raise _PluginLoadError(SkippedFactorReason.IMPORT_ERROR, str(exc)) from exc
    candidate = getattr(module, "FACTOR_PLUGIN", None)
    if candidate is None:
        raise _PluginLoadError(
            SkippedFactorReason.MISSING_PLUGIN_DECLARATION, "未导出 FACTOR_PLUGIN"
        )
    _validate_metadata(candidate)
    return replace(
        cast(FactorPlugin, candidate),
        source_path=str(path),
        source_hash=source_hash,
        golden_cases=tuple(getattr(candidate, "golden_cases", ()) or ()),
    )


def _load_candidate(path: Path) -> tuple[FactorPlugin | None, SkippedFactorEntry | None]:
    try:
        return _load_plugin(path), None
    except _PluginLoadError as exc:
        return None, SkippedFactorEntry(str(path), exc.reason, exc.detail)
    except Exception as exc:  # pragma: no cover - defensive isolation
        return None, SkippedFactorEntry(str(path), SkippedFactorReason.IMPORT_ERROR, str(exc))


def _accept_plugin(
    path: Path,
    plugin: FactorPlugin,
    seen: set[str],
    plugins: list[FactorPlugin],
    skipped: list[SkippedFactorEntry],
) -> None:
    if plugin.factor_id in FEATURE_COLS:
        skipped.append(
            SkippedFactorEntry(
                str(path),
                SkippedFactorReason.BUILTIN_ID_CONFLICT,
                f"与内置因子重名: {plugin.factor_id}",
                plugin.factor_id,
            )
        )
        return
    if plugin.factor_id in seen:
        skipped.append(
            SkippedFactorEntry(
                str(path),
                SkippedFactorReason.DUPLICATE_PLUGIN_ID,
                f"重复 factor_id: {plugin.factor_id}",
                plugin.factor_id,
            )
        )
        return
    seen.add(plugin.factor_id)
    plugins.append(plugin)


def _scan_directory(directory: Path) -> tuple[list[FactorPlugin], list[SkippedFactorEntry]]:
    plugins: list[FactorPlugin] = []
    skipped: list[SkippedFactorEntry] = []
    seen: set[str] = set()
    if not directory.is_dir():
        return plugins, skipped
    for path in sorted(directory.glob("*.py"), key=lambda item: item.name):
        if _skip_name(path.name):
            continue
        plugin, problem = _load_candidate(path)
        if problem is not None:
            skipped.append(problem)
        elif plugin is not None:
            _accept_plugin(path, plugin, seen, plugins, skipped)
    return plugins, skipped


def discover_factor_plugins(factor_dir: str | Path | None = None) -> PluginDiscovery:
    """Scan one flat directory, returning valid plugins and skip diagnostics."""
    try:
        directory = _resolve_factor_dir(factor_dir)
    except ValueError as exc:
        return PluginDiscovery(
            str(factor_dir or ""),
            (),
            (
                SkippedFactorEntry(
                    str(factor_dir or ""),
                    SkippedFactorReason.SOURCE_CHECKOUT_REJECTED,
                    str(exc),
                ),
            ),
        )
    signature = _directory_signature(directory)
    key = str(directory)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
    plugins, skipped = _scan_directory(directory)
    result = PluginDiscovery(str(directory), tuple(plugins), tuple(skipped), signature)
    with _CACHE_LOCK:
        _CACHE[key] = (signature, result)
    return result


def clear_plugin_cache() -> None:
    """Drop cached scans and loaded plugin modules."""
    with _CACHE_LOCK:
        _CACHE.clear()
        for name in [name for name in sys.modules if name.startswith("_millionaire_factor_")]:
            sys.modules.pop(name, None)


def factor_source_hash(factor_id: str) -> str:
    """Return the source hash for an external factor, or an empty string."""
    plugin = discover_factor_plugins().by_id(factor_id)
    return plugin.source_hash if plugin is not None else ""


def _input_frame(panel: pl.DataFrame, plugin: FactorPlugin) -> tuple[pl.DataFrame, str]:
    date_col = "dt" if plugin.bar_interval != "1d" else "date"
    required = {*plugin.required_columns, "asset", date_col}
    absent = sorted(required - set(panel.columns))
    if absent:
        raise PluginContractError(f"输入面板缺少列: {', '.join(absent)}")
    frame = panel
    if plugin.price_adjustment == "hfq" and "adjust" in panel.columns:
        frame = frame.with_columns(
            (pl.col(column) * pl.col("adjust")).alias(column)
            for column in _OHLC_COLUMNS
            if column in panel.columns
        )
    return frame.sort(["asset", date_col]), date_col


def _series_frame(
    result: pl.Series | pl.DataFrame,
    keys: pl.DataFrame,
    date_col: str,
    factor_id: str,
) -> pl.DataFrame:
    key_columns = ["asset", date_col]
    if isinstance(result, pl.Series):
        if result.len() != keys.height:
            raise PluginContractError("compute 返回的 Series 长度与输入不一致")
        frame = keys.with_columns(result.alias(factor_id))
    elif isinstance(result, pl.DataFrame):
        missing = [column for column in (*key_columns, factor_id) if column not in result.columns]
        if missing:
            raise PluginContractError(f"compute 返回的 DataFrame 缺少列: {', '.join(missing)}")
        frame = result.select([*key_columns, factor_id])
        if frame.select(key_columns).is_duplicated().any():
            raise PluginContractError("compute 返回的键重复")
        frame = keys.join(frame, on=key_columns, how="left")
    else:
        raise PluginContractError("compute 必须返回 pl.Series 或 pl.DataFrame")
    values = frame[factor_id]
    if values.dtype in (pl.Float32, pl.Float64):
        invalid = values.is_not_null() & ~values.is_finite()
        if bool(invalid.any()):
            raise PluginContractError("compute 返回了 NaN 或 Inf；预热/缺失值请使用 null")
    return frame


def compute_plugin(
    panel: pl.DataFrame,
    plugin: FactorPlugin,
) -> pl.DataFrame:
    """Compute one plugin and return aligned keys plus the factor column."""
    frame, date_col = _input_frame(panel, plugin)
    keys = frame.select(["asset", date_col])
    result = plugin.compute(frame)
    return _series_frame(result, keys, date_col, plugin.factor_id)


def augment_panel_with_plugins(
    panel: pl.DataFrame,
    factor_ids: Iterable[str] | None = None,
    *,
    strict: bool = False,
) -> pl.DataFrame:
    """Join selected external factor columns onto a built-in factor panel."""
    discovery = discover_factor_plugins()
    requested = set(factor_ids) if factor_ids is not None else None
    result = panel
    for plugin in discovery.plugins:
        if requested is not None and plugin.factor_id not in requested:
            continue
        try:
            computed = compute_plugin(panel, plugin)
        except Exception as exc:
            if strict:
                raise
            logger.warning("外部因子计算失败，已跳过 {}: {}", plugin.factor_id, exc)
            continue
        if plugin.factor_id in result.columns:
            result = result.drop(plugin.factor_id)
        result = result.join(computed, on=list(computed.columns[:-1]), how="left")
    return result


__all__ = [
    "FactorPlugin",
    "GoldenCase",
    "PluginContractError",
    "PluginDiscovery",
    "SkippedFactorEntry",
    "SkippedFactorReason",
    "augment_panel_with_plugins",
    "clear_plugin_cache",
    "compute_plugin",
    "discover_factor_plugins",
    "factor_source_hash",
]

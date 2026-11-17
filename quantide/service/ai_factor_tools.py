"""Strict six-tool sandbox used by the Web AI factor studio."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import threading
from pathlib import Path
from typing import Any, cast

from quantide.config.paths import (
    get_app_config_dir,
    get_app_db_path,
    normalize_factor_dir,
)
from quantide.config.settings import get_factor_dir
from quantide.core.atomic_files import atomic_path
from quantide.factors.alpha import FEATURE_COLS
from quantide.factors.registry import all_factor_ids, factor_metadata
from quantide.service.process_runner import (
    CANCELLED,
    FAILED,
    SUCCEEDED,
    TIMEOUT,
    run_isolated,
)

_FACTOR_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_WINDOWS_BUDGET = 120.0
_STUDY_BUDGET = 150.0


class AIToolError(RuntimeError):
    """Structured tool refusal with a stable code for the agent loop."""

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "code": self.code, "message": self.message, **self.data}


def _prepare_isolated_worker(payload: dict[str, Any]) -> None:
    from quantide.config.paths import set_app_config_dir_override
    from quantide.data import init_data
    from quantide.data.sqlite import db

    if payload.get("config_home"):
        set_app_config_dir_override(payload["config_home"])
    if payload.get("data_home"):
        init_data(str(payload["data_home"]), init_db=False)
    if not db._initialized:
        db.init(get_app_db_path())


def _wind_tunnel_worker(payload: dict[str, Any]) -> dict[str, Any]:
    _prepare_isolated_worker(payload)
    from quantide.factors.plugins import _load_plugin
    from quantide.service.factor_wind_tunnel import (
        load_wind_tunnel_inputs,
        run_factor_wind_tunnel,
    )

    factor_id = str(payload["factor_id"])
    source = Path(payload["factor_dir"]) / f"{factor_id}.py"
    plugin = _load_plugin(source)
    inputs = load_wind_tunnel_inputs(
        dt.date.fromisoformat(payload["start"]),
        dt.date.fromisoformat(payload["end"]),
        interval=plugin.bar_interval,
        price_adjustment=plugin.price_adjustment,
    )
    result = run_factor_wind_tunnel(
        factor_id,
        frame=inputs.frame,
        source_daily=inputs.source_daily,
        plugin=plugin,
        interval=plugin.bar_interval,
        save=True,
    )
    return result.as_dict()


def _study_worker(payload: dict[str, Any]) -> dict[str, Any]:
    _prepare_isolated_worker(payload)
    from quantide.service.factor_study import run_custom_study

    study = run_custom_study(
        str(payload["factor_id"]),
        dt.date.fromisoformat(payload["start"]),
        dt.date.fromisoformat(payload["end"]),
        [int(value) for value in payload["holdings"]],
        "open",
    )
    return study.as_dict()


def _payload_base() -> dict[str, Any]:
    from quantide.config.settings import get_data_home

    return {
        "config_home": str(get_app_config_dir()),
        "data_home": get_data_home(),
        "factor_dir": normalize_factor_dir(get_factor_dir()),
    }


def _run_process(worker: Any, payload: dict[str, Any], *, timeout: float, cancel: Any) -> Any:
    outcome = run_isolated(worker, payload, timeout=timeout, cancel=cancel)
    if outcome.status == CANCELLED:
        raise AIToolError("cancelled", "任务已取消。")
    if outcome.status == TIMEOUT:
        raise AIToolError("timeout", "计算超时，已终止受控子进程。")
    if outcome.status == FAILED:
        raise AIToolError("worker_failed", str(outcome.error or "子进程计算失败"))
    if outcome.status != SUCCEEDED:
        raise AIToolError("worker_failed", f"未知子进程状态: {outcome.status}")
    return outcome.value


def _coverage_window() -> tuple[dt.date, dt.date]:
    from quantide.service.research_cli import data_status

    coverage = data_status().get("coverage") or {}
    try:
        start = dt.date.fromisoformat(str(coverage["start"]))
        end = dt.date.fromisoformat(str(coverage["end"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AIToolError("no_market_data", "当前数据源没有可用日线覆盖。") from exc
    return start, end


def inspect_market_schema(
    _arguments: dict[str, Any] | None = None, **_kwargs: Any
) -> dict[str, Any]:
    """Read active market mode, datasets, schema and coverage without mutation."""
    from quantide.service.research_cli import data_status

    try:
        status = data_status()
    except Exception as exc:
        raise AIToolError("market_schema_failed", f"读取行情 schema 失败: {exc}") from exc
    return {"ok": True, **status, "adjustment": "daily bars expose raw and hfq adjustment"}


def search_registered_factors(
    arguments: dict[str, Any] | None = None, **_kwargs: Any
) -> dict[str, Any]:
    """Search built-in and external factors by id/name/group."""
    args = arguments or {}
    query = str(args.get("query") or "").strip().lower()
    group = str(args.get("group") or "").strip()
    try:
        metadata = factor_metadata()
    except Exception as exc:
        raise AIToolError("factor_search_failed", f"因子目录读取失败: {exc}") from exc
    items = []
    for factor_id in all_factor_ids():
        definition = metadata.get(factor_id)
        if definition is None:
            continue
        haystack = f"{factor_id} {definition.display_name} {definition.group}".lower()
        if query and query not in haystack:
            continue
        if group and definition.group != group:
            continue
        items.append(
            {
                "factor_id": factor_id,
                "display_name": definition.display_name,
                "group": definition.group,
                "principle": definition.principle,
                "formula": definition.formula,
                "warmup_bars": (definition.parameters[0] if definition.parameters else ""),
            }
        )
    return {"ok": True, "query": query, "count": len(items), "factors": items[:30]}


def _factor_root() -> Path:
    root = Path(normalize_factor_dir(get_factor_dir())).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def _validate_target(root: Path, target: Path, resolved: Path) -> None:
    if target.is_symlink() or resolved.parent != root or resolved.name != target.name:
        raise AIToolError("path_escape", "目标路径越出 factor_dir 直接子级，已拒绝写入。")


def _target_path(factor_id: str) -> Path:
    if not _FACTOR_ID.fullmatch(factor_id):
        raise AIToolError("invalid_factor_id", "factor_id 必须匹配 ^[a-z][a-z0-9_]{2,63}$")
    if factor_id in set(FEATURE_COLS):
        raise AIToolError("builtin_conflict", f"{factor_id} 与内置因子重名，禁止覆盖。")
    root = _factor_root()
    target = root / f"{factor_id}.py"
    resolved = target.resolve(strict=False)
    _validate_target(root, target, resolved)
    return target


def write_factor_plugin(arguments: dict[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
    """Atomically write one validated single-file factor inside ``factor_dir``."""
    args = arguments or {}
    factor_id = str(args.get("factor_id") or "").strip()
    code = str(args.get("code") or "")
    if not code.strip():
        raise AIToolError("empty_code", "因子代码不能为空。")
    target = _target_path(factor_id)
    try:
        with atomic_path(target) as temporary:
            temporary.write_text(code, encoding="utf-8")
            if os.name != "nt":
                os.chmod(temporary, 0o600)
    except OSError as exc:
        raise AIToolError("write_failed", f"写入因子文件失败: {exc}") from exc
    source_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
    return {
        "ok": True,
        "factor_id": factor_id,
        "path": str(target),
        "source_hash": source_hash,
    }


def _wind_payload(factor_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    start, end = _coverage_window()
    cutoff = str(arguments.get("cutoff") or "").strip()
    if cutoff:
        try:
            end = min(end, dt.date.fromisoformat(cutoff))
        except ValueError as exc:
            raise AIToolError("invalid_cutoff", "cutoff 必须是 YYYY-MM-DD。") from exc
    return {
        **_payload_base(),
        "factor_id": factor_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def _wind_summary(result: dict[str, Any], factor_id: str) -> dict[str, Any]:
    report = result.get("report") or {}
    diagnostics = []
    for check in report.get("checks") or []:
        if isinstance(check, dict) and check.get("status") in {"FAIL", "INCONCLUSIVE"}:
            diagnostics.append(
                {
                    "code": check.get("check_id"),
                    "message": check.get("message"),
                    "first_difference": check.get("first_difference"),
                }
            )
    return {
        "ok": result.get("status") == "PASS",
        "factor_id": factor_id,
        "status": result.get("status"),
        "first_difference": report.get("first_difference"),
        "diagnostics": diagnostics,
        "orthogonality": result.get("orthogonality") or {},
        "report": report,
    }


def run_factor_wind_tunnel(
    arguments: dict[str, Any] | None = None,
    *,
    cancel: threading.Event | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Run the deterministic wind tunnel in an isolated subprocess."""
    args = arguments or {}
    factor_id = str(args.get("factor_id") or "").strip()
    target = _target_path(factor_id)
    if not target.is_file():
        raise AIToolError("factor_missing", f"因子文件不存在: {factor_id}.py")
    result = _run_process(
        _wind_tunnel_worker,
        _wind_payload(factor_id, args),
        timeout=_WINDOWS_BUDGET,
        cancel=cancel,
    )
    if not isinstance(result, dict):
        raise AIToolError("worker_failed", "风洞子进程没有返回结构化结果。")
    return _wind_summary(result, factor_id)


def _require_pass(factor_id: str) -> None:
    from quantide.service.factor_audit import factor_wind_tunnel_badge

    badge = factor_wind_tunnel_badge(factor_id)
    if badge.badge_status != "PASS":
        raise AIToolError(
            "wind_tunnel_not_passed",
            f"因子 {factor_id} 当前风洞状态为 {badge.badge_status}，禁止生成统计结论。",
            {"badge_status": badge.badge_status, "message": badge.message},
        )


def _study_summary(result: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in result.get("results") or []:
        diagnostics = item.get("diagnostics") or {}
        rows.append(
            {
                "holding_days": item.get("holding_days"),
                "as_of_date": diagnostics.get("as_of_date"),
                "rank_ic": item.get("rank_ic"),
                "pearson_ic": item.get("pearson_ic"),
                "deciles": item.get("deciles"),
            }
        )
    return {
        "study_id": result.get("study_id"),
        "factor_id": result.get("factor_id"),
        "data_cutoff": result.get("data_cutoff"),
        "results": rows,
        "common_cohort": result.get("common_cohort"),
        "universe_filter": result.get("universe_filter"),
        "universe": _universe_digest(result.get("universe_diagnostics")),
    }


def _universe_digest(diagnostics: Any) -> dict[str, Any] | None:
    """Summarize PIT eligibility so the model sees downgrades without full members."""
    if not isinstance(diagnostics, dict):
        return None
    by_date = diagnostics.get("by_date") or {}
    warnings: set[str] = set()
    size_bases: set[str] = set()
    counts: dict[str, int] = {}
    effective = 0
    capped = False
    for entry in by_date.values():
        if not isinstance(entry, dict):
            continue
        warnings.update(str(item) for item in entry.get("warnings") or ())
        size_bases.add(str(entry.get("size_basis") or "none"))
        for key, value in (entry.get("exclusion_counts") or {}).items():
            counts[key] = counts.get(key, 0) + int(value)
        effective += len(entry.get("assets") or ())
        capped = capped or bool(entry.get("capped"))
    return {
        "applied": diagnostics.get("applied"),
        "config": diagnostics.get("config"),
        "dates": len(by_date),
        "effective_rows": effective,
        "warnings": sorted(warnings),
        "size_bases": sorted(size_bases),
        "exclusion_counts": counts,
        "capped": capped,
    }


def run_factor_ic_study(
    arguments: dict[str, Any] | None = None,
    *,
    cancel: threading.Event | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Run RankIC/decile research only after the current fingerprint is PASS."""
    args = arguments or {}
    factor_id = str(args.get("factor_id") or "").strip()
    if not _FACTOR_ID.fullmatch(factor_id):
        raise AIToolError("invalid_factor_id", "factor_id 格式非法。")
    _require_pass(factor_id)
    start, end = _coverage_window()
    lookback = str(args.get("lookback") or "1y")
    days = 1095 if lookback == "3y" else 365
    start = max(start, end - dt.timedelta(days=days))
    holdings = args.get("holdings") or [1, 3, 5]
    try:
        holdings = [int(value) for value in holdings]
    except (TypeError, ValueError) as exc:
        raise AIToolError("invalid_holdings", "holdings 必须是整数列表。") from exc
    result = _run_process(
        _study_worker,
        {
            **_payload_base(),
            "factor_id": factor_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "holdings": holdings,
        },
        timeout=_STUDY_BUDGET,
        cancel=cancel,
    )
    if not isinstance(result, dict):
        raise AIToolError("worker_failed", "检验子进程没有返回结构化结果。")
    return {"ok": True, **_study_summary(result)}


def _preset_source(arguments: dict[str, Any], factor_id: str) -> tuple[str, list[str], str]:
    from quantide.service.factor_presets import load_preset

    baseline_id = str(arguments.get("baseline_preset_id") or "").strip()
    if not baseline_id:
        features = [value for value in all_factor_ids() if value != factor_id][:10]
        return "", features, "MLMomentumReversalStrategy"
    baseline = load_preset(baseline_id)
    return baseline_id, list(baseline.features), baseline.strategy_id


def _preset_window(arguments: dict[str, Any]) -> tuple[dt.date, dt.date]:
    start, end = _coverage_window()
    start = max(start, end - dt.timedelta(days=365))
    raw_start = str(arguments.get("start") or "").strip()
    raw_end = str(arguments.get("end") or "").strip()
    if not raw_start and not raw_end:
        return start, end
    try:
        requested_start = dt.date.fromisoformat(raw_start) if raw_start else start
        requested_end = dt.date.fromisoformat(raw_end) if raw_end else end
    except ValueError as exc:
        raise AIToolError("invalid_window", "start/end 必须是 YYYY-MM-DD。") from exc
    if requested_start > requested_end:
        raise AIToolError("invalid_window", "start 不能晚于 end。")
    return max(start, requested_start), min(end, requested_end)


def _preset_ablation(
    baseline_id: str,
    strategy_id: str,
    preset_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    from quantide.service.research_backtest import AblationStudySpec, run_ablation

    start, end = _preset_window(arguments)
    spec = AblationStudySpec(
        baseline_preset_id=baseline_id,
        variant_preset_ids=(preset_id,),
        start=start,
        end=end,
        strategy_id=strategy_id,
    )
    try:
        return {"ablation": run_ablation(spec)}
    except Exception as exc:
        return {"ablation": None, "ablation_error": str(exc)}


def save_preset_and_run_ablation(
    arguments: dict[str, Any] | None = None, **_kwargs: Any
) -> dict[str, Any]:
    """Save a preset containing the new factor and optionally run an ablation."""
    from quantide.service.factor_presets import save_preset

    args = arguments or {}
    factor_id = str(args.get("add_factor_id") or args.get("factor_id") or "").strip()
    if not _FACTOR_ID.fullmatch(factor_id):
        raise AIToolError("invalid_factor_id", "add_factor_id 格式非法。")
    _require_pass(factor_id)
    baseline_id, features, strategy_id = _preset_source(args, factor_id)
    if factor_id not in features:
        features.append(factor_id)
    preset = save_preset(
        str(args.get("preset_id") or f"ai_{factor_id}")[:64],
        str(args.get("name") or f"AI 因子 {factor_id}"),
        features,
        strategy_id=strategy_id,
        label_kind=str(args.get("label_kind") or "raw_return"),
    )
    payload: dict[str, Any] = {"ok": True, "preset": preset.as_dict(), "ablation": None}
    if baseline_id:
        payload.update(_preset_ablation(baseline_id, strategy_id, preset.preset_id, args))
        if payload.get("ablation_error"):
            payload["ok"] = False
            payload["code"] = "ablation_failed"
            payload["message"] = f"消融回测失败：{payload['ablation_error']}"
    return payload


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "inspect_market_schema",
            "description": "读取当前行情模式、数据集字段、覆盖区间与复权约定。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_registered_factors",
            "description": "检索已注册内置与外部因子的 ID、分组、原理与公式摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "group": {"type": ["string", "null"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_factor_plugin",
            "description": "只在 factor_dir 直接子级写入合法 factor_id.py 因子插件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "factor_id": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["factor_id", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_factor_wind_tunnel",
            "description": "在受控子进程运行风洞与正交性检查，返回 PASS/FAIL/INCONCLUSIVE。",
            "parameters": {
                "type": "object",
                "properties": {
                    "factor_id": {"type": "string"},
                    "cutoff": {"type": ["string", "null"]},
                },
                "required": ["factor_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_factor_ic_study",
            "description": "仅对当前指纹 PASS 的因子运行 RankIC、ICIR 与十分位收益检验。",
            "parameters": {
                "type": "object",
                "properties": {
                    "factor_id": {"type": "string"},
                    "lookback": {"type": "string", "enum": ["1y", "3y"]},
                    "holdings": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["factor_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_preset_and_run_ablation",
            "description": "保存包含新因子的 FactorPreset，并按需运行固定条件消融回测。",
            "parameters": {
                "type": "object",
                "properties": {
                    "preset_id": {"type": "string"},
                    "name": {"type": "string"},
                    "baseline_preset_id": {"type": ["string", "null"]},
                    "add_factor_id": {"type": "string"},
                    "label_kind": {
                        "type": "string",
                        "enum": ["raw_return", "excess_mean", "cs_rank"],
                    },
                    "start": {"type": ["string", "null"]},
                    "end": {"type": ["string", "null"]},
                },
                "required": ["preset_id", "name", "add_factor_id"],
            },
        },
    },
]

TOOL_HANDLERS: dict[str, Any] = {
    "inspect_market_schema": inspect_market_schema,
    "search_registered_factors": search_registered_factors,
    "write_factor_plugin": write_factor_plugin,
    "run_factor_wind_tunnel": run_factor_wind_tunnel,
    "run_factor_ic_study": run_factor_ic_study,
    "save_preset_and_run_ablation": save_preset_and_run_ablation,
}


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    cancel: threading.Event | None = None,
) -> dict[str, Any]:
    """Execute one whitelisted tool or return a structured refusal."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "code": "unknown_tool", "message": f"工具不在白名单: {name}"}
    try:
        if name in {"run_factor_wind_tunnel", "run_factor_ic_study"}:
            return cast(dict[str, Any], handler(arguments, cancel=cancel))
        return cast(dict[str, Any], handler(arguments))
    except AIToolError as exc:
        return exc.as_dict()
    except Exception as exc:
        return {"ok": False, "code": "tool_failed", "message": str(exc)}


__all__ = [
    "AIToolError",
    "TOOL_HANDLERS",
    "TOOL_SCHEMAS",
    "execute_tool",
    "inspect_market_schema",
    "run_factor_ic_study",
    "run_factor_wind_tunnel",
    "save_preset_and_run_ablation",
    "search_registered_factors",
    "write_factor_plugin",
]

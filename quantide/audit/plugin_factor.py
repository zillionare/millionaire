"""Deterministic wind-tunnel audit for external factor plugins."""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, cast

import polars as pl

from quantide.audit.checks import future_invariance_check
from quantide.audit.cutoffs import interior_cutoffs
from quantide.audit.future import _first_difference, frame_digest
from quantide.audit.models import (
    AuditCheck,
    AuditReport,
    AuditSpec,
    AuditStatus,
    FirstDifference,
    canonical_hash,
)
from quantide.audit.runner import AuditRunner
from quantide.factors.plugins import (
    FactorPlugin,
    GoldenCase,
    PluginContractError,
    compute_plugin,
    discover_factor_plugins,
)

PLUGIN_AUDIT_VERSION = "2.0.0"
_POSITIVE_COLUMNS = ("open", "high", "low", "close", "volume", "amount")


def _date_column(plugin: FactorPlugin) -> str:
    return "dt" if plugin.bar_interval != "1d" else "date"


def _with_availability(frame: pl.DataFrame, date_col: str) -> pl.DataFrame:
    if "available_at" in frame.columns:
        return frame
    return frame.with_columns(pl.col(date_col).alias("available_at"))


def _is_sorted(frame: pl.DataFrame, date_col: str) -> bool:
    ordered = frame.select(["asset", date_col]).sort(["asset", date_col])
    return bool(frame.select(["asset", date_col]).equals(ordered))


def _first_bad_key(frame: pl.DataFrame, date_col: str) -> dict[str, Any] | None:
    counts = (
        frame.group_by(["asset", date_col])
        .len()
        .filter(pl.col("len") > 1)
        .sort(["asset", date_col])
    )
    if counts.is_empty():
        return None
    return counts.row(0, named=True)


def _warmup_violation(
    output: pl.DataFrame,
    plugin: FactorPlugin,
    date_col: str,
) -> FirstDifference | None:
    if plugin.warmup_bars <= 0:
        return None
    for asset in output["asset"].unique(maintain_order=True).to_list():
        group = output.filter(pl.col("asset") == asset).sort(date_col)
        limit = min(plugin.warmup_bars, group.height)
        early = group.head(limit).filter(pl.col(plugin.factor_id).is_not_null())
        if early.height:
            row = early.row(0, named=True)
            return FirstDifference(
                time=str(row.get(date_col, "")),
                asset=str(asset),
                column=plugin.factor_id,
                expected="null during warmup",
                actual=row.get(plugin.factor_id),
                kind="warmup_violation",
                minimal_input={"warmup_bars": plugin.warmup_bars},
            )
    return None


def _contract_check(
    frame: pl.DataFrame,
    plugin: FactorPlugin,
    date_col: str,
) -> AuditCheck:
    if date_col not in frame.columns:
        return AuditCheck("plugin.contract", True, AuditStatus.FAIL, message=f"缺少 {date_col} 列")
    missing = sorted({*plugin.required_columns, "asset", date_col} - set(frame.columns))
    if missing:
        return AuditCheck(
            "plugin.contract",
            True,
            AuditStatus.FAIL,
            message=f"输入缺少列: {', '.join(missing)}",
        )
    if frame[date_col].dtype not in (pl.Date, pl.Datetime):
        return AuditCheck("plugin.contract", True, AuditStatus.FAIL, message="日期列类型无效")
    if not _is_sorted(frame, date_col):
        return AuditCheck(
            "plugin.contract", True, AuditStatus.FAIL, message="输入未按资产和日期排序"
        )
    duplicate = _first_bad_key(frame, date_col)
    if duplicate is not None:
        return AuditCheck(
            "plugin.contract",
            True,
            AuditStatus.FAIL,
            message=f"键重复: {duplicate}",
            first_difference=FirstDifference(
                time=str(duplicate.get(date_col)),
                asset=str(duplicate.get("asset")),
                column="(asset, date)",
                expected="unique key",
                actual=f"{duplicate.get('len')} rows",
                kind="duplicate_key",
            ),
        )
    try:
        output = compute_plugin(frame, plugin)
    except PluginContractError as exc:
        return AuditCheck("plugin.contract", True, AuditStatus.FAIL, message=str(exc))
    violation = _warmup_violation(output, plugin, date_col)
    if violation is not None:
        return AuditCheck(
            "plugin.contract",
            True,
            AuditStatus.FAIL,
            message=f"预热窗口内出现非空值: {violation.asset} {violation.time}",
            first_difference=violation,
        )
    values = output[plugin.factor_id]
    finite = values.filter(values.is_not_null() & values.is_finite())
    if finite.len() == 0:
        return AuditCheck(
            "plugin.contract",
            True,
            AuditStatus.INCONCLUSIVE,
            message="因子在样本内没有有效值",
            sample_size=output.height,
        )
    return AuditCheck("plugin.contract", True, AuditStatus.PASS, sample_size=output.height)


def _target_subset(frame: pl.DataFrame, asset: str, date_col: str) -> pl.DataFrame:
    return frame.filter(pl.col("asset") == asset).sort(["asset", date_col])


def _cross_section_check(
    frame: pl.DataFrame,
    plugin: FactorPlugin,
    date_col: str,
) -> AuditCheck:
    if plugin.scope == "cross_sectional":
        return AuditCheck(
            "plugin.cross_section_isolation",
            False,
            AuditStatus.NOT_APPLICABLE,
            message="截面因子允许受其它证券影响",
        )
    assets = sorted(str(asset) for asset in frame["asset"].unique().to_list())
    if len(assets) < 2:
        return AuditCheck(
            "plugin.cross_section_isolation",
            True,
            AuditStatus.INCONCLUSIVE,
            message="至少需要两只证券才能检查跨证券隔离",
        )
    asset = assets[-1]
    try:
        full = compute_plugin(frame, plugin).filter(pl.col("asset") == asset)
        subset = compute_plugin(_target_subset(frame, asset, date_col), plugin)
    except PluginContractError as exc:
        return AuditCheck(
            "plugin.cross_section_isolation", True, AuditStatus.FAIL, message=str(exc)
        )
    full = full.sort(date_col)
    subset = subset.sort(date_col)
    if frame_digest(full) == frame_digest(subset):
        return AuditCheck(
            "plugin.cross_section_isolation",
            True,
            AuditStatus.PASS,
            sample_size=full.height,
        )
    difference = _first_difference(full, subset, date_col)
    return AuditCheck(
        "plugin.cross_section_isolation",
        True,
        AuditStatus.FAIL,
        message=f"{asset} 的输出受无关证券影响，疑似缺少 .over('asset')",
        first_difference=FirstDifference(
            time=str(difference.get("time", "")),
            asset=asset,
            column=str(difference.get("column", plugin.factor_id)),
            expected=difference.get("expected"),
            actual=difference.get("actual"),
            kind="cross_sectional_dependency",
            minimal_input={"row": difference.get("row")},
        ),
        sample_size=full.height,
    )


def _interior_cutoffs(frame: pl.DataFrame, date_col: str, count: int = 3) -> tuple[dt.date, ...]:
    return interior_cutoffs(frame[date_col].to_list(), count)


def _warm_pipeline(checked: pl.DataFrame, plugin: FactorPlugin) -> Any:
    """Return a pipeline that warms the plugin module with the full baseline first."""
    from quantide.factors.plugin_worker import compute_sequence
    from quantide.factors.plugins import _plugin_budget, _plugin_outcome_value
    from quantide.service.process_runner import run_isolated

    def pipeline(data: pl.DataFrame) -> pl.DataFrame:
        if not plugin.source_path:
            return compute_plugin(data, plugin)
        timeout, memory_bytes = _plugin_budget()
        outcome = run_isolated(
            compute_sequence,
            plugin.source_path,
            plugin.source_hash,
            [checked, data],
            timeout=timeout,
            memory_bytes=memory_bytes,
        )
        return cast(pl.DataFrame, _plugin_outcome_value(outcome, timeout)[-1])

    return pipeline


def _merge_branch_checks(checks: list[AuditCheck]) -> AuditCheck:
    failure = next((check for check in checks if check.status is AuditStatus.FAIL), None)
    if failure is not None:
        return failure
    incomplete = next((check for check in checks if check.status is not AuditStatus.PASS), None)
    if incomplete is not None:
        return incomplete
    return AuditCheck(
        "plugin.future_invariance",
        True,
        AuditStatus.PASS,
        sample_size=checks[0].sample_size if checks else None,
        details={"branches": [check.check_id for check in checks]},
    )


def _merge_invariance_checks(
    cold: AuditCheck, warm: AuditCheck, details: dict[str, Any]
) -> AuditCheck:
    merged_details = {
        **details,
        "executed_branches": ["cold", "warm"],
        "cold": cold.details,
        "warm": warm.details,
    }
    for branch in (cold, warm):
        if branch.status is AuditStatus.FAIL:
            return AuditCheck(
                "plugin.future_invariance",
                True,
                AuditStatus.FAIL,
                message=branch.message,
                first_difference=branch.first_difference,
                details=merged_details,
            )
    if cold.status is not AuditStatus.PASS or warm.status is not AuditStatus.PASS:
        return AuditCheck(
            "plugin.future_invariance",
            True,
            AuditStatus.INCONCLUSIVE,
            message=cold.message or warm.message,
            details=merged_details,
        )
    return AuditCheck(
        "plugin.future_invariance",
        True,
        AuditStatus.PASS,
        sample_size=cold.sample_size,
        details=merged_details,
    )


def _future_check(
    frame: pl.DataFrame,
    plugin: FactorPlugin,
    date_col: str,
    cutoffs: tuple[dt.date, ...],
    modes: tuple[str, ...],
    seeds: tuple[int, ...],
) -> AuditCheck:
    if len(cutoffs) < 3:
        return AuditCheck(
            "plugin.future_invariance",
            True,
            AuditStatus.INCONCLUSIVE,
            message="至少需要 3 个未来截断点",
        )
    checked = _with_availability(frame, date_col)

    def pipeline(data: pl.DataFrame) -> pl.DataFrame:
        if not plugin.source_path:
            return compute_plugin(data, plugin)
        from quantide.factors.plugin_worker import compute_once
        from quantide.factors.plugins import _plugin_budget, _plugin_outcome_value
        from quantide.service.process_runner import run_isolated

        timeout, memory_bytes = _plugin_budget()
        outcome = run_isolated(
            compute_once,
            plugin.source_path,
            plugin.source_hash,
            data,
            timeout=timeout,
            memory_bytes=memory_bytes,
        )
        return cast(pl.DataFrame, _plugin_outcome_value(outcome, timeout))

    cold_checks: list[AuditCheck] = []
    warm_checks: list[AuditCheck] = []
    if not plugin.source_path:
        cold_checks = [
            future_invariance_check(
                f"plugin.future_invariance:{cutoff.isoformat()}",
                pipeline,
                checked,
                cutoff,
                modes=modes,
                seeds=seeds,
                date_col=date_col,
                positive_columns=_POSITIVE_COLUMNS,
            )
            for cutoff in cutoffs
        ]
        cold = _merge_branch_checks(cold_checks)
        if cold.status is AuditStatus.FAIL:
            return cold
        return AuditCheck(
            "plugin.future_invariance",
            True,
            AuditStatus.INCONCLUSIVE,
            message="程序化 FactorPlugin 缺少可重建 source_path，无法证明冷/热隔离。",
            details={
                "executed_branches": ["cold"],
                "cold": cold.details,
                "warm_branch": "unavailable",
            },
        )
    warm_pipeline = _warm_pipeline(checked, plugin)
    for cutoff in cutoffs:
        cold_checks.append(
            future_invariance_check(
                f"plugin.future_invariance:{cutoff.isoformat()}",
                pipeline,
                checked,
                cutoff,
                modes=modes,
                seeds=seeds,
                date_col=date_col,
                positive_columns=_POSITIVE_COLUMNS,
            )
        )
        warm_checks.append(
            future_invariance_check(
                f"plugin.future_invariance:{cutoff.isoformat()}",
                warm_pipeline,
                checked,
                cutoff,
                modes=modes,
                seeds=seeds,
                date_col=date_col,
                positive_columns=_POSITIVE_COLUMNS,
            )
        )
    details = {
        "cutoffs": [value.isoformat() for value in cutoffs],
        "modes": list(modes),
        "seeds": list(seeds),
        "cold_cutoffs": [item.check_id for item in cold_checks],
        "warm_cutoffs": [item.check_id for item in warm_checks],
    }
    cold = _merge_branch_checks(cold_checks)
    warm = _merge_branch_checks(warm_checks)
    return _merge_invariance_checks(cold, warm, details)


def _golden_case_mismatch(
    case: GoldenCase,
    plugin: FactorPlugin,
    index: int,
    left: float | None,
    right: float | None,
) -> AuditCheck | None:
    if left is None and right is None:
        return None
    if left is None or right is None:
        return AuditCheck(
            "plugin.golden_cases",
            True,
            AuditStatus.FAIL,
            message=f"{case.name}: 第 {index} 行空值不一致",
        )
    if math.isclose(float(left), float(right), abs_tol=case.atol, rel_tol=0.0):
        return None
    return AuditCheck(
        "plugin.golden_cases",
        True,
        AuditStatus.FAIL,
        message=f"{case.name}: 第 {index} 行期望 {left}，实际 {right}",
        first_difference=FirstDifference(
            time=str(case.bars[index].get("date", "")),
            asset=str(case.bars[index].get("asset", "")),
            column=plugin.factor_id,
            expected=left,
            actual=right,
            kind="golden_case_mismatch",
            minimal_input={"case": case.name, "row": index},
        ),
    )


def _golden_case_check(case: GoldenCase, plugin: FactorPlugin) -> AuditCheck | None:
    try:
        frame = pl.DataFrame(case.bars)
        output = compute_plugin(frame, plugin)
    except Exception as exc:
        return AuditCheck("plugin.golden_cases", True, AuditStatus.FAIL, message=str(exc))
    actual = output[plugin.factor_id].to_list()
    expected = list(case.expected)
    if len(actual) != len(expected):
        return AuditCheck(
            "plugin.golden_cases",
            True,
            AuditStatus.FAIL,
            message=f"{case.name}: 输出长度不一致",
        )
    for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
        failure = _golden_case_mismatch(case, plugin, index, left, right)
        if failure is not None:
            return failure
    return None


def _golden_check(plugin: FactorPlugin) -> AuditCheck:
    cases = tuple(plugin.golden_cases or ())
    if not cases:
        return AuditCheck(
            "plugin.golden_cases",
            False,
            AuditStatus.NOT_APPLICABLE,
            message="插件未提供 GOLDEN_CASES",
        )
    for case in cases:
        failure = _golden_case_check(case, plugin)
        if failure is not None:
            return failure
    return AuditCheck("plugin.golden_cases", True, AuditStatus.PASS, sample_size=len(cases))


def _determinism_check(
    frame: pl.DataFrame,
    plugin: FactorPlugin,
    date_col: str,
) -> AuditCheck:
    try:
        first = compute_plugin(frame, plugin).sort(date_col)
        second = compute_plugin(frame, plugin).sort(date_col)
    except PluginContractError as exc:
        return AuditCheck("plugin.deterministic", True, AuditStatus.FAIL, message=str(exc))
    if frame_digest(first) != frame_digest(second):
        return AuditCheck(
            "plugin.deterministic",
            True,
            AuditStatus.FAIL,
            message="重复运行结果不一致",
        )
    return AuditCheck("plugin.deterministic", True, AuditStatus.PASS, sample_size=first.height)


def _resolve_plugin(plugin: FactorPlugin | str) -> FactorPlugin:
    if isinstance(plugin, FactorPlugin):
        return plugin
    found = discover_factor_plugins().by_id(plugin)
    if found is None:
        raise KeyError(plugin)
    return found


def plugin_config_hash(
    plugin: FactorPlugin,
    *,
    cutoffs: tuple[dt.date, ...],
    modes: tuple[str, ...] = ("zero", "extreme", "random"),
    seeds: tuple[int, ...] = (0,),
) -> str:
    """Return the plugin configuration fingerprint shared with the audit spec."""
    return canonical_hash(
        {
            "factor_id": plugin.factor_id,
            "bar_interval": plugin.bar_interval,
            "scope": plugin.scope,
            "required_columns": list(plugin.required_columns),
            "warmup_bars": plugin.warmup_bars,
            "cutoffs": [value.isoformat() for value in cutoffs],
            "modes": list(modes),
            "seeds": list(seeds),
            "oracle_version": PLUGIN_AUDIT_VERSION,
        }
    )


def build_plugin_spec(
    frame: pl.DataFrame,
    plugin: FactorPlugin,
    *,
    cutoffs: tuple[dt.date, ...],
    modes: tuple[str, ...] = ("zero", "extreme", "random"),
    seeds: tuple[int, ...] = (0,),
) -> AuditSpec:
    date_col = _date_column(plugin)
    return AuditSpec(
        spec_id=f"factor_plugin:{plugin.factor_id}:{plugin.source_hash}",
        object_type="factor_plugin",
        object_id=plugin.factor_id,
        source_hash=plugin.source_hash,
        data_hash=frame_digest(frame),
        config_hash=plugin_config_hash(plugin, cutoffs=cutoffs, modes=modes, seeds=seeds),
        interval=plugin.bar_interval,
        timezone="Asia/Shanghai",
        availability_contract=f"plugin availability={plugin.availability}",
        seed_set=tuple(seeds),
        statistical_profile="external-factor-plugin",
        oracle_version=PLUGIN_AUDIT_VERSION,
        truncation_points=tuple(value.isoformat() for value in cutoffs),
        metadata={"source_path": plugin.source_path, "date_col": date_col},
    )


def audit_factor_plugin(
    plugin: FactorPlugin | str,
    frame: pl.DataFrame,
    *,
    spec: AuditSpec | None = None,
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None = None,
    modes: tuple[str, ...] = ("zero", "extreme", "random"),
    seeds: tuple[int, ...] = (0,),
) -> AuditReport:
    """Run contract, isolation, determinism, golden-case and future checks."""
    resolved_plugin = _resolve_plugin(plugin)
    date_col = _date_column(resolved_plugin)
    resolved_cutoffs = tuple(cutoffs) if cutoffs is not None else _interior_cutoffs(frame, date_col)
    if any(not isinstance(value, dt.date) for value in resolved_cutoffs):
        raise ValueError("cutoffs must be dates")
    expected = build_plugin_spec(
        frame,
        resolved_plugin,
        cutoffs=resolved_cutoffs,
        modes=modes,
        seeds=seeds,
    )
    if spec is not None and spec.fingerprint != expected.fingerprint:
        raise ValueError("explicit spec does not match the executed plugin audit")
    registry = {
        "plugin.contract": (
            lambda _: _contract_check(frame, resolved_plugin, date_col),
            True,
        ),
        "plugin.cross_section_isolation": (
            lambda _: _cross_section_check(frame, resolved_plugin, date_col),
            True,
        ),
        "plugin.deterministic": (
            lambda _: _determinism_check(frame, resolved_plugin, date_col),
            True,
        ),
        "plugin.golden_cases": (lambda _: _golden_check(resolved_plugin), False),
        "plugin.future_invariance": (
            lambda _: _future_check(
                frame, resolved_plugin, date_col, resolved_cutoffs, modes, seeds
            ),
            True,
        ),
    }
    return AuditRunner(registry).run(spec or expected)


__all__ = [
    "PLUGIN_AUDIT_VERSION",
    "audit_factor_plugin",
    "build_plugin_spec",
    "plugin_config_hash",
]

"""Audit adapter for the built-in factor pipeline."""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

import polars as pl

from quantide.audit.checks import future_invariance_check
from quantide.audit.future import NUMERIC_DTYPES, frame_digest
from quantide.audit.models import (
    AuditCheck,
    AuditReport,
    AuditSpec,
    AuditStatus,
    FirstDifference,
    canonical_hash,
)
from quantide.audit.runner import AuditRunner
from quantide.factors.alpha import FACTOR_VERSION, compute_alpha_features
from quantide.factors.metadata import (
    FACTOR_METADATA,
    factor_definition,
    normalized_tracking_defaults,
    validate_factor_metadata,
)

_REQUIRED_RAW = {
    "date",
    "asset",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "available_at",
}
DEFAULT_POSITIVE_COLUMNS: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)


def _duplicate_key(frame: pl.DataFrame) -> tuple[Any, Any, int] | None:
    counts = (
        frame.group_by(["date", "asset"]).len().filter(pl.col("len") > 1).sort(["date", "asset"])
    )
    if counts.is_empty():
        return None
    row = counts.row(0, named=True)
    return row["date"], row["asset"], int(row["len"])


def _is_sorted(frame: pl.DataFrame) -> bool:
    ordered = frame.select(["asset", "date"]).sort(["asset", "date"])
    return bool(frame.select(["asset", "date"]).equals(ordered))


def _schema_check(frame: pl.DataFrame, factor: str) -> AuditCheck:
    missing = sorted(_REQUIRED_RAW - set(frame.columns))
    if missing:
        return AuditCheck(
            "factor.schema",
            True,
            AuditStatus.FAIL,
            message=f"missing input columns: {missing}",
        )
    if factor not in FACTOR_METADATA:
        return AuditCheck("factor.schema", True, AuditStatus.FAIL, message="unknown factor")
    for column in ("date", "available_at"):
        if frame[column].dtype not in (pl.Date, pl.Datetime):
            return AuditCheck(
                "factor.schema",
                True,
                AuditStatus.FAIL,
                message=f"{column} must be a date or datetime column",
            )
    non_numeric = [
        column
        for column in ("open", "high", "low", "close", "volume")
        if frame[column].dtype not in NUMERIC_DTYPES
    ]
    if non_numeric:
        return AuditCheck(
            "factor.schema",
            True,
            AuditStatus.FAIL,
            message=f"non-numeric price/volume columns: {sorted(non_numeric)}",
        )
    duplicate = _duplicate_key(frame)
    if duplicate is not None:
        day, asset, count = duplicate
        return AuditCheck(
            "factor.schema",
            True,
            AuditStatus.FAIL,
            message=f"duplicate date/asset key: {day} {asset} ({count} rows)",
            first_difference=FirstDifference(
                time=str(day),
                asset=str(asset),
                column="(date, asset)",
                expected="unique key",
                actual=f"{count} rows",
                kind="duplicate_key",
            ),
        )
    if not _is_sorted(frame):
        return AuditCheck(
            "factor.schema",
            True,
            AuditStatus.FAIL,
            message="input must be sorted by asset then date",
        )
    if frame["available_at"].null_count():
        return AuditCheck(
            "factor.schema",
            True,
            AuditStatus.FAIL,
            message="missing availability values",
        )
    output = compute_alpha_features(frame)
    missing_output = {"date", "asset", factor} - set(output.columns)
    if missing_output:
        return AuditCheck(
            "factor.schema",
            True,
            AuditStatus.FAIL,
            message=f"missing output columns: {sorted(missing_output)}",
        )
    values = output[factor].to_list()
    if not any(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values):
        return AuditCheck(
            "factor.schema",
            True,
            AuditStatus.INCONCLUSIVE,
            message="factor produced no valid values in sample",
            sample_size=output.height,
        )
    return AuditCheck("factor.schema", True, AuditStatus.PASS, sample_size=output.height)


def _determinism_check(frame: pl.DataFrame, factor: str) -> AuditCheck:
    first = compute_alpha_features(frame).select(["date", "asset", factor])
    second = compute_alpha_features(frame).select(["date", "asset", factor])
    if frame_digest(first) != frame_digest(second):
        return AuditCheck(
            "factor.deterministic",
            True,
            AuditStatus.FAIL,
            message="repeated factor runs differ",
        )
    return AuditCheck("factor.deterministic", True, AuditStatus.PASS, sample_size=first.height)


def _metadata_check(factor: str) -> AuditCheck:
    definition = factor_definition(factor)
    validate_factor_metadata()
    if definition.factor_id != factor:
        return AuditCheck("factor.metadata", True, AuditStatus.FAIL, message="factor id mismatch")
    defaults = normalized_tracking_defaults(factor)
    return AuditCheck(
        "factor.metadata",
        True,
        AuditStatus.PASS,
        details={
            "defaults_version": defaults.defaults_version,
            "defaults_source": defaults.source,
            "factor_version": FACTOR_VERSION,
        },
    )


def _interior_cutoffs(frame: pl.DataFrame, count: int = 2) -> tuple[dt.date, ...]:
    if "date" not in frame.columns:
        return ()
    dates = sorted(set(frame["date"].to_list()))
    if len(dates) < 2:
        return ()
    chosen: list[dt.date] = []
    for index in range(1, count + 1):
        position = min(int(len(dates) * index / (count + 1)), len(dates) - 2)
        chosen.append(dates[max(position, 0)])
    return tuple(dict.fromkeys(chosen))


def _resolve_cutoffs(
    frame: pl.DataFrame,
    cutoff: dt.date | None,
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None,
) -> tuple[dt.date, ...]:
    if cutoff is not None and cutoffs is not None:
        raise ValueError("pass either cutoff or cutoffs, not both")
    if cutoffs is not None:
        resolved = tuple(cutoffs)
    elif cutoff is not None:
        resolved = (cutoff,)
    else:
        resolved = _interior_cutoffs(frame)
    if any(not isinstance(value, dt.date) for value in resolved):
        raise ValueError("cutoffs must be dates")
    return resolved


def build_factor_spec(
    frame: pl.DataFrame,
    factor: str,
    *,
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None = None,
    modes: tuple[str, ...] = ("random", "zero", "extreme"),
    seeds: tuple[int, ...] = (0,),
    positive_columns: tuple[str, ...] = DEFAULT_POSITIVE_COLUMNS,
) -> AuditSpec:
    definition = factor_definition(factor)
    resolved_cutoffs = tuple(cutoffs) if cutoffs is not None else _interior_cutoffs(frame)
    return AuditSpec(
        spec_id=f"factor:{factor}:{FACTOR_VERSION}",
        object_type="factor",
        object_id=factor,
        source_hash=FACTOR_VERSION,
        data_hash=frame_digest(frame),
        config_hash=canonical_hash(
            {
                "factor": factor,
                "group": definition.group,
                "parameters": definition.parameters,
                "cutoffs": [value.isoformat() for value in resolved_cutoffs],
                "modes": list(modes),
                "seeds": list(seeds),
                "positive_columns": list(positive_columns),
            }
        ),
        interval="1d",
        timezone="Asia/Shanghai",
        availability_contract="factor at t0 after t0 close; labels use t1 entry and t(h+1) exit",
        truncation_points=tuple(value.isoformat() for value in resolved_cutoffs),
        seed_set=tuple(seeds),
        statistical_profile="factor-panel",
    )


def _future_invariance_check(
    check_id: str,
    pipeline: Any,
    frame: pl.DataFrame,
    cutoffs: tuple[dt.date, ...],
    modes: tuple[str, ...],
    seeds: tuple[int, ...],
    positive_columns: tuple[str, ...],
) -> AuditCheck:
    if not cutoffs:
        return AuditCheck(
            check_id,
            True,
            AuditStatus.INCONCLUSIVE,
            message="no truncation cutoffs available for future perturbation",
        )
    failures: list[AuditCheck] = []
    without_evidence: list[AuditCheck] = []
    for cutoff in cutoffs:
        check = future_invariance_check(
            f"{check_id}:{cutoff.isoformat()}",
            pipeline,
            frame,
            cutoff,
            modes=modes,
            seeds=seeds,
            positive_columns=positive_columns,
        )
        if check.status is AuditStatus.FAIL:
            failures.append(check)
        elif check.status is not AuditStatus.PASS:
            without_evidence.append(check)
    details = {
        "cutoffs": [value.isoformat() for value in cutoffs],
        "modes": list(modes),
        "seeds": list(seeds),
    }
    if failures:
        return AuditCheck(
            check_id,
            True,
            AuditStatus.FAIL,
            message=failures[0].message,
            first_difference=failures[0].first_difference,
            details={
                **details,
                "failed_cutoffs": [item.check_id.rsplit(":", 1)[-1] for item in failures],
            },
        )
    if without_evidence:
        return AuditCheck(
            check_id,
            True,
            AuditStatus.INCONCLUSIVE,
            message=without_evidence[0].message,
            details={
                **details,
                "cutoffs_without_evidence": [
                    item.check_id.rsplit(":", 1)[-1] for item in without_evidence
                ],
            },
        )
    return AuditCheck(check_id, True, AuditStatus.PASS, sample_size=frame.height, details=details)


_SPEC_FIELDS = (
    "spec_id",
    "object_type",
    "object_id",
    "source_hash",
    "data_hash",
    "config_hash",
    "interval",
    "timezone",
    "availability_contract",
    "seed_set",
    "truncation_points",
    "statistical_profile",
)


def _spec_mismatches(declared: AuditSpec, expected: AuditSpec) -> list[str]:
    return [field for field in _SPEC_FIELDS if getattr(declared, field) != getattr(expected, field)]


def audit_factor(
    frame: pl.DataFrame,
    factor: str,
    *,
    spec: AuditSpec | None = None,
    cutoff: dt.date | None = None,
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None = None,
    modes: tuple[str, ...] = ("random", "zero", "extreme"),
    seeds: tuple[int, ...] = (0,),
    positive_columns: tuple[str, ...] = DEFAULT_POSITIVE_COLUMNS,
) -> AuditReport:
    resolved_cutoffs = _resolve_cutoffs(frame, cutoff, cutoffs)
    expected_spec = build_factor_spec(
        frame,
        factor,
        cutoffs=resolved_cutoffs,
        modes=modes,
        seeds=seeds,
        positive_columns=positive_columns,
    )
    if spec is not None:
        mismatches = _spec_mismatches(spec, expected_spec)
        if mismatches:
            raise ValueError(
                "explicit spec does not match the executed audit: " + ", ".join(mismatches)
            )
        resolved_spec = spec
    else:
        resolved_spec = expected_spec

    def pipeline(data: pl.DataFrame) -> pl.DataFrame:
        return compute_alpha_features(data).select(["date", "asset", factor])

    registry = {
        "factor.schema": (lambda _: _schema_check(frame, factor), True),
        "factor.metadata": (lambda _: _metadata_check(factor), True),
        "factor.deterministic": (lambda _: _determinism_check(frame, factor), True),
        "factor.future_invariance": (
            lambda _: _future_invariance_check(
                "factor.future_invariance",
                pipeline,
                frame,
                resolved_cutoffs,
                modes,
                seeds,
                positive_columns,
            ),
            True,
        ),
    }
    return AuditRunner(registry).run(resolved_spec)

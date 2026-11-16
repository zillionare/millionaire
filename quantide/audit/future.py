"""Future-data perturbation checks for deterministic frame pipelines."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import math
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

FramePipeline = Callable[[pl.DataFrame], pl.DataFrame]
NUMERIC_DTYPES = frozenset(
    {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    }
)
INTEGER_DTYPES = frozenset(
    {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    }
)
_KEY_COLUMNS = frozenset({"date", "asset", "available_at"})


@dataclass(frozen=True)
class PerturbationResult:
    mode: str
    seed: int
    passed: bool
    message: str = ""
    expected_digest: str = ""
    actual_digest: str = ""
    perturbed_rows: int = 0
    changed_cells: int = 0
    compared_rows: int = 0
    effective_values: int = 0
    first_difference: dict[str, Any] = field(default_factory=dict)


def frame_digest(frame: pl.DataFrame) -> str:
    buffer = io.BytesIO()
    frame.write_ipc(buffer, compression="uncompressed")
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def _as_datetime(value: Any, *, end_of_day: bool) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    moment = dt.time.max if end_of_day else dt.time.min
    return dt.datetime.combine(value, moment)


def _is_future(value: Any, cutoff: Any) -> bool:
    """Compare availability at native precision; a date cutoff covers that day."""
    if isinstance(value, dt.datetime) or isinstance(cutoff, dt.datetime):
        left = _as_datetime(value, end_of_day=False)
        right = _as_datetime(cutoff, end_of_day=not isinstance(cutoff, dt.datetime))
        if left.tzinfo is None and right.tzinfo is not None:
            left = left.replace(tzinfo=right.tzinfo)
        elif left.tzinfo is not None and right.tzinfo is None:
            right = right.replace(tzinfo=left.tzinfo)
        return bool(left > right)
    return bool(value > cutoff)


def _future_rows(frame: pl.DataFrame, cutoff: Any, available_col: str) -> list[int]:
    if available_col not in frame.columns:
        raise ValueError(f"frame missing availability column: {available_col}")
    values = frame[available_col].to_list()
    return [
        index
        for index, value in enumerate(values)
        if value is not None and not _is_null(value) and _is_future(value, cutoff)
    ]


def _is_null(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _bounds(series: pl.Series) -> tuple[float, float]:
    finite = [
        float(value)
        for value in series.to_list()
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    if not finite:
        return 0.0, 0.0
    return min(finite), max(finite)


def _replacements(
    series: pl.Series,
    mode: str,
    seed: int,
    positive: bool,
    column: str,
    count: int,
) -> list[Any]:
    low, high = _bounds(series)
    if mode == "zero":
        return [max(1.0, low) if positive else 0.0] * count
    if mode == "extreme":
        base = max(abs(low), abs(high), 1.0)
        return [base * 10.0] * count
    if mode == "random":
        minimum = max(low, 1e-6) if positive else low
        if high <= minimum:
            value = max(minimum, 1.0) if positive else 0.0
            return [value] * count
        generator = random.Random(f"{seed}:{column}")
        return [generator.uniform(minimum, high) for _ in range(count)]
    raise ValueError(f"unknown perturbation mode: {mode}")


def perturb_frame(
    frame: pl.DataFrame,
    cutoff: Any,
    mode: str,
    seed: int = 0,
    *,
    available_col: str = "available_at",
    positive_columns: Iterable[str] = (),
) -> pl.DataFrame:
    """Perturb numeric future rows; identity and categorical columns stay intact."""
    future = _future_rows(frame, cutoff, available_col)
    if not future:
        return frame.clone()
    positive = set(positive_columns)
    result = frame.clone()
    for column in frame.columns:
        dtype = frame[column].dtype
        if column == available_col or dtype not in NUMERIC_DTYPES:
            continue
        replacements = _replacements(
            frame[column], mode, seed, column in positive, column, len(future)
        )
        values = frame[column].to_list()
        for index, value in zip(future, replacements, strict=True):
            values[index] = round(value) if dtype in INTEGER_DTYPES else value
        result = result.with_columns(pl.Series(column, values, dtype=dtype))
    return result


def _before_cutoff(frame: pl.DataFrame, date_col: str, cutoff: Any) -> pl.DataFrame:
    if date_col not in frame.columns:
        raise ValueError(f"pipeline output missing date column: {date_col}")
    dtype = frame[date_col].dtype
    if dtype == pl.Datetime and not isinstance(cutoff, dt.datetime):
        cutoff = dt.datetime.combine(cutoff, dt.time.max)
    elif dtype == pl.Date and isinstance(cutoff, dt.datetime):
        cutoff = cutoff.date()
    return frame.filter(pl.col(date_col) <= cutoff)


def _first_difference(
    expected: pl.DataFrame, actual: pl.DataFrame, date_col: str
) -> dict[str, Any]:
    expected_rows = expected.to_dicts()
    actual_rows = actual.to_dicts()
    for index, (left, right) in enumerate(zip(expected_rows, actual_rows, strict=False)):
        if left != right:
            columns = sorted(
                key for key in set(left) | set(right) if left.get(key) != right.get(key)
            )
            column = columns[0] if columns else ""
            return {
                "row": index,
                "time": str(left.get(date_col, "")),
                "asset": str(left.get("asset", "")),
                "column": column,
                "expected": left.get(column),
                "actual": right.get(column),
                "kind": "future_dependency",
            }
    if expected.height != actual.height:
        return {
            "row": min(expected.height, actual.height),
            "time": "",
            "asset": "",
            "column": "",
            "expected": expected.height,
            "actual": actual.height,
            "kind": "row_count_mismatch",
        }
    return {}


def _numeric_columns(frame: pl.DataFrame, available_col: str) -> list[str]:
    return [
        column
        for column in frame.columns
        if column != available_col and frame[column].dtype in NUMERIC_DTYPES
    ]


def _changed_cells(
    original: pl.DataFrame,
    perturbed: pl.DataFrame,
    indices: list[int],
    columns: list[str],
) -> int:
    changed = 0
    for column in columns:
        before = original[column].to_list()
        after = perturbed[column].to_list()
        changed += sum(1 for index in indices if before[index] != after[index])
    return changed


def effective_values(frame: pl.DataFrame) -> int:
    """Count finite numeric values in pipeline output outside identity columns."""
    total = 0
    for column in frame.columns:
        if column in _KEY_COLUMNS or frame[column].dtype not in NUMERIC_DTYPES:
            continue
        total += sum(
            1
            for value in frame[column].to_list()
            if isinstance(value, (int, float)) and math.isfinite(float(value))
        )
    return total


@dataclass(frozen=True)
class _RunOptions:
    pipeline: FramePipeline
    baseline: pl.DataFrame
    cutoff: Any
    expected_digest: str
    date_col: str
    available_col: str
    positive_columns: tuple[str, ...]


def _output_result(
    perturbed: pl.DataFrame,
    options: _RunOptions,
) -> tuple[pl.DataFrame, str]:
    output = _before_cutoff(options.pipeline(perturbed), options.date_col, options.cutoff)
    return output, frame_digest(output)


def _run_perturbation(
    frame: pl.DataFrame,
    mode: str,
    seed: int,
    options: _RunOptions,
) -> PerturbationResult:
    future = _future_rows(frame, options.cutoff, options.available_col)
    compared_rows = options.baseline.height
    evidence = effective_values(options.baseline)
    if not future:
        return PerturbationResult(
            mode=mode,
            seed=seed,
            passed=False,
            message="no future rows to perturb at this cutoff",
            expected_digest=options.expected_digest,
            actual_digest=options.expected_digest,
            perturbed_rows=0,
            compared_rows=compared_rows,
            effective_values=evidence,
        )
    perturbed = perturb_frame(
        frame,
        options.cutoff,
        mode,
        seed,
        available_col=options.available_col,
        positive_columns=options.positive_columns,
    )
    changed = _changed_cells(
        frame,
        perturbed,
        future,
        _numeric_columns(frame, options.available_col),
    )
    if not changed:
        return PerturbationResult(
            mode=mode,
            seed=seed,
            passed=False,
            message="perturbation did not change any input value",
            expected_digest=options.expected_digest,
            actual_digest=options.expected_digest,
            perturbed_rows=len(future),
            changed_cells=0,
            compared_rows=compared_rows,
            effective_values=evidence,
        )
    output, actual_digest = _output_result(perturbed, options)
    passed = actual_digest == options.expected_digest
    return PerturbationResult(
        mode=mode,
        seed=seed,
        passed=passed,
        message="" if passed else "future rows changed pre-cutoff output",
        expected_digest=options.expected_digest,
        actual_digest=actual_digest,
        perturbed_rows=len(future),
        changed_cells=changed,
        compared_rows=compared_rows,
        effective_values=evidence,
        first_difference=(
            {} if passed else _first_difference(options.baseline, output, options.date_col)
        ),
    )


def assert_future_invariance(
    pipeline: FramePipeline,
    frame: pl.DataFrame,
    cutoff: Any,
    *,
    modes: tuple[str, ...] = ("random", "zero", "extreme"),
    seeds: tuple[int, ...] = (0,),
    date_col: str = "date",
    available_col: str = "available_at",
    positive_columns: Iterable[str] = (),
) -> list[PerturbationResult]:
    baseline = _before_cutoff(pipeline(frame), date_col, cutoff)
    options = _RunOptions(
        pipeline=pipeline,
        baseline=baseline,
        cutoff=cutoff,
        expected_digest=frame_digest(baseline),
        date_col=date_col,
        available_col=available_col,
        positive_columns=tuple(positive_columns),
    )
    return [_run_perturbation(frame, mode, seed, options) for mode in modes for seed in seeds]


def cutoff_from_frame(frame: pl.DataFrame, date_col: str = "date") -> Any:
    if date_col not in frame.columns or frame.is_empty():
        raise ValueError("frame has no dates")
    return frame[date_col].max()

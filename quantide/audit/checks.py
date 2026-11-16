"""Adapters that turn audit primitives into report checks."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import polars as pl

from quantide.audit.account import AccountLedger
from quantide.audit.future import FramePipeline, PerturbationResult, assert_future_invariance
from quantide.audit.models import AuditCheck, AuditStatus, FirstDifference


def _has_comparison_evidence(result: PerturbationResult) -> bool:
    return (
        result.perturbed_rows > 0
        and result.changed_cells > 0
        and result.compared_rows > 0
        and result.effective_values > 0
    )


def future_invariance_check(
    check_id: str,
    pipeline: FramePipeline,
    frame: pl.DataFrame,
    cutoff: Any,
    *,
    modes: tuple[str, ...] = ("random", "zero", "extreme"),
    seeds: tuple[int, ...] = (0,),
    date_col: str = "date",
    available_col: str = "available_at",
    positive_columns: Iterable[str] = (),
) -> AuditCheck:
    results = assert_future_invariance(
        pipeline,
        frame,
        cutoff,
        modes=modes,
        seeds=seeds,
        date_col=date_col,
        available_col=available_col,
        positive_columns=positive_columns,
    )
    if not results:
        return AuditCheck(
            check_id=check_id,
            required=True,
            status=AuditStatus.INCONCLUSIVE,
            message="no perturbation runs were requested",
            sample_size=frame.height,
        )
    failed = next(
        (result for result in results if not result.passed and _has_comparison_evidence(result)),
        None,
    )
    if failed is not None:
        difference = failed.first_difference
        return AuditCheck(
            check_id=check_id,
            required=True,
            status=AuditStatus.FAIL,
            message=f"{failed.mode}/{failed.seed}: {failed.message}",
            sample_size=frame.height,
            first_difference=FirstDifference(
                time=str(difference.get("time", "")),
                asset=str(difference.get("asset", "")),
                column=str(difference.get("column", "")),
                expected=difference.get("expected"),
                actual=difference.get("actual"),
                kind=str(difference.get("kind", "future_dependency")),
                minimal_input={"row": difference.get("row")},
            ),
            details={"mode": failed.mode, "seed": failed.seed},
        )
    without_evidence = [result for result in results if not _has_comparison_evidence(result)]
    if without_evidence:
        reasons = []
        for result in without_evidence:
            if result.perturbed_rows == 0:
                reasons.append(f"{result.mode}/{result.seed}: no future rows")
            elif result.changed_cells == 0:
                reasons.append(f"{result.mode}/{result.seed}: {result.message}")
            else:
                reasons.append(f"{result.mode}/{result.seed}: no comparable pre-cutoff output")
        return AuditCheck(
            check_id=check_id,
            required=True,
            status=AuditStatus.INCONCLUSIVE,
            message="; ".join(dict.fromkeys(reasons)),
            sample_size=frame.height,
            details={
                "modes": list(modes),
                "seeds": list(seeds),
                "perturbed_rows": without_evidence[0].perturbed_rows,
                "changed_cells": without_evidence[0].changed_cells,
                "compared_rows": without_evidence[0].compared_rows,
                "effective_values": without_evidence[0].effective_values,
            },
        )
    return AuditCheck(
        check_id=check_id,
        required=True,
        status=AuditStatus.PASS,
        sample_size=frame.height,
        details={
            "modes": list(modes),
            "seeds": list(seeds),
            "expected_digest": results[0].expected_digest if results else "",
            "perturbed_rows": results[0].perturbed_rows,
            "changed_cells": results[0].changed_cells,
            "compared_rows": results[0].compared_rows,
            "effective_values": results[0].effective_values,
        },
    )


def ledger_invariant_check(check_id: str, ledger: AccountLedger) -> AuditCheck:
    errors = ledger.validate()
    if not errors:
        return AuditCheck(check_id, True, AuditStatus.PASS)
    return AuditCheck(
        check_id,
        True,
        AuditStatus.FAIL,
        message="; ".join(errors),
        first_difference=FirstDifference(
            time="",
            asset="",
            column="account",
            expected="conserved account",
            actual="; ".join(errors),
            kind="invariant_violation",
        ),
    )


def callback_check(
    check_id: str,
    callback: Callable[[], AuditCheck],
    *,
    required: bool = True,
) -> AuditCheck:
    check = callback()
    return AuditCheck(
        check_id=check_id,
        required=required,
        status=check.status,
        message=check.message,
        duration_ms=check.duration_ms,
        sample_size=check.sample_size,
        first_difference=check.first_difference,
        details=check.details,
    )

"""Future-data perturbation tests."""

from __future__ import annotations

import datetime as dt

import polars as pl

from quantide.audit.checks import future_invariance_check, ledger_invariant_check
from quantide.audit.future import (
    PerturbationResult,
    assert_future_invariance,
    cutoff_from_frame,
    frame_digest,
    perturb_frame,
)
from quantide.audit.models import AuditStatus


def _frame() -> pl.DataFrame:
    dates = [dt.date(2024, 1, day) for day in range(1, 6)]
    rows = []
    for asset in ("000001", "000002"):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "asset": asset,
                    "date": day,
                    "available_at": day,
                    "x": float(index + 1),
                    "price": 10.0 + index,
                }
            )
    return pl.DataFrame(rows)


def _good_pipeline(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns((pl.col("x") - pl.col("x").shift(1).over("asset")).alias("signal"))


def _bad_pipeline(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns((pl.col("x") - pl.col("x").mean()).alias("signal"))


def test_frame_digest_is_stable() -> None:
    assert frame_digest(_frame()) == frame_digest(_frame())
    assert frame_digest(_frame()) != frame_digest(_frame().filter(pl.col("asset") == "000001"))


def test_perturbation_only_changes_future_rows() -> None:
    frame = _frame()
    cutoff = dt.date(2024, 1, 3)
    perturbed = perturb_frame(frame, cutoff, "zero", positive_columns=("price",))
    before = frame.filter(pl.col("date") <= cutoff)
    after = perturbed.filter(pl.col("date") <= cutoff)
    assert before.equals(after)
    future = perturbed.filter(pl.col("date") > cutoff)
    assert future["x"].to_list() == [0.0] * future.height
    assert all(value > 0 for value in future["price"].to_list())
    assert cutoff_from_frame(frame) == dt.date(2024, 1, 5)


def test_future_perturbation_passes_independent_shift() -> None:
    results = assert_future_invariance(
        _good_pipeline,
        _frame(),
        dt.date(2024, 1, 3),
        modes=("zero", "random", "extreme"),
        seeds=(3,),
    )
    assert all(result.passed for result in results)
    assert all(result.expected_digest == result.actual_digest for result in results)


def test_future_perturbation_fails_full_sample_leak() -> None:
    results = assert_future_invariance(
        _bad_pipeline,
        _frame(),
        dt.date(2024, 1, 3),
        modes=("zero",),
        positive_columns=("price",),
    )
    assert len(results) == 1
    assert not results[0].passed
    assert results[0].first_difference["kind"] == "future_dependency"
    assert results[0].first_difference["time"] == "2024-01-01"


def test_check_adapter_reports_pass_and_failure() -> None:
    good = future_invariance_check(
        "future",
        _good_pipeline,
        _frame(),
        dt.date(2024, 1, 3),
        modes=("zero",),
        positive_columns=("price",),
    )
    assert good.status is AuditStatus.PASS
    bad = future_invariance_check(
        "future",
        _bad_pipeline,
        _frame(),
        dt.date(2024, 1, 3),
        modes=("zero",),
        positive_columns=("price",),
    )
    assert bad.status is AuditStatus.FAIL
    assert bad.first_difference is not None
    assert bad.first_difference.kind == "future_dependency"
    empty = future_invariance_check(
        "future",
        _good_pipeline,
        _frame(),
        dt.date(2024, 1, 3),
        modes=(),
        seeds=(),
    )
    assert empty.status is AuditStatus.INCONCLUSIVE


def test_intraday_availability_compares_full_precision() -> None:
    moments = [
        dt.datetime(2024, 1, 2, 10, 0),
        dt.datetime(2024, 1, 2, 10, 30),
        dt.datetime(2024, 1, 2, 11, 0),
    ]
    frame = pl.DataFrame(
        {
            "asset": ["a"] * 3,
            "date": moments,
            "available_at": moments,
            "x": [1.0, 2.0, 3.0],
        }
    )

    def leaky(data: pl.DataFrame) -> pl.DataFrame:
        return data.with_columns((pl.col("x") - pl.col("x").mean()).alias("signal"))

    results = assert_future_invariance(
        leaky,
        frame,
        moments[1],
        modes=("zero",),
        date_col="date",
    )
    assert results[0].perturbed_rows == 1
    assert not results[0].passed


def test_clear_failure_dominates_inconclusive_perturbations() -> None:
    dates = [dt.date(2024, 1, day) for day in range(1, 4)]
    frame = pl.DataFrame(
        {
            "asset": ["a"] * 3,
            "date": dates,
            "available_at": dates,
            "x": [0.0, 0.0, 0.0],
        }
    )

    def leaky(data: pl.DataFrame) -> pl.DataFrame:
        return data.with_columns((pl.col("x") - pl.col("x").mean()).alias("signal"))

    check = future_invariance_check(
        "future",
        leaky,
        frame,
        dates[0],
        modes=("zero", "extreme"),
    )
    assert check.status is AuditStatus.FAIL
    assert check.first_difference is not None
    assert check.first_difference.column == "signal"
    assert check.details["mode"] == "extreme"


def test_failure_without_comparison_evidence_remains_inconclusive(monkeypatch) -> None:
    from quantide.audit import checks

    results = [
        PerturbationResult(
            mode="extreme",
            seed=0,
            passed=False,
            message="future rows changed pre-cutoff output",
            changed_cells=0,
        )
    ]
    monkeypatch.setattr(checks, "assert_future_invariance", lambda *args, **kwargs: results)
    check = checks.future_invariance_check(
        "future",
        _good_pipeline,
        _frame(),
        dt.date(2024, 1, 3),
    )
    assert check.status is AuditStatus.INCONCLUSIVE


def test_cutoff_without_future_rows_is_inconclusive() -> None:
    check = future_invariance_check(
        "future",
        _good_pipeline,
        _frame(),
        dt.date(2024, 1, 5),
        modes=("zero",),
    )
    assert check.status is AuditStatus.INCONCLUSIVE
    assert "no future rows" in check.message


def test_empty_pipeline_output_is_inconclusive() -> None:
    check = future_invariance_check(
        "future",
        lambda data: data.head(0),
        _frame(),
        dt.date(2024, 1, 3),
        modes=("zero",),
    )
    assert check.status is AuditStatus.INCONCLUSIVE
    assert "no comparable pre-cutoff output" in check.message


def test_perturbation_without_input_change_is_inconclusive() -> None:
    d1, d2 = dt.date(2024, 1, 1), dt.date(2024, 1, 2)
    frame = pl.DataFrame(
        {
            "asset": ["a", "a"],
            "date": [d1, d2],
            "available_at": [d1, d2],
            "x": [0.0, 0.0],
            "price": [0.0, 0.0],
        }
    )
    check = future_invariance_check(
        "future",
        lambda data: data.with_columns((pl.col("x") + 1).alias("signal")),
        frame,
        d1,
        modes=("zero",),
        positive_columns=(),
    )
    assert check.status is AuditStatus.INCONCLUSIVE
    assert "did not change any input value" in check.message


def test_random_perturbation_varies_values_per_row() -> None:
    cutoff = dt.date(2024, 1, 3)
    first = perturb_frame(_frame(), cutoff, "random", seed=5)
    second = perturb_frame(_frame(), cutoff, "random", seed=5)
    future = first.filter(pl.col("date") > cutoff)
    assert len(set(future["x"].to_list())) > 1
    assert first.equals(second)


def test_ledger_invariant_check_reports_errors() -> None:
    from quantide.audit.account import AccountLedger

    ledger = AccountLedger(100)
    passed = ledger_invariant_check("ledger", ledger)
    assert passed.status is AuditStatus.PASS
    ledger.cash = -1
    failed = ledger_invariant_check("ledger", ledger)
    assert failed.status is AuditStatus.FAIL
    assert "negative" in failed.message

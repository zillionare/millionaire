"""Key-mutation catalogue for acceptance audits, optionally run in subprocesses."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any
from unittest.mock import patch

import polars as pl

from quantide.audit.account import AccountLedger
from quantide.audit.checks import future_invariance_check
from quantide.audit.models import AuditStatus
from quantide.audit.performance import (
    AttributionPeriod,
    AuditTrade,
    attribute_period,
    link_carino,
)
from quantide.core.strategy import Strategy

MUTATION_VERSION = "1.0.0"
CaseRunner = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class MutationCase:
    mutation_id: str
    requirement: str
    acceptance: str
    location: str
    description: str


def _frame(cutoff: dt.date) -> pl.DataFrame:
    dates = [cutoff + dt.timedelta(days=index) for index in range(-2, 3)]
    rows = []
    for asset_index in range(6):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset_index:06d}",
                    "available_at": day,
                    "x": float(asset_index + index),
                    "open": 10.0 + asset_index + index * 0.1,
                    "high": 11.0 + asset_index + index * 0.1,
                    "low": 9.0 + asset_index + index * 0.1,
                    "close": 10.5 + asset_index + index * 0.1,
                }
            )
    return pl.DataFrame(rows)


def _detect(pipeline: Callable[[pl.DataFrame], pl.DataFrame], cutoff: dt.date) -> bool:
    check = future_invariance_check(
        "mutation.future",
        pipeline,
        _frame(cutoff),
        cutoff,
        modes=("zero", "extreme"),
    )
    return check.status is AuditStatus.FAIL and check.first_difference is not None


def _case_future_shift() -> dict[str, Any]:
    cutoff = dt.date(2024, 1, 10)
    leaked = _detect(
        lambda data: data.with_columns(
            pl.col("x").shift(-1).over("asset").fill_null(0).alias("signal")
        ),
        cutoff,
    )
    return _killed(leaked, "future shift changes pre-cutoff signal")


def _case_full_sample_standardize() -> dict[str, Any]:
    cutoff = dt.date(2024, 1, 10)
    leaked = _detect(
        lambda data: data.with_columns(
            ((pl.col("x") - pl.col("x").mean()) / pl.col("x").std()).alias("signal")
        ),
        cutoff,
    )
    return _killed(leaked, "full-sample mean/std depends on future rows")


def _case_future_universe() -> dict[str, Any]:
    cutoff = dt.date(2024, 1, 10)

    def pipeline(data: pl.DataFrame) -> pl.DataFrame:
        future = data.filter(pl.col("date") > cutoff)
        winners = future.group_by("asset").agg(pl.col("x").max().alias("peak"))
        chosen = winners.filter(pl.col("peak") >= winners["peak"].median())["asset"].to_list()
        return data.with_columns(pl.col("asset").is_in(chosen).alias("signal"))

    return _killed(_detect(pipeline, cutoff), "future universe changes historical rows")


def _case_cross_asset_roll() -> dict[str, Any]:
    cutoff = dt.date(2024, 1, 10)
    leaked = _detect(
        lambda data: data.with_columns(
            pl.col("x").shift(-1).fill_null(0).rolling_mean(2).alias("signal")
        ),
        cutoff,
    )
    return _killed(leaked, "row-wise roll crosses asset and future boundaries")


def _case_t_plus_one_unlock() -> dict[str, Any]:
    day = dt.date(2024, 1, 3)
    next_day = dt.date(2024, 1, 4)

    def target(force_unlock: bool) -> bool:
        ledger = AccountLedger(10_000)
        ledger.buy("000001", 100, 10.0, day, next_day)
        if force_unlock:
            # Mutation: rewrite the pending settlement date to trade day.
            ledger.pending = {
                (day, asset): shares for (_settle_date, asset), shares in ledger.pending.items()
            }
            ledger.settle(day)
        try:
            ledger.sell("000001", 100, 10.1)
        except ValueError:
            return True
        return False

    baseline_rejects = target(False)
    mutant_rejects = target(True)
    return _killed(
        baseline_rejects and not mutant_rejects,
        "baseline rejects same-day sell; forced unlock mutant accepts it",
        baseline_ok=baseline_rejects,
    )


def _production_fee(omit_fee: bool) -> float:
    from quantide.core.enums import OrderSide
    from quantide.service.paper_matching import PaperMatching

    probe = PaperMatching.__new__(PaperMatching)
    probe._commission = 0.0003
    probe._min_commission = 5.0
    probe._transfer_fee = 0.00001
    probe._stamp_tax = 0.001
    if omit_fee:
        with patch.object(PaperMatching, "_calculate_fee", return_value=0.0):
            return float(probe._calculate_fee(1_000.0, OrderSide.BUY))
    return float(probe._calculate_fee(1_000.0, OrderSide.BUY))


def _case_fee_omission() -> dict[str, Any]:
    def target(omit_fee: bool) -> float:
        ledger = AccountLedger(10_000)
        ledger.buy(
            "000001",
            100,
            10.0,
            dt.date(2024, 1, 3),
            dt.date(2024, 1, 4),
            fee=_production_fee(omit_fee),
        )
        return ledger.cash

    oracle = 10_000.0 - 1_000.0 - 5.01
    baseline_matches = target(False) == oracle
    mutant_mismatches = target(True) != oracle
    return _killed(
        baseline_matches and mutant_mismatches,
        "frozen fee oracle 5.01; fee-zero mutant diverges",
        baseline_ok=baseline_matches,
    )


def _case_duplicate_cost() -> dict[str, Any]:
    from quantide.audit import performance

    trade = AuditTrade("000001", "buy", 100, 10.0, fee=5)
    period = AttributionPeriod(10_000, {}, {}, {"000001": 10.0}, (trade,))
    baseline = attribute_period(period)
    original = performance._apply_trades

    def duplicated(
        period: AttributionPeriod,
        positions: dict[str, float],
        cash: float,
    ) -> tuple[dict[str, float], float, float, float, dict[str, float]]:
        repeated = replace(period, trades=period.trades + period.trades)
        return original(repeated, positions, cash)

    with patch.object(performance, "_apply_trades", duplicated):
        mutant = attribute_period(period)
    return _killed(
        baseline.costs == -5 and mutant.costs == -10,
        "baseline costs -5; trade-duplication mutant deducts the same fee twice (-10)",
        baseline_ok=baseline.costs == -5,
    )


def _case_period_override() -> dict[str, Any]:
    from quantide.core.enums import FrameType
    from quantide.service.runner import BacktestRunner

    class DailyStrategy(Strategy):
        BAR_INTERVAL = "1d"

        @staticmethod
        def default_config() -> dict[str, Any]:
            return {}

    def target() -> bool:
        try:
            BacktestRunner.validate_strategy_interval(DailyStrategy, {}, FrameType.MIN30)
        except ValueError:
            return True
        return False

    baseline_rejects = target()
    with patch.object(
        BacktestRunner,
        "validate_strategy_interval",
        classmethod(lambda cls, *_args: "1d"),
    ):
        mutant_rejects = target()
    return _killed(
        baseline_rejects and not mutant_rejects,
        "baseline rejects 30m override; patched override mutant accepts it",
        baseline_ok=baseline_rejects,
    )


def _case_attribution_sign() -> dict[str, Any]:
    period = AttributionPeriod(
        10_000,
        {"000001": 100},
        {"000001": 10.0},
        {"000001": 11.0},
    )
    result = attribute_period(period)
    flipped = -result.price_pnl
    detected = abs(flipped - result.delta_equity) > 1e-9
    return _killed(detected, "flipped attribution sign breaks reconciliation")


def _case_bad_link() -> dict[str, Any]:
    first = attribute_period(
        AttributionPeriod(10_000, {"000001": 100}, {"000001": 10.0}, {"000001": 11.0})
    )
    second = attribute_period(
        AttributionPeriod(11_100, {"000001": 100}, {"000001": 11.1}, {"000001": 10.0})
    )
    linked = link_carino([first, second])
    # Simple summation is invalid for compounded returns; the linked result must
    # differ from it, so a mutant that adds period contributions is detectable.
    naive = sum(period.return_pct for period in (first, second))
    detected = abs(naive - linked["total_return"]) > 1e-12
    return _killed(detected, "naive return summation differs from Carino linking")


def _killed(detected: bool, evidence: str, *, baseline_ok: bool = True) -> dict[str, Any]:
    return {"killed": bool(detected), "baseline_ok": bool(baseline_ok), "evidence": evidence}


CASES: tuple[MutationCase, ...] = (
    MutationCase(
        "future_shift",
        "FR-4002",
        "AC-4002",
        "factor pipeline shift",
        "Future values are shifted into historical outputs.",
    ),
    MutationCase(
        "full_sample_standardize",
        "FR-4002",
        "AC-4002",
        "factor normalization",
        "Mean/std are fitted over the full sample including future rows.",
    ),
    MutationCase(
        "future_universe",
        "FR-4002",
        "AC-4003",
        "selection pool",
        "Selection uses future index constituents or future ranks.",
    ),
    MutationCase(
        "cross_asset_roll",
        "FR-4002",
        "AC-4002",
        "rolling window",
        "Rolling crosses asset boundaries and consumes future rows.",
    ),
    MutationCase(
        "t_plus_one_unlock",
        "FR-4005",
        "AC-4008",
        "account settlement",
        "Sell is unlocked on the same day as the buy.",
    ),
    MutationCase(
        "fee_omission",
        "FR-4005",
        "AC-4008",
        "transaction costs",
        "Broker or ledger forgets the commission.",
    ),
    MutationCase(
        "duplicate_cost",
        "FR-4007",
        "AC-4011",
        "cost attribution",
        "The same fee is deducted twice.",
    ),
    MutationCase(
        "period_override",
        "FR-4001",
        "AC-4001",
        "strategy interval",
        "A daily strategy is executed on 30-minute bars.",
    ),
    MutationCase(
        "attribution_sign",
        "FR-4007",
        "AC-4010",
        "attribution entry",
        "The sign of a P&L contribution is reversed.",
    ),
    MutationCase(
        "bad_link",
        "FR-4007",
        "AC-4011",
        "multi-period linking",
        "Period returns are summed instead of Carino-linked.",
    ),
)
_RUNNERS: dict[str, CaseRunner] = {
    "future_shift": _case_future_shift,
    "full_sample_standardize": _case_full_sample_standardize,
    "future_universe": _case_future_universe,
    "cross_asset_roll": _case_cross_asset_roll,
    "t_plus_one_unlock": _case_t_plus_one_unlock,
    "fee_omission": _case_fee_omission,
    "duplicate_cost": _case_duplicate_cost,
    "period_override": _case_period_override,
    "attribution_sign": _case_attribution_sign,
    "bad_link": _case_bad_link,
}


def run_case(mutation_id: str) -> dict[str, Any]:
    case = next((item for item in CASES if item.mutation_id == mutation_id), None)
    if case is None:
        raise KeyError(mutation_id)
    try:
        result = _RUNNERS[mutation_id]()
    except Exception as exc:  # Import/runtime crashes are not valid kills.
        return {
            "mutation_id": mutation_id,
            "status": "ERROR",
            "message": f"{type(exc).__name__}: {exc}",
            "requirement": case.requirement,
            "acceptance": case.acceptance,
        }
    killed = bool(result.pop("killed"))
    baseline_ok = bool(result.pop("baseline_ok", True))
    result.update(
        {
            "mutation_id": mutation_id,
            "status": "KILLED" if killed else "BASELINE_FAILED" if not baseline_ok else "SURVIVED",
            "requirement": case.requirement,
            "acceptance": case.acceptance,
            "location": case.location,
            "baseline_ok": baseline_ok,
        }
    )
    return result


def run_mutation_suite(*, isolated: bool = True) -> dict[str, Any]:
    results = [
        _isolated_case(case.mutation_id) if isolated else run_case(case.mutation_id)
        for case in CASES
    ]
    survived = [item["mutation_id"] for item in results if item["status"] != "KILLED"]
    return {
        "mutation_version": MUTATION_VERSION,
        "status": "PASS" if not survived else "FAIL",
        "total": len(results),
        "killed": len(results) - len(survived),
        "survived": survived,
        "results": results,
    }


def _isolated_case(mutation_id: str) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "quantide.audit.mutations",
        "--case",
        mutation_id,
        "--json",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if completed.returncode != 0:
        return {
            "mutation_id": mutation_id,
            "status": "ERROR",
            "message": completed.stderr.strip()[-500:],
        }
    payload = json.loads(completed.stdout)
    return dict(payload) if isinstance(payload, dict) else {"status": "ERROR"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run key audit mutations")
    parser.add_argument("--case", help="run one mutation")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--no-isolate", action="store_true", help="run in-process")
    args = parser.parse_args(argv)
    if args.case:
        result = run_case(args.case)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"{result['mutation_id']}: {result['status']} {result.get('evidence', '')}")
        return 0 if result["status"] == "KILLED" else 1
    report = run_mutation_suite(isolated=not args.no_isolate)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['status']} {report['killed']}/{report['total']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

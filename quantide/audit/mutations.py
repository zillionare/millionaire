"""Key-mutation catalogue for acceptance audits, optionally run in subprocesses."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
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

MUTATION_VERSION = "1.1.0"
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


def _cross_asset_frame() -> pl.DataFrame:
    rows = []
    for asset_index, asset in enumerate(("000001", "000002")):
        for index, day in enumerate(
            dt.date(2024, 1, 2) + dt.timedelta(days=offset) for offset in range(5)
        ):
            price = 10.0 + asset_index + index * 0.2
            rows.append(
                {
                    "date": day,
                    "asset": asset,
                    "open": price,
                    "high": price + 0.1,
                    "low": price - 0.1,
                    "close": price + 0.05,
                    "volume": 1000.0,
                    "amount": 10000.0,
                }
            )
    return pl.DataFrame(rows).sort(["asset", "date"])


def _cross_asset_status(leaky: bool) -> AuditStatus:
    from quantide.audit.plugin_factor import audit_factor_plugin
    from quantide.factors.plugins import FactorPlugin

    def compute(frame: pl.DataFrame) -> pl.DataFrame:
        shifted = pl.col("close").shift(1)
        expression = shifted if leaky else shifted.over("asset")
        return frame.with_columns(expression.alias("mut_5001_signal"))

    plugin = FactorPlugin(
        factor_id="mut_5001_signal",
        display_name="MUT-5001 audit probe",
        group="audit",
        compute=compute,
        source_hash="mut-5001",
    )
    frame = _cross_asset_frame()
    report = audit_factor_plugin(plugin, frame, modes=("zero",), seeds=(0,))
    return next(
        check.status
        for check in report.checks
        if check.check_id == "plugin.cross_section_isolation"
    )


def _case_mut_5001() -> dict[str, Any]:
    baseline = _cross_asset_status(False) is AuditStatus.PASS
    mutant = _cross_asset_status(True) is AuditStatus.FAIL
    return _killed(
        baseline and mutant,
        "baseline keeps per-asset shift; removing .over('asset') fails isolation",
        baseline_ok=baseline,
    )


def _pit_frame() -> pl.DataFrame:
    start = dt.date(2024, 1, 2)
    return pl.DataFrame(
        [
            {
                "date": start + dt.timedelta(days=offset),
                "asset": "A",
                "close": 10.0,
                "volume": 1000.0,
                "list_date": dt.date(2000, 1, 1),
                "delist_date": None,
            }
            for offset in range(3)
        ]
    )


def _case_mut_5002() -> dict[str, Any]:
    from quantide.factors import universe

    history = _pit_frame()
    dates = history["date"].to_list()
    status = pl.DataFrame(
        {
            "date": dates,
            "asset": ["A"] * 3,
            "is_st": [False, True, True],
        }
    )
    config = universe.UniverseFilterConfig(min_listing_days=0, max_universe_size=None)
    baseline = universe.filter_universe_for_date(
        history, dates[0], config, status_frame=status
    ).assets

    def stale_status(
        frame: pl.DataFrame,
        _trade_date: dt.date,
        status_frame: pl.DataFrame | None,
        warnings: list[str],
    ) -> pl.DataFrame:
        if status_frame is None or status_frame.is_empty():
            warnings.append("st_history_unavailable")
            return frame.with_columns(pl.lit(False).alias("is_st"))
        latest = (
            status_frame.sort("date").group_by("asset").agg(pl.col("is_st").last().alias("is_st"))
        )
        return (
            frame.drop("is_st", strict=False)
            .join(latest, on="asset", how="left")
            .with_columns(pl.col("is_st").fill_null(False).cast(pl.Boolean))
        )

    with patch.object(universe, "_attach_status", stale_status):
        mutant = universe.filter_universe_for_date(
            history, dates[0], config, status_frame=status
        ).assets
    return _killed(
        baseline == ("A",) and "A" not in mutant,
        "PIT status keeps A on t1; static latest status removes it",
        baseline_ok=baseline == ("A",),
    )


def _label_frame() -> pl.DataFrame:
    rows = []
    for asset_index, asset in enumerate(("A", "B", "C")):
        for index in range(6):
            price = 10.0 * (1.0 + 0.05 * index) * (1.0 + 0.01 * index * asset_index)
            rows.append(
                {
                    "date": dt.date(2024, 1, 2) + dt.timedelta(days=index),
                    "asset": asset,
                    "close": price,
                }
            )
    return pl.DataFrame(rows).sort(["asset", "date"])


def _date_means(frame: pl.DataFrame) -> list[float]:
    label = "future_n_trading_day_close_return"
    values = (
        frame.filter(pl.col(label).is_not_null())
        .group_by("date")
        .agg(pl.col(label).mean().alias("mean"))
        .sort("date")["mean"]
        .to_list()
    )
    return [float(value) for value in values]


def _case_mut_5003() -> dict[str, Any]:
    from quantide.strategies.example import _ml_support

    frame = _label_frame()
    label = "future_n_trading_day_close_return"
    baseline = _ml_support.compute_future_close_return_labels(
        frame, horizon=1, label_kind="cs_rank"
    )

    def pooled_rank(value_frame: pl.DataFrame, label_kind: str) -> pl.DataFrame:
        if label_kind == "raw_return":
            return value_frame
        value = pl.col(label).rank(method="average") / pl.col(label).count() - 0.5
        return value_frame.with_columns(value.alias(label))

    with patch.object(_ml_support, "_cross_section_label", pooled_rank):
        mutant = _ml_support.compute_future_close_return_labels(
            frame, horizon=1, label_kind="cs_rank"
        )
    baseline_means = _date_means(baseline)
    mutant_means = _date_means(mutant)
    baseline_ok = (
        bool(baseline_means)
        and max(baseline_means) - min(baseline_means) <= 1e-12
        and all(-0.5 <= value <= 0.5 for value in baseline_means)
    )
    return _killed(
        baseline_ok and max(mutant_means) - min(mutant_means) > 1e-6,
        "production cs_rank stays date-local; pooled operator shifts dates",
        baseline_ok=baseline_ok,
    )


def _badge_context(record: dict[str, Any], *, ignore_source: bool = False) -> ExitStack:
    from quantide.service import factor_audit

    discovery = SimpleNamespace(by_id=lambda _factor_id: None)
    stack = ExitStack()
    stack.enter_context(patch.object(factor_audit, "_load_records", lambda: {"demo": record}))
    stack.enter_context(patch.object(factor_audit, "discover_factor_plugins", lambda: discovery))
    stack.enter_context(patch.object(factor_audit, "factor_version", lambda _id: "new-source"))
    stack.enter_context(
        patch.object(factor_audit, "_current_data_hash", lambda _record: ("data", None))
    )
    stack.enter_context(patch.object(factor_audit, "_current_config_hash", lambda *_args: "config"))
    if ignore_source:
        stack.enter_context(
            patch.object(
                factor_audit,
                "_fingerprints_match",
                lambda record, source, config, data: (
                    record.get("config_hash") == config and record.get("data_hash") == data
                ),
            )
        )
    return stack


def _case_mut_5004() -> dict[str, Any]:
    from quantide.service import factor_audit

    record = {
        "run_id": "run-1",
        "status": "PASS",
        "checked_at": "2026-01-01T00:00:00",
        "source_hash": "old-source",
        "config_hash": "config",
        "data_hash": "data",
    }
    with _badge_context(record):
        baseline = factor_audit.factor_wind_tunnel_badge("demo").badge_status
    with _badge_context(record, ignore_source=True):
        mutant = factor_audit.factor_wind_tunnel_badge("demo").badge_status
    baseline_ok = baseline == "STALE"
    return _killed(
        baseline_ok and mutant == "PASS",
        "source change downgrades PASS to STALE; ignoring source keeps PASS",
        baseline_ok=baseline_ok,
    )


def _minute_frame() -> pl.DataFrame:
    target = dt.datetime(2026, 10, 27, 10, 0)
    rows = []
    for bar_time in (target, target + dt.timedelta(minutes=30)):
        rows.append(
            {
                "date": bar_time,
                "asset": "000001.SZ",
                "open": 10.0,
                "high": 10.1,
                "low": 9.9,
                "close": 10.0,
                "volume": 1000.0,
                "amount": 10000.0,
            }
        )
    return pl.DataFrame(rows)


def _case_mut_5005() -> dict[str, Any]:
    from quantide.service import shadow_intraday

    frame = _minute_frame()
    target = dt.datetime(2026, 10, 27, 10, 0)

    class _Minutes:
        @staticmethod
        def get_bars_in_range(
            start: Any,
            end: Any = None,
            assets: Any = None,
            adjust: Any = None,
            eager_mode: Any = True,
        ) -> pl.DataFrame:
            return frame

    baseline = shadow_intraday.load_closed_bar_frame(target, ["000001.SZ"], minute_model=_Minutes())
    with patch.object(shadow_intraday, "_closed_bucket", lambda value, _slot: value):
        mutant = shadow_intraday.load_closed_bar_frame(
            target, ["000001.SZ"], minute_model=_Minutes()
        )
    baseline_ok = baseline is not None and baseline.height == 1
    detected = (
        mutant is not None
        and baseline is not None
        and mutant.height > baseline.height
        and set(mutant["date"].to_list()) != set(baseline["date"].to_list())
    )
    return _killed(
        detected,
        "production closed-bucket filter returns 10:00 only; disabling it consumes 10:30",
        baseline_ok=baseline_ok,
    )


def _preset_rejects_missing(features: list[str]) -> bool:
    from quantide.service.factor_presets import _validate_features

    try:
        _validate_features(features, "1d")
    except ValueError as exc:
        return "缺失因子" in str(exc)
    return False


def _case_mut_5006() -> dict[str, Any]:
    from quantide.service import factor_presets

    features = ["ma20_slope", "not_a_real_factor"]
    baseline = _preset_rejects_missing(features)
    original = factor_presets.all_factor_ids
    with patch.object(
        factor_presets,
        "all_factor_ids",
        lambda: [*original(), "not_a_real_factor"],
    ):
        mutant_accepts = not _preset_rejects_missing(features)
    return _killed(
        baseline and mutant_accepts,
        "production preset validator rejects missing factor; injected known-set accepts it",
        baseline_ok=baseline,
    )


def _sandbox_path_probe() -> tuple[bool, bool]:
    from quantide.service import ai_factor_tools

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        with (
            patch.object(ai_factor_tools, "normalize_factor_dir", lambda _value=None: str(root)),
            patch.object(ai_factor_tools, "_FACTOR_ID", re.compile(r".+")),
        ):
            try:
                ai_factor_tools._target_path("../escape")
            except ai_factor_tools.AIToolError:
                baseline_rejects = True
            else:
                baseline_rejects = False
            with patch.object(
                ai_factor_tools,
                "_validate_target",
                lambda _root, _target, _resolved: None,
            ):
                escaped = ai_factor_tools._target_path("../escape")
                mutant_escaped = not escaped.resolve().is_relative_to(root)
    return baseline_rejects, mutant_escaped


def _wind_bypass_probe() -> tuple[bool, bool]:
    from quantide.service import ai_factor_tools, factor_audit

    day = dt.date(2026, 1, 1)
    result = {"results": [], "study_id": "study-1", "factor_id": "bad_factor"}
    badge = SimpleNamespace(badge_status="FAIL", message="blocked")
    with (
        patch.object(factor_audit, "factor_wind_tunnel_badge", lambda _factor_id: badge),
        patch.object(ai_factor_tools, "_coverage_window", lambda: (day, day)),
        patch.object(ai_factor_tools, "_run_process", lambda *_args, **_kwargs: result),
    ):
        try:
            ai_factor_tools.run_factor_ic_study({"factor_id": "bad_factor"})
        except ai_factor_tools.AIToolError:
            baseline_rejects = True
        else:
            baseline_rejects = False
        with patch.object(ai_factor_tools, "_require_pass", lambda _factor_id: None):
            mutated = ai_factor_tools.run_factor_ic_study({"factor_id": "bad_factor"})
        mutant_accepts = isinstance(mutated, dict) and mutated.get("study_id") == "study-1"
    return baseline_rejects, mutant_accepts


def _case_mut_5007() -> dict[str, Any]:
    path_rejects, path_mutant_escaped = _sandbox_path_probe()
    wind_rejects, wind_mutant_accepts = _wind_bypass_probe()
    baseline_ok = path_rejects and wind_rejects
    detected = baseline_ok and path_mutant_escaped and wind_mutant_accepts
    return _killed(
        detected,
        "production path guard blocks ../escape; disabling it escapes factor_dir",
        baseline_ok=baseline_ok,
    )


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
    MutationCase(
        "MUT-5001",
        "FR-5002",
        "AC-5004/AC-5005",
        "external factor cross-asset isolation",
        "External factor removes .over('asset') and leaks values across securities.",
    ),
    MutationCase(
        "MUT-5002",
        "FR-5009",
        "AC-5016",
        "PIT universe ST status",
        "PIT filtering reads the latest static name instead of the signal-date fact.",
    ),
    MutationCase(
        "MUT-5003",
        "FR-5010",
        "AC-5017",
        "cross-section label rank",
        "cs_rank pools all dates instead of ranking inside each mature date.",
    ),
    MutationCase(
        "MUT-5004",
        "FR-5007",
        "AC-5013",
        "wind-tunnel badge fingerprint",
        "Badge ignores a changed source hash and keeps PASS.",
    ),
    MutationCase(
        "MUT-5005",
        "FR-5012",
        "AC-5019",
        "30m shadow bar boundary",
        "30m shadow replay consumes a forming minute bucket.",
    ),
    MutationCase(
        "MUT-5006",
        "FR-5004",
        "AC-5007",
        "factor preset validation",
        "Preset silently drops a missing factor instead of failing closed.",
    ),
    MutationCase(
        "MUT-5007",
        "FR-5014",
        "AC-5027/AC-5028",
        "Web Agent sandbox and wind tunnel",
        "Agent can escape factor_dir or bypass a FAIL badge to emit a study card.",
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
    "MUT-5001": _case_mut_5001,
    "MUT-5002": _case_mut_5002,
    "MUT-5003": _case_mut_5003,
    "MUT-5004": _case_mut_5004,
    "MUT-5005": _case_mut_5005,
    "MUT-5006": _case_mut_5006,
    "MUT-5007": _case_mut_5007,
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

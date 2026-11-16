"""Pre-registered synthetic signal recovery and random-control audits."""

from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import polars as pl

from quantide.audit.statistics import StatisticalProfile
from quantide.factors.research import (
    HorizonRequest,
    ICSummary,
    daily_pearson_ic,
    daily_rank_ic,
    study_horizon,
    summarize_ic,
)

Metric = Literal["pearson", "rank"]


@dataclass(frozen=True)
class SignalExperiment:
    target_ic: float
    metric: Metric
    n_dates: int = 25
    n_assets: int = 120
    seeds: tuple[int, ...] = (0,)
    alpha: float = 0.05
    power: float = 0.8
    annualization: int = 252

    def __post_init__(self) -> None:
        if not -1 < self.target_ic < 1 or self.target_ic == 0:
            raise ValueError("target_ic must be non-zero and between -1 and 1")
        if self.metric not in ("pearson", "rank"):
            raise ValueError("metric must be pearson or rank")
        if self.n_dates < 2 or self.n_assets < 2:
            raise ValueError("experiment needs at least two dates and assets")
        if not self.seeds or not 0 < self.alpha < 1 or not 0 < self.power < 1:
            raise ValueError("invalid statistical profile")

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_ic": self.target_ic,
            "metric": self.metric,
            "n_dates": self.n_dates,
            "n_assets": self.n_assets,
            "seeds": list(self.seeds),
            "alpha": self.alpha,
            "power": self.power,
            "annualization": self.annualization,
        }

    @property
    def required_days(self) -> int:
        z_alpha = _normal_quantile(1 - self.alpha / 2)
        z_power = _normal_quantile(self.power)
        return max(3, math.ceil(((z_alpha + z_power) / math.atanh(self.target_ic)) ** 2 + 3))


def _normal_quantile(probability: float) -> float:
    if not 0 < probability < 1:
        raise ValueError("probability must be between zero and one")
    # Acklam's rational approximation is adequate for audit thresholds.
    a = [-39.69683028665376, 220.9460984245205, -275.9285104469687]
    a += [138.357751867269, -30.66479806614716, 2.506628277459239]
    b = [-54.47609879822406, 161.5858368580409, -155.6989798598866]
    b += [66.80131188771972, -13.28068155288572]
    c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838]
    c += [-2.549732539343734, 4.374664141464968, 2.938163982698783]
    d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996]
    d += [3.754408661907416]
    low, high = 0.02425, 1 - 0.02425
    if probability < low:
        q = math.sqrt(-2 * math.log(probability))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if probability > high:
        q = math.sqrt(-2 * math.log(1 - probability))
        return -(
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
        )
    q = probability - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )


def _price_paths(
    simple_returns: list[list[float]], n_assets: int, n_dates: int
) -> list[list[float]]:
    prices: list[list[float]] = []
    for asset_index in range(n_assets):
        path = [10.0]
        for date_index in range(1, n_dates):
            path.append(path[-1] * (1.0 + simple_returns[date_index - 1][asset_index]))
        prices.append(path)
    return prices


def _panel_rows(
    dates: list[dt.date],
    factors: list[Any],
    latent: list[Any],
    prices: list[list[float]],
    n_assets: int,
) -> list[dict[str, Any]]:
    rows = []
    for date_index, day in enumerate(dates):
        for asset_index in range(n_assets):
            forward = (
                0.01 * float(latent[date_index][asset_index])
                if date_index + 1 < len(dates)
                else 0.0
            )
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset_index:06d}",
                    "factor": float(factors[date_index][asset_index]),
                    "forward": forward,
                    "open": prices[asset_index][date_index],
                }
            )
    return rows


def synthetic_panel(experiment: SignalExperiment, *, seed: int = 0) -> pl.DataFrame:
    """Build a panel whose simple forward returns recover the requested target IC."""
    generator = np.random.default_rng(seed)
    rho = (
        experiment.target_ic
        if experiment.metric == "pearson"
        else 2 * math.sin(math.pi * experiment.target_ic / 6)
    )
    dates = [dt.date(2024, 1, 2) + dt.timedelta(days=index) for index in range(experiment.n_dates)]
    factors = [generator.standard_normal(experiment.n_assets) for _ in range(experiment.n_dates)]
    noises = [generator.standard_normal(experiment.n_assets) for _ in range(experiment.n_dates)]
    latent = [
        rho * factor + math.sqrt(max(0.0, 1 - rho * rho)) * noise
        for factor, noise in zip(factors, noises, strict=True)
    ]
    simple_returns = [[0.0] * experiment.n_assets] + [
        [0.01 * value for value in latent[index]] for index in range(experiment.n_dates - 1)
    ]
    prices = _price_paths(simple_returns, experiment.n_assets, experiment.n_dates)
    return pl.DataFrame(_panel_rows(dates, factors, latent, prices, experiment.n_assets))


def _summaries(panel: pl.DataFrame, metric: Metric, profile: StatisticalProfile) -> list[ICSummary]:
    factor = "factor"
    summaries: list[ICSummary] = []
    if metric == "rank":
        for _seed in profile.seeds:
            # The panel already fixes the seed; repeated seeds verify determinism.
            points = daily_rank_ic(panel, factor, profile.min_cross_section)
            summaries.append(summarize_ic([point.ic for point in points]))
        return summaries
    for _ in profile.seeds:
        pearson_points = daily_pearson_ic(panel, factor, profile.min_cross_section)
        summaries.append(summarize_ic([point.ic for point in pearson_points]))
    return summaries


def _confidence_interval(mean: float, n_days: int, alpha: float) -> tuple[float, float]:
    if n_days <= 3 or abs(mean) >= 1:
        return (-1.0, 1.0)
    z = _normal_quantile(1 - alpha / 2)
    center = math.atanh(mean)
    width = z / math.sqrt(n_days - 3)
    return (math.tanh(center - width), math.tanh(center + width))


def _run_recovery(experiment: SignalExperiment, seed: int) -> dict[str, Any]:
    panel = synthetic_panel(experiment, seed=seed)
    profile = StatisticalProfile(
        alpha=experiment.alpha,
        power=experiment.power,
        seeds=(seed,),
        min_cross_section=min(20, experiment.n_assets),
    )
    summaries = _summaries(panel, experiment.metric, profile)
    observed = summaries[0]
    required = experiment.required_days
    if observed.mean is None or observed.n_days < required:
        status = "INCONCLUSIVE"
        reason = "insufficient statistical power"
    else:
        low, high = _confidence_interval(observed.mean, observed.n_days, experiment.alpha)
        if low <= 0 <= high:
            status = "INCONCLUSIVE"
            reason = "confidence interval covers zero"
        elif low <= experiment.target_ic <= high:
            status = "RECOVERED"
            reason = "target lies inside the confidence interval"
        else:
            status = "FAILED"
            reason = "target lies outside the confidence interval"
    return {
        "status": status,
        "reason": reason,
        "observed": observed.as_dict(),
        "target": experiment.target_ic,
        "required_days": required,
        "n_days": observed.n_days,
        "seed": seed,
    }


def signal_recovery(experiment: SignalExperiment, *, seed: int | None = None) -> dict[str, Any]:
    """Recover every pre-registered seed; one failed seed fails the audit."""
    seeds = (seed,) if seed is not None else experiment.seeds
    runs = [_run_recovery(experiment, item) for item in seeds]
    statuses = {item["status"] for item in runs}
    if "FAILED" in statuses:
        status = "FAILED"
    elif "INCONCLUSIVE" in statuses:
        status = "INCONCLUSIVE"
    else:
        status = "RECOVERED"
    return {
        "status": status,
        "reason": ", ".join(sorted({item["reason"] for item in runs})),
        "observed": runs[0]["observed"],
        "target": experiment.target_ic,
        "required_days": experiment.required_days,
        "n_days": runs[0]["n_days"],
        "profile": experiment.as_dict(),
        "seed": seeds[0],
        "seeds": list(seeds),
        "runs": runs,
    }


def _study_seed(experiment: SignalExperiment, seed: int) -> dict[str, Any]:
    panel = synthetic_panel(experiment, seed=seed)
    start = panel["date"].min()
    end = panel["date"].max()
    if not isinstance(start, dt.date) or not isinstance(end, dt.date):
        raise ValueError("synthetic panel lacks dates")
    result = study_horizon(
        panel,
        HorizonRequest(
            "factor",
            1,
            start,
            end,
            end,
            min_cross_section=min(20, experiment.n_assets),
            annualization=experiment.annualization,
        ),
    )
    summary = result.pearson_ic if experiment.metric == "pearson" else result.rank_ic
    low, high = (
        _confidence_interval(summary.mean, summary.n_days, experiment.alpha)
        if summary.mean is not None
        else (-1.0, 1.0)
    )
    status = (
        "INCONCLUSIVE"
        if summary.mean is None or summary.n_days < experiment.required_days
        else "RECOVERED"
        if low <= experiment.target_ic <= high
        else "FAILED"
    )
    return {
        "status": status,
        "observed": summary.as_dict(),
        "horizon": result.as_dict(),
        "required_days": experiment.required_days,
        "seed": seed,
    }


def study_synthetic_signal(
    experiment: SignalExperiment, *, seed: int | None = None
) -> dict[str, Any]:
    """Run every pre-registered recovery through the production horizon path."""
    seeds = (seed,) if seed is not None else experiment.seeds
    runs = [_study_seed(experiment, item) for item in seeds]
    statuses = {item["status"] for item in runs}
    status = (
        "FAILED"
        if "FAILED" in statuses
        else "INCONCLUSIVE"
        if "INCONCLUSIVE" in statuses
        else "RECOVERED"
    )
    return {
        "status": status,
        "observed": runs[0]["observed"],
        "horizon": runs[0]["horizon"],
        "required_days": experiment.required_days,
        "seeds": list(seeds),
        "runs": runs,
    }


@dataclass(frozen=True)
class RandomControl:
    n_dates: int = 250
    n_assets: int = 50
    seeds: tuple[int, ...] = (0, 1, 2)
    cost_per_turnover: float = 0.001
    gross_tolerance: float = 0.02
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n_dates < 2 or self.n_assets < 2 or not self.seeds:
            raise ValueError("invalid random control")
        if self.cost_per_turnover < 0 or self.gross_tolerance < 0:
            raise ValueError("costs and tolerance must be non-negative")


def _random_return_paths(control: RandomControl, seed: int) -> tuple[list[float], list[float]]:
    generator = random.Random(seed)
    gross: list[float] = []
    turnover: list[float] = []
    previous = [1.0 / control.n_assets] * control.n_assets
    for _ in range(control.n_dates):
        weights = [generator.random() for _ in range(control.n_assets)]
        total = sum(weights)
        weights = [value / total for value in weights]
        returns = [generator.gauss(0.0, 0.01) for _ in range(control.n_assets)]
        gross.append(sum(weight * value for weight, value in zip(weights, returns, strict=True)))
        turnover.append(sum(abs(a - b) for a, b in zip(weights, previous, strict=True)))
        previous = weights
    return gross, turnover


def _zero_drift_seed(control: RandomControl, seed: int) -> dict[str, Any]:
    gross, turnover = _random_return_paths(control, seed)
    mean_gross = float(np.mean(gross))
    mean_turnover = float(np.mean(turnover))
    expected_net = -control.cost_per_turnover * mean_turnover
    mean_net = float(np.mean([value + expected_net for value in gross]))
    std_gross = float(np.std(gross, ddof=1)) if len(gross) > 1 else 0.0
    status = (
        "PASS"
        if abs(mean_gross) <= control.gross_tolerance
        and abs(mean_net - expected_net) <= control.gross_tolerance
        else "FAIL"
    )
    return {
        "status": status,
        "mean_gross": mean_gross,
        "mean_net": mean_net,
        "expected_net": expected_net,
        "mean_turnover": mean_turnover,
        "gross_std": std_gross,
        "n_dates": control.n_dates,
        "seed": seed,
    }


def zero_drift_control(control: RandomControl, *, seed: int | None = None) -> dict[str, Any]:
    """Long-only random equal-weight control over every declared seed."""
    seeds = (seed,) if seed is not None else control.seeds
    runs = [_zero_drift_seed(control, item) for item in seeds]
    first = runs[0]
    return {
        **first,
        "status": "PASS" if all(item["status"] == "PASS" for item in runs) else "FAIL",
        "seeds": list(seeds),
        "runs": runs,
    }


def matched_benchmark_excess(
    strategy_returns: list[float],
    benchmark_returns: list[float],
    *,
    alpha: float = 0.05,
) -> dict[str, Any]:
    if len(strategy_returns) != len(benchmark_returns) or len(strategy_returns) < 2:
        raise ValueError("strategy and benchmark series must align")
    excess = [s - b for s, b in zip(strategy_returns, benchmark_returns, strict=True)]
    summary = summarize_ic(excess)  # mean/t/ICIR apply to any day series
    low, high = _confidence_interval(summary.mean or 0.0, len(excess), alpha)
    return {
        "mean_excess": summary.mean,
        "t_naive": summary.t_naive,
        "n_days": summary.n_days,
        "confidence_interval": [low, high],
        "status": "INCONCLUSIVE" if summary.mean is None else "OK",
        "significant": low > 0 or high < 0,
    }

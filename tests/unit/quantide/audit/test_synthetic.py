"""Synthetic signal recovery and random-control tests."""

from __future__ import annotations

import pytest

from quantide.audit.synthetic import (
    RandomControl,
    SignalExperiment,
    matched_benchmark_excess,
    signal_recovery,
    study_synthetic_signal,
    zero_drift_control,
)


@pytest.mark.parametrize("target", [0.25, -0.25])
def test_pearson_power_recovers_positive_and_negative_signals(target) -> None:
    experiment = SignalExperiment(
        target_ic=target,
        metric="pearson",
        n_dates=190,
        n_assets=120,
        seeds=(3,),
    )
    result = signal_recovery(experiment)
    assert result["status"] == "RECOVERED", result
    assert result["observed"]["mean"] == pytest.approx(target, abs=0.08)
    assert result["observed"]["icir"] is not None


def test_rank_signal_is_recovered_with_rank_metric() -> None:
    experiment = SignalExperiment(
        target_ic=0.25,
        metric="rank",
        n_dates=190,
        n_assets=120,
        seeds=(5,),
    )
    result = signal_recovery(experiment)
    assert result["status"] == "RECOVERED", result


def test_insufficient_sample_is_inconclusive_not_pass() -> None:
    experiment = SignalExperiment(
        target_ic=0.05,
        metric="pearson",
        n_dates=25,
        n_assets=120,
        seeds=(0,),
    )
    result = signal_recovery(experiment)
    assert result["status"] == "INCONCLUSIVE"
    assert result["required_days"] > experiment.n_dates


def test_production_horizon_path_recovers_synthetic_signal() -> None:
    experiment = SignalExperiment(
        target_ic=0.3,
        metric="pearson",
        n_dates=150,
        n_assets=120,
    )
    result = study_synthetic_signal(experiment)
    assert result["status"] == "RECOVERED"
    assert result["horizon"]["pearson_ic"]["n_days"] > 0


def test_zero_drift_random_control_is_gross_zero_and_net_negative_cost() -> None:
    result = zero_drift_control(RandomControl(n_dates=120, n_assets=30, seed=7))
    assert result["status"] == "PASS"
    assert abs(result["mean_gross"]) < 0.02
    assert result["mean_net"] < 0
    assert result["mean_net"] == pytest.approx(result["expected_net"], abs=0.02)


def test_matched_benchmark_excess_is_computed_separately() -> None:
    strategy = [0.01, 0.02, -0.01, 0.0]
    benchmark = [0.005, 0.01, -0.005, 0.0]
    result = matched_benchmark_excess(strategy, benchmark)
    assert result["mean_excess"] == pytest.approx(0.0025)
    assert result["n_days"] == 4


def test_every_declared_seed_is_executed_for_signal_and_control() -> None:
    experiment = SignalExperiment(
        target_ic=0.25,
        metric="pearson",
        n_dates=190,
        n_assets=120,
        seeds=(3, 999),
    )
    result = signal_recovery(experiment)
    assert result["status"] == "RECOVERED", result
    assert result["seeds"] == [3, 999]
    assert [run["seed"] for run in result["runs"]] == [3, 999]
    production = study_synthetic_signal(experiment)
    assert production["status"] == "RECOVERED", production
    assert [run["seed"] for run in production["runs"]] == [3, 999]

    control = zero_drift_control(RandomControl(n_dates=80, n_assets=20, seeds=(2, 7)))
    assert control["status"] == "PASS"
    assert [run["seed"] for run in control["runs"]] == [2, 7]

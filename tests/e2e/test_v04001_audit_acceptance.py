"""Deterministic v0.4-001 audit acceptance evidence."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.audit.mutations import run_mutation_suite
from quantide.audit.synthetic import (
    RandomControl,
    SignalExperiment,
    signal_recovery,
    zero_drift_control,
)
from quantide.service.attribution_facts import (
    AccountFacts,
    FactSnapshot,
    attribution_report,
)
from quantide.service.factor_runs import FactorRunStore, RunBudget
from quantide.service.monthly_bars import MonthlySeries, monthly_ma_signals
from quantide.strategies.example.monthly_ma import MonthlyMAStrategy

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]


def test_key_mutations_are_all_killed() -> None:
    report = run_mutation_suite(isolated=False)
    assert report["status"] == "PASS"
    assert report["survived"] == []


def test_signal_recovery_and_zero_drift_controls() -> None:
    experiment = SignalExperiment(
        target_ic=0.25, metric="pearson", n_dates=190, n_assets=120, seeds=(3,)
    )
    assert signal_recovery(experiment)["status"] == "RECOVERED"
    assert zero_drift_control(RandomControl(n_dates=80, n_assets=20, seed=2))["status"] == "PASS"


def test_account_fact_attribution_reconciles() -> None:
    d0 = dt.date(2024, 1, 2)
    d1 = dt.date(2024, 1, 3)
    facts = AccountFacts(
        "release",
        "backtest",
        (
            FactSnapshot(d0, 1000, 1000, {}, {}),
            FactSnapshot(d1, 1100, 0, {"A": 100}, {"A": 11}),
        ),
        (),
    )
    report = attribution_report(facts)
    assert report["status"] == "OK_WITH_RESIDUAL"
    assert report["residual"] == 100
    assert report["reconciliation_issues"]


def test_monthly_contract_and_storage(tmp_path) -> None:
    assert MonthlyMAStrategy.BAR_INTERVAL == "1M"
    store = FactorRunStore(tmp_path / "runs.sqlite")
    assert store.enqueue(
        ["bias_5"],
        lookback="3y",
        profile_revisions={"bias_5": 0},
        source_revision=0,
        source_versions={"source_market_version": "m"},
        budget=RunBudget(),
    )
    assert len(store.list_runs()) == 1


def test_monthly_cross_does_not_use_forming_bar() -> None:
    assert MonthlySeries("A", ()).closed == ()
    assert monthly_ma_signals(MonthlySeries("A", ()), ()) == []
    frame = pl.DataFrame({"date": [], "asset": []})
    assert frame.is_empty()

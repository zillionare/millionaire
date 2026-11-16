"""Random-control and permutation statistics tests."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.audit.statistics import (
    StatisticalProfile,
    empirical_p_value,
    null_rank_ic_distribution,
    permute_within_date,
    random_factor,
    rank_ic_summary,
    summarize_null_distribution,
)


def _panel() -> pl.DataFrame:
    dates = [dt.date(2024, 1, day) for day in range(1, 6)]
    rows = []
    for asset in range(120):
        for index, day in enumerate(dates):
            forward = asset / 120 + index * 0.001
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "factor": forward,
                    "forward": forward,
                }
            )
    return pl.DataFrame(rows)


def test_statistical_profile_is_validated_and_fingerprinted() -> None:
    profile = StatisticalProfile(seeds=(1, 2), permutations=10)
    assert profile.fingerprint == StatisticalProfile(seeds=(1, 2), permutations=10).fingerprint
    assert profile.fingerprint != StatisticalProfile(seeds=(1, 3), permutations=10).fingerprint
    with pytest.raises(ValueError):
        StatisticalProfile(alpha=1.0)
    with pytest.raises(ValueError):
        StatisticalProfile(seeds=())


def test_permutation_preserves_each_date_bucket() -> None:
    panel = _panel()
    permuted = permute_within_date(panel, "factor", seed=7)
    for day in panel["date"].unique().to_list():
        original = sorted(panel.filter(pl.col("date") == day)["factor"].to_list())
        changed = sorted(permuted.filter(pl.col("date") == day)["factor_permuted"].to_list())
        assert original == changed
    assert permuted["factor_permuted"].to_list() != panel["factor"].to_list()


def test_random_factor_is_deterministic_and_rank_ic_is_positive_for_signal() -> None:
    panel = _panel()
    first = random_factor(panel, seed=3)
    second = random_factor(panel, seed=3)
    assert first["random_factor"].to_list() == second["random_factor"].to_list()
    summary = rank_ic_summary(panel, "factor")
    assert summary.mean == pytest.approx(1.0)
    assert summary.n_days == 5


def test_null_distribution_and_p_value_are_reproducible() -> None:
    panel = _panel()
    profile = StatisticalProfile(seeds=(1, 2), permutations=10, min_cross_section=10)
    nulls = null_rank_ic_distribution(panel, "factor", profile)
    observed = rank_ic_summary(panel, "factor")
    result = summarize_null_distribution(observed, nulls, profile)
    assert len(nulls) == 20
    assert result["status"] == "OK"
    assert result["null_count"] == 20
    assert result["expected_count"] == 20
    assert result["p_value"] <= 1
    assert empirical_p_value(0.5, [0.0, 0.1]) == pytest.approx(1 / 3)
    assert empirical_p_value(0.05, [0.0, 0.1]) == pytest.approx(2 / 3)


def test_null_distribution_requires_declared_sample_count() -> None:
    panel = _panel()
    profile = StatisticalProfile(seeds=(1, 2), permutations=10, min_cross_section=10)
    observed = rank_ic_summary(panel, "factor")
    nulls = null_rank_ic_distribution(panel, "factor", profile)[:3]
    result = summarize_null_distribution(observed, nulls, profile)
    assert result["status"] == "INCONCLUSIVE"
    assert result["reason"] == "insufficient null samples"


def test_rank_ic_summary_honours_custom_forward_column() -> None:
    panel = _panel().rename({"forward": "ret"})
    summary = rank_ic_summary(panel, "factor", forward_col="ret")
    assert summary.mean == pytest.approx(1.0)
    assert summary.n_days == 5

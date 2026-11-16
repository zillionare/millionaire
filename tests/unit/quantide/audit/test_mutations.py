"""Mutation catalogue and isolated-run tests."""

from __future__ import annotations

from unittest.mock import patch

from quantide.audit.mutations import CASES, run_case, run_mutation_suite
from quantide.service.paper_matching import PaperMatching


def test_every_key_mutation_is_killed_in_process() -> None:
    report = run_mutation_suite(isolated=False)
    assert report["status"] == "PASS", report
    assert report["killed"] == len(CASES)
    assert {item["acceptance"] for item in report["results"]} >= {
        "AC-4002",
        "AC-4003",
        "AC-4008",
        "AC-4010",
        "AC-4011",
    }


def test_single_case_runs_in_isolated_subprocess() -> None:
    result = run_mutation_suite(isolated=True)
    assert result["status"] == "PASS", result
    assert result["survived"] == []


def test_unknown_mutation_is_rejected() -> None:
    try:
        run_case("does-not-exist")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown mutation should raise KeyError")


def test_wrong_production_fee_fails_the_frozen_baseline() -> None:
    with patch.object(PaperMatching, "_calculate_fee", return_value=123.0):
        result = run_case("fee_omission")
    assert result["status"] == "BASELINE_FAILED"
    assert result["baseline_ok"] is False

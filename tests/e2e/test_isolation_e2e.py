"""Offline E2E journey for deterministic execution in two distinct orders."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


TARGET_DIR = Path("tests/unit/quantide/core/domain")


def _collect_node_ids() -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(TARGET_DIR),
            "--collect-only",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    node_ids = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    assert len(node_ids) >= 2
    return node_ids


def _run(node_ids: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *node_ids,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _passed(output: str) -> int:
    match = re.search(r"(\d+)\s+passed", output)
    assert match is not None, output
    return int(match.group(1))


def test_two_distinct_explicit_orders_have_identical_green_totals() -> None:
    """AC-NFR1201-02: forward and reverse node order both finish green with equal totals."""
    node_ids = sorted(_collect_node_ids())
    reverse_ids = list(reversed(node_ids))
    assert node_ids != reverse_ids

    forward = _run(node_ids)
    reverse = _run(reverse_ids)

    assert forward.returncode == 0, forward.stdout + forward.stderr
    assert reverse.returncode == 0, reverse.stdout + reverse.stderr
    assert _passed(forward.stdout) == _passed(reverse.stdout) == len(node_ids)


def test_grid_search_worker_lines_are_merged_into_same_run_coverage(
    tmp_path: Path,
) -> None:
    """AC-NFR1201-03: real ProcessPool worker lines appear in pytest-cov JSON."""
    report = tmp_path / "grid-search-coverage.json"
    environment = os.environ.copy()
    environment["COVERAGE_PROCESS_START"] = "pyproject.toml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/quantide/service/test_grid_search.py",
            "--cov=quantide",
            f"--cov-report=json:{report}",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    coverage = json.loads(report.read_text(encoding="utf-8"))
    executed = set(
        coverage["files"]["quantide/service/grid_search.py"]["executed_lines"]
    )
    assert {31, 35, 41, 43, 56, 86}.issubset(executed)

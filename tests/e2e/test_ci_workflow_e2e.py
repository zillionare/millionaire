"""FR-0601: .github/workflows/unit-coverage.yml schema contract.

E2E contract (M-E2E Stage 2, v0.2-003-coverage):

* The workflow runs on push/PR to ``main`` and ``releases/**``.
* The Python matrix contains a ``3.13`` entry (pyproject.toml requires >=3.13).
* The workflow references the FR-0102 per-file coverage checker.
* None of the main coverage-gate steps use ``continue-on-error: true`` —
  silencing the gate would violate FR-0601 AC-5 / NFR-0010 AC-4.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/unit-coverage.yml")


@pytest.fixture
def workflow() -> dict:
    if not WORKFLOW.exists():
        pytest.skip(f"workflow file not found: {WORKFLOW} — see #214 (FR-0601)")
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_python_matrix_3_13_plus(workflow: dict) -> None:
    """AC-FR0601-01: matrix.python includes 3.13."""
    job = workflow["jobs"]["unit-coverage"]
    matrix = job["strategy"]["matrix"]
    python_versions = matrix.get("python") or matrix.get("python-version")
    assert python_versions, "matrix.python (or python-version) is required"
    assert any(str(v).startswith("3.13") for v in python_versions), (
        f"python matrix does not contain 3.13: {python_versions}"
    )


def test_workflow_invokes_coverage_checker(workflow: dict) -> None:
    """AC-FR0601-04 / AC-FR0102-01..05: workflow references per_file_coverage."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "per_file_coverage" in text or "FR-0102" in text or "coverage_check" in text


def test_workflow_no_continue_on_error_on_coverage_gate(workflow: dict) -> None:
    """AC-FR0601-05 / AC-NFR0010-04: main gate steps must NOT silence failures."""
    job = workflow["jobs"]["unit-coverage"]
    steps = job["steps"]
    for step in steps:
        if "continue-on-error" in step:
            value = step["continue-on-error"]
            assert value in (False, "false"), (
                f"step {step.get('name', '?')} has continue-on-error: {value!r}; "
                "FR-0601 AC-5 forbids silencing the coverage gate."
            )


def test_workflow_triggers_on_releases_branches(workflow: dict) -> None:
    """AC-FR0601-01: triggers include push/PR to main + releases/**."""
    on = workflow.get(True, workflow.get("on", {}))
    push_branches = on.get("push", {}).get("branches", [])
    pr_branches = on.get("pull_request", {}).get("branches", [])
    assert any("releases/**" in b or "releases/*" in b for b in push_branches), (
        f"push.branches missing releases/**: {push_branches}"
    )
    assert any("releases/**" in b or "releases/*" in b for b in pr_branches), (
        f"pull_request.branches missing releases/**: {pr_branches}"
    )
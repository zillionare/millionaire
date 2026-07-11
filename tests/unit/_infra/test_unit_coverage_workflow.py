"""FR-0601 CI coverage-gate workflow contract tests.

AC-FR-0601-1 through AC-FR-0601-5 require a Python 3.13 coverage workflow
that runs both coverage gates without allowing either to fail silently.
"""

from pathlib import Path
from typing import Any

import yaml


WORKFLOW_PATH = Path(".github/workflows/unit-coverage.yml")
CANONICAL_COMMAND_PARTS = (
    "pytest tests/unit",
    "--cov=quantide",
    "--cov-fail-under=95",
    "--cov-report=term-missing",
    "--cov-report=json:coverage.json",
    "--cov-report=html:htmlcov",
)


def _load_workflow(source: str) -> dict[str, Any]:
    return yaml.safe_load(source)


def _workflow_is_valid(workflow: dict[str, Any]) -> bool:
    triggers = workflow.get("on", workflow.get(True, {}))
    if not {"push", "pull_request"}.issubset(triggers):
        return False
    branches = [*triggers["push"].get("branches", []), *triggers["pull_request"].get("branches", [])]
    if not {"main", "releases/**"}.issubset(branches):
        return False

    jobs = workflow.get("jobs", {})
    coverage_job = jobs.get("unit-coverage", {})
    matrix = coverage_job.get("strategy", {}).get("matrix", {}).get("python-version", [])
    if not any(str(version).startswith("3.13") for version in matrix):
        return False

    steps = coverage_job.get("steps", [])
    commands = "\n".join(str(step.get("run", "")) for step in steps)
    if not all(part in commands for part in CANONICAL_COMMAND_PARTS):
        return False
    if "per_file_coverage.py" not in commands:
        return False
    if any(step.get("continue-on-error") is True for step in steps):
        return False
    environments = [step.get("env", {}) for step in steps]
    return any("HOME" in env and "XDG_CONFIG_HOME" in env for env in environments)


def test_unit_coverage_workflow_enforces_the_two_coverage_gates() -> None:
    """FR-0601 AC-1..AC-5: checked-in workflow has triggers, isolation, and both blocking gates."""
    workflow = _load_workflow(WORKFLOW_PATH.read_text())

    assert _workflow_is_valid(workflow)


def test_workflow_validation_rejects_old_python_matrix() -> None:
    """FR-0601 AC-1: a 3.11-only synthetic workflow is rejected."""
    workflow = _load_workflow(
        """on: {push: {branches: [main, releases/**]}, pull_request: {branches: [main, releases/**]}}
jobs:
  unit-coverage:
    strategy: {matrix: {python-version: ['3.11']}}
    steps: []
"""
    )

    assert _workflow_is_valid(workflow) is False


def test_workflow_validation_rejects_missing_canonical_command() -> None:
    """FR-0601 AC-3: a synthetic workflow without the 95% gate is rejected."""
    workflow = _load_workflow(
        """on: {push: {branches: [main, releases/**]}, pull_request: {branches: [main, releases/**]}}
jobs:
  unit-coverage:
    strategy: {matrix: {python-version: ['3.13']}}
    steps:
      - run: HOME=/tmp XDG_CONFIG_HOME=/tmp pytest tests/unit --cov=quantide
      - run: python tests/unit/_checkers/per_file_coverage.py coverage.json
"""
    )

    assert _workflow_is_valid(workflow) is False


def test_workflow_validation_rejects_non_blocking_gate() -> None:
    """FR-0601 AC-5: a synthetic continue-on-error coverage gate is rejected."""
    workflow = _load_workflow(
        """on: {push: {branches: [main, releases/**]}, pull_request: {branches: [main, releases/**]}}
jobs:
  unit-coverage:
    strategy: {matrix: {python-version: ['3.13']}}
    steps:
      - continue-on-error: true
        run: HOME=/tmp XDG_CONFIG_HOME=/tmp pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing --cov-report=json:coverage.json --cov-report=html:htmlcov
      - run: python tests/unit/_checkers/per_file_coverage.py coverage.json
"""
    )

    assert _workflow_is_valid(workflow) is False

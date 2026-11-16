"""FR-0602 coverage-report artifact contract tests.

AC-FR-0602-1 and AC-FR-0602-2: CI retains the JSON and HTML reports for 30
days and attempts upload even when the blocking coverage gate has failed.
"""

from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(".github/workflows/ci.yml")


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def _artifact_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    steps = workflow["jobs"]["tests"]["steps"]
    return [
        step
        for step in steps
        if "actions/upload-artifact" in str(step.get("uses", ""))
        and str(step.get("with", {}).get("name", "")).startswith("tests-")
    ]


def test_coverage_artifact_retains_json_and_html_reports() -> None:
    """FR-0602 AC-1: a stable 30-day artifact contains coverage.json and htmlcov."""
    artifact_steps = _artifact_steps(_workflow())

    assert len(artifact_steps) == 1
    artifact = artifact_steps[0]
    settings = artifact["with"]
    assert settings["name"] == "tests-${{ matrix.os }}"
    assert settings["retention-days"] == 30
    assert "coverage.json" in settings["path"]
    assert "htmlcov/" in settings["path"]


def test_coverage_artifact_upload_is_attempted_after_a_failed_gate() -> None:
    """FR-0602 AC-2: report upload is always attempted without weakening the gate."""
    artifact = _artifact_steps(_workflow())[0]

    assert artifact["if"] == "always()"
    assert artifact.get("continue-on-error") is not True


def test_artifact_filter_ignores_non_upload_steps() -> None:
    """FR-0602 AC-1: synthetic non-upload steps are not mistaken for report artifacts."""
    workflow = {"jobs": {"tests": {"steps": [{"uses": "actions/checkout@v4"}]}}}

    assert _artifact_steps(workflow) == []


def test_package_artifact_does_not_replace_coverage_evidence() -> None:
    """Adding a publishable wheel must not replace failure-time coverage upload."""
    workflow = _workflow()
    package = next(
        step
        for step in workflow["jobs"]["tests"]["steps"]
        if str(step.get("with", {}).get("name", "")).startswith("package-")
    )
    assert package not in _artifact_steps(workflow)
    assert package.get("if") != "always()"
    assert package["with"]["if-no-files-found"] == "error"
